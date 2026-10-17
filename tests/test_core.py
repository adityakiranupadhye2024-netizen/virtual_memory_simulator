import unittest

from vm_simulator.core import MemorySimulator, MultiLevelPageTable, TranslationLookasideBuffer


class PageTableTests(unittest.TestCase):
    def test_two_level_mapping_and_unmapping(self):
        table = MultiLevelPageTable()
        self.assertEqual(table.lookup(19), (None, 1))
        table.map_page(19, 7)
        self.assertEqual(table.lookup(19), (7, 2))
        self.assertEqual(table.entries(), {19: 7})
        table.unmap_page(19)
        self.assertEqual(table.lookup(19), (None, 1))

    def test_tlb_hit_and_invalidation(self):
        tlb = TranslationLookasideBuffer(capacity=2)
        tlb.insert(("P1", 4), 3)
        self.assertEqual(tlb.lookup(("P1", 4)), 3)
        self.assertIsNone(tlb.lookup(("P1", 5)))
        tlb.invalidate("P1", 4)
        self.assertIsNone(tlb.lookup(("P1", 4)))


class SimulatorTests(unittest.TestCase):
    def test_simulation_preserves_frame_invariants(self):
        sim = MemorySimulator(total_frames=12, num_processes=3, sequence_length=80, seed=5)
        sim.run_to_completion()
        self.assertEqual(sim.references, 240)
        self.assertEqual(len(sim.frames), 12)
        allocated = [idx for indexes in sim.allocations.values() for idx in indexes]
        self.assertEqual(sorted(allocated), list(range(12)))
        for pid, indexes in sim.allocations.items():
            for idx in indexes:
                self.assertEqual(sim.frames[idx].owner, pid)
        self.assertLessEqual(sim.page_faults, sim.references)
        self.assertGreater(sim.replacements, 0)

    def test_all_replacement_algorithms_run(self):
        for algorithm in MemorySimulator.ALGORITHMS:
            sim = MemorySimulator(total_frames=8, num_processes=2, algorithm=algorithm, sequence_length=40)
            sim.run_to_completion()
            self.assertEqual(sim.references, 80)

    def test_tlb_disabled_has_no_tlb_rate(self):
        sim = MemorySimulator(total_frames=4, num_processes=2, tlb_enabled=False, sequence_length=10)
        sim.run(5)
        self.assertIsNone(sim.metrics()["tlb_hit_rate"])

    def test_tlb_does_not_change_page_faults_but_reduces_table_accesses(self):
        enabled = MemorySimulator(total_frames=8, num_processes=2, tlb_enabled=True,
                                  adaptive_enabled=False, sequence_length=100, seed=7)
        disabled = MemorySimulator(total_frames=8, num_processes=2, tlb_enabled=False,
                                   adaptive_enabled=False, sequence_length=100, seed=7)
        enabled.run_to_completion()
        disabled.run_to_completion()
        self.assertEqual(enabled.page_faults, disabled.page_faults)
        self.assertLess(enabled.page_table_accesses, disabled.page_table_accesses)

    def test_adaptive_control_preserves_frame_ownership_invariants(self):
        sim = MemorySimulator(total_frames=8, num_processes=4, adaptive_enabled=True,
                              sequence_length=70, seed=42)
        sim.run_to_completion()
        allocated = [idx for indexes in sim.allocations.values() for idx in indexes]
        self.assertEqual(sorted(allocated), list(range(sim.total_frames)))
        for pid, indexes in sim.allocations.items():
            for idx in indexes:
                self.assertEqual(sim.frames[idx].owner, pid)
        self.assertGreaterEqual(sim.adaptive_actions, 0)

    def test_translation_inspector_reports_hierarchical_indices_without_mutation(self):
        sim = MemorySimulator(total_frames=4, num_processes=2, sequence_length=10, adaptive_enabled=False)
        process = sim.processes[0]
        frame_index = sim.allocations[process.pid][0]
        sim.frames[frame_index].vpn = 19
        process.page_table.map_page(19, frame_index)
        before = (sim.references, sim.page_faults, sim.tlb.hits, sim.tlb.misses, sim.tick)

        detail = sim.translation_details(process.pid, 19 * 256 + 7)

        self.assertEqual(detail["vpn"], 19)
        self.assertEqual(detail["offset"], 7)
        self.assertEqual(detail["level_1_index"], 2)
        self.assertEqual(detail["level_2_index"], 3)
        self.assertEqual(detail["physical_address"], frame_index * 256 + 7)
        self.assertTrue(detail["resident"])
        after = (sim.references, sim.page_faults, sim.tlb.hits, sim.tlb.misses, sim.tick)
        self.assertEqual(before, after)

    def test_supported_workload_patterns_produce_valid_sequences(self):
        for pattern in MemorySimulator.WORKLOAD_PATTERNS:
            sim = MemorySimulator(total_frames=8, num_processes=2, sequence_length=50,
                                  seed=123, workload_pattern=pattern, adaptive_enabled=False)
            sim.run_to_completion()
            self.assertEqual(sim.references, 100, pattern)
            for process in sim.processes:
                self.assertEqual(len(process.sequence), 50, pattern)
                self.assertTrue(all(0 <= vpn < 64 for vpn in process.sequence), pattern)

    def test_adaptive_mechanisms_can_be_enabled_independently(self):
        red = MemorySimulator(total_frames=8, num_processes=2, sequence_length=60, seed=42,
                              frame_redistribution_enabled=True, process_suspension_enabled=False)
        sus = MemorySimulator(total_frames=8, num_processes=2, sequence_length=60, seed=42,
                              frame_redistribution_enabled=False, process_suspension_enabled=True)
        self.assertTrue(red.frame_redistribution_enabled)
        self.assertFalse(red.process_suspension_enabled)
        self.assertFalse(sus.frame_redistribution_enabled)
        self.assertTrue(sus.process_suspension_enabled)

    def test_suspension_only_preserves_frame_ownership_invariants(self):
        sim = MemorySimulator(total_frames=8, num_processes=4, sequence_length=80, seed=42,
                              frame_redistribution_enabled=False, process_suspension_enabled=True)
        sim.run_to_completion()
        allocated = [idx for indexes in sim.allocations.values() for idx in indexes]
        self.assertEqual(sorted(allocated), list(range(sim.total_frames)))
        for pid, indexes in sim.allocations.items():
            for idx in indexes:
                self.assertEqual(sim.frames[idx].owner, pid)

    def test_translation_inspector_validation(self):
        sim = MemorySimulator(total_frames=4, num_processes=2, sequence_length=10)
        with self.assertRaises(ValueError):
            sim.translation_details("P1", -1)
        with self.assertRaises(ValueError):
            sim.translation_details("P1", 16384)
        with self.assertRaises(ValueError):
            sim.translation_details("P9", 0)

    def test_tlb_cached_translation_is_detected(self):
        sim = MemorySimulator(total_frames=4, num_processes=2, sequence_length=10)
        process = sim.processes[0]
        frame_index = sim.allocations[process.pid][0]
        sim.frames[frame_index].vpn = 4
        process.page_table.map_page(4, frame_index)
        sim.tlb.insert((process.pid, 4), frame_index)
        detail = sim.translation_details(process.pid, 4 * 256 + 3)
        self.assertTrue(detail["tlb_cached"])
        self.assertEqual(detail["translation_source"], "TLB")
        self.assertEqual(detail["levels_walked"], 0)


if __name__ == "__main__":
    unittest.main()
