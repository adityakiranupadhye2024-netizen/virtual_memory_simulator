"""Core logic for a standalone virtual-memory management simulator.

This is an educational simulation. It does not inspect or alter the host OS's
real page tables, physical memory, CPU utilization, or running processes.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
import random
from typing import Deque, Dict, Iterable, List, Optional, Tuple

PAGE_SIZE = 256
TLB_CAPACITY = 8
WORKING_SET_WINDOW = 12
FAULT_WINDOW = 20


class MultiLevelPageTable:
    """A two-level page table using 8 entries per level (for this simulation)."""

    def __init__(self) -> None:
        self.root: Dict[int, Dict[int, int]] = {}

    @staticmethod
    def split_vpn(vpn: int) -> Tuple[int, int]:
        return vpn // 8, vpn % 8

    def lookup(self, vpn: int) -> Tuple[Optional[int], int]:
        """Return (frame index, levels walked)."""
        level_1, level_2 = self.split_vpn(vpn)
        if level_1 not in self.root:
            return None, 1
        return self.root[level_1].get(level_2), 2

    def map_page(self, vpn: int, frame_index: int) -> None:
        level_1, level_2 = self.split_vpn(vpn)
        self.root.setdefault(level_1, {})[level_2] = frame_index

    def unmap_page(self, vpn: int) -> None:
        level_1, level_2 = self.split_vpn(vpn)
        second_level = self.root.get(level_1)
        if second_level is None:
            return
        second_level.pop(level_2, None)
        if not second_level:
            self.root.pop(level_1, None)

    def entries(self) -> Dict[int, int]:
        result: Dict[int, int] = {}
        for level_1, second_level in self.root.items():
            for level_2, frame_index in second_level.items():
                result[level_1 * 8 + level_2] = frame_index
        return result


class TranslationLookasideBuffer:
    """Small LRU translation cache, keyed by (process_id, virtual_page)."""

    def __init__(self, capacity: int = TLB_CAPACITY) -> None:
        self.capacity = capacity
        self.entries: OrderedDict[Tuple[str, int], int] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def lookup(self, key: Tuple[str, int]) -> Optional[int]:
        if key not in self.entries:
            self.misses += 1
            return None
        self.hits += 1
        self.entries.move_to_end(key)
        return self.entries[key]

    def insert(self, key: Tuple[str, int], frame_index: int) -> None:
        self.entries[key] = frame_index
        self.entries.move_to_end(key)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)

    def invalidate(self, pid: str, vpn: Optional[int] = None) -> None:
        for key in list(self.entries):
            if key[0] == pid and (vpn is None or key[1] == vpn):
                self.entries.pop(key, None)

    def clear(self) -> None:
        self.entries.clear()
        self.hits = 0
        self.misses = 0


@dataclass
class PhysicalFrame:
    index: int
    owner: str
    vpn: Optional[int] = None
    loaded_at: int = 0
    last_used: int = 0
    referenced: bool = False


@dataclass
class ProcessState:
    pid: str
    priority: int
    sequence: List[int]
    page_table: MultiLevelPageTable = field(default_factory=MultiLevelPageTable)
    cursor: int = 0
    references: int = 0
    faults: int = 0
    replacements: int = 0
    suspended_until: int = 0
    recent_faults: Deque[int] = field(default_factory=lambda: deque(maxlen=FAULT_WINDOW))
    clock_hand: int = 0

    @property
    def complete(self) -> bool:
        return self.cursor >= len(self.sequence)


class MemorySimulator:
    """Discrete-event simulator for virtual memory, allocation, and thrashing."""

    ALGORITHMS = ("FIFO", "LRU", "Clock", "Optimal")

    def __init__(
        self,
        total_frames: int = 16,
        num_processes: int = 4,
        algorithm: str = "LRU",
        tlb_enabled: bool = True,
        adaptive_enabled: bool = True,
        sequence_length: int = 400,
        seed: int = 42,
        workload_pattern: str = "phase_locality",
        frame_redistribution_enabled: Optional[bool] = None,
        process_suspension_enabled: Optional[bool] = None,
        record_history: bool = True,
    ) -> None:
        if total_frames < 2:
            raise ValueError("Use at least 2 physical frames.")
        if num_processes < 1:
            raise ValueError("Use at least 1 process.")
        if total_frames < num_processes:
            raise ValueError("Physical frames must be at least the number of processes.")
        if algorithm not in self.ALGORITHMS:
            raise ValueError(f"Unknown page replacement algorithm: {algorithm}")
        if sequence_length < 1:
            raise ValueError("Sequence length must be positive.")
        if workload_pattern not in self.WORKLOAD_PATTERNS:
            raise ValueError(f"Unknown workload pattern: {workload_pattern}")

        self.total_frames = total_frames
        self.algorithm = algorithm
        self.tlb_enabled = tlb_enabled
        self.adaptive_enabled = adaptive_enabled
        # Explicit switches support ablation experiments while preserving the GUI's
        # original master adaptive_enabled behavior.
        self.frame_redistribution_enabled = bool(
            adaptive_enabled and (adaptive_enabled if frame_redistribution_enabled is None else frame_redistribution_enabled)
        )
        self.process_suspension_enabled = bool(
            adaptive_enabled and (adaptive_enabled if process_suspension_enabled is None else process_suspension_enabled)
        )
        self.sequence_length = sequence_length
        self.workload_pattern = workload_pattern
        self.record_history = record_history
        self.max_memory_pressure_percent = 0.0
        self.seed = seed
        self.rng = random.Random(seed)
        self.tick = 0
        self.references = 0
        self.page_faults = 0
        self.replacements = 0
        self.page_table_accesses = 0
        self._scheduler_cursor = 0
        self._recent_faults: Deque[int] = deque(maxlen=FAULT_WINDOW)
        self._last_working_sets: Dict[str, int] = {}
        self._last_intervention_tick = -10_000
        self.thrashing_active = False
        self.thrashing_detections = 0
        self.adaptive_actions = 0
        self.frame_redistributions = 0
        self.process_suspensions = 0
        self.events: Deque[str] = deque(maxlen=250)
        self.history: List[dict] = []
        self.tlb = TranslationLookasideBuffer()
        self.processes = self._make_processes(num_processes, sequence_length, seed, workload_pattern)
        self.allocations: Dict[str, List[int]] = {p.pid: [] for p in self.processes}
        self.frames: List[PhysicalFrame] = []
        self._initial_allocate()
        self._record_event(
            f"Simulation initialized: {num_processes} processes, {total_frames} frames, "
            f"{algorithm}, TLB {'ON' if tlb_enabled else 'OFF'}, "
            f"adaptive control {'ON' if (self.frame_redistribution_enabled or self.process_suspension_enabled) else 'OFF'}; "
            f"workload {workload_pattern}."
        )
        if self.record_history:
            self._save_snapshot()

    WORKLOAD_PATTERNS = (
        "phase_locality",
        "uniform_random",
        "sequential_scan",
        "bursty_hotset",
        "alternating_hotsets",
    )

    @staticmethod
    def _make_workload(length: int, seed: int, pattern: str = "phase_locality") -> List[int]:
        """Generate one of five repeatable virtual-page reference patterns."""
        rng = random.Random(seed)
        sequence: List[int] = []
        for i in range(length):
            if pattern == "phase_locality":
                phase = i // 36
                base = (phase * 7 + seed % 5) % 32
                vpn = (base + rng.randrange(8)) % 32 if rng.random() < 0.84 else rng.randrange(32)
            elif pattern == "uniform_random":
                vpn = rng.randrange(64)
            elif pattern == "sequential_scan":
                vpn = i % 64
            elif pattern == "bursty_hotset":
                phase = i // 48
                if phase % 3 == 2:
                    vpn = rng.randrange(64)
                else:
                    base = ((phase // 3) * 13 + seed % 8) % 56
                    vpn = (base + rng.randrange(6)) % 64 if rng.random() < 0.9 else rng.randrange(64)
            elif pattern == "alternating_hotsets":
                base = 0 if (i // 32) % 2 == 0 else 32
                vpn = base + rng.randrange(8)
            else:
                raise ValueError(f"Unknown workload pattern: {pattern}")
            sequence.append(vpn)
        return sequence

    def _make_processes(self, count: int, length: int, seed: int, pattern: str) -> List[ProcessState]:
        return [
            ProcessState(
                pid=f"P{i + 1}",
                priority=count - i,
                sequence=self._make_workload(length, seed + (i + 1) * 101, pattern),
            )
            for i in range(count)
        ]

    def _initial_allocate(self) -> None:
        for index in range(self.total_frames):
            pid = self.processes[index % len(self.processes)].pid
            self.frames.append(PhysicalFrame(index=index, owner=pid))
            self.allocations[pid].append(index)
        for indexes in self.allocations.values():
            indexes.sort()

    def _record_event(self, message: str) -> None:
        self.events.append(f"T{self.tick:04d}  {message}")

    def _process(self, pid: str) -> ProcessState:
        for process in self.processes:
            if process.pid == pid:
                return process
        raise ValueError(f"Unknown process ID: {pid}")

    def _working_set(self, process: ProcessState, end_cursor: Optional[int] = None) -> set[int]:
        end = process.cursor if end_cursor is None else end_cursor
        start = max(0, end - WORKING_SET_WINDOW)
        return set(process.sequence[start:end])

    def _active_processes(self) -> List[ProcessState]:
        return [p for p in self.processes if not p.complete and p.suspended_until <= self.tick]

    def _resume_due_processes(self) -> None:
        resumed = []
        for process in self.processes:
            if process.suspended_until and process.suspended_until <= self.tick and not process.complete:
                process.suspended_until = 0
                resumed.append(process.pid)
        if resumed:
            self._record_event("Resumed process(es): " + ", ".join(resumed) + ".")
            self._rebalance_frames()

    def _pick_process(self) -> Optional[ProcessState]:
        candidates = self._active_processes()
        if not candidates:
            waiting = [p.suspended_until for p in self.processes if not p.complete and p.suspended_until > self.tick]
            if waiting:
                self.tick = min(waiting)
                self._resume_due_processes()
                candidates = self._active_processes()
        if not candidates:
            return None
        # Round-robin while respecting each process's suspension/completion state.
        n = len(self.processes)
        for offset in range(n):
            idx = (self._scheduler_cursor + offset) % n
            p = self.processes[idx]
            if p in candidates:
                self._scheduler_cursor = (idx + 1) % n
                return p
        return candidates[0]

    def _clear_frame(self, frame_index: int) -> None:
        frame = self.frames[frame_index]
        old_pid, old_vpn = frame.owner, frame.vpn
        if old_vpn is not None:
            old_process = self._process(old_pid)
            old_process.page_table.unmap_page(old_vpn)
            self.tlb.invalidate(old_pid, old_vpn)
        frame.vpn = None
        frame.loaded_at = 0
        frame.last_used = 0
        frame.referenced = False

    def _select_victim(self, process: ProcessState, frame_indexes: List[int]) -> int:
        if not frame_indexes:
            raise RuntimeError(f"Process {process.pid} has no allocated frames.")
        occupied = [self.frames[i] for i in frame_indexes if self.frames[i].vpn is not None]
        if len(occupied) < len(frame_indexes):
            return next(i for i in frame_indexes if self.frames[i].vpn is None)

        if self.algorithm == "FIFO":
            return min(frame_indexes, key=lambda i: self.frames[i].loaded_at)
        if self.algorithm == "LRU":
            return min(frame_indexes, key=lambda i: self.frames[i].last_used)
        if self.algorithm == "Clock":
            indexes = sorted(frame_indexes)
            if process.clock_hand not in indexes:
                process.clock_hand = indexes[0]
            while True:
                current = process.clock_hand
                frame = self.frames[current]
                position = indexes.index(current)
                process.clock_hand = indexes[(position + 1) % len(indexes)]
                if not frame.referenced:
                    return current
                frame.referenced = False
        # Optimal replacement uses the known remainder of this generated benchmark stream.
        future = process.sequence[process.cursor:]
        farthest_index = frame_indexes[0]
        farthest_next_use = -1
        for frame_index in frame_indexes:
            vpn = self.frames[frame_index].vpn
            try:
                next_use = future.index(vpn)  # type: ignore[arg-type]
            except ValueError:
                return frame_index
            if next_use > farthest_next_use:
                farthest_next_use = next_use
                farthest_index = frame_index
        return farthest_index

    def _access(self, process: ProcessState, vpn: int) -> dict:
        self.references += 1
        process.references += 1
        offset = (self.tick * 13 + int(process.pid[1:]) * 17) % PAGE_SIZE
        virtual_address = vpn * PAGE_SIZE + offset
        key = (process.pid, vpn)
        frame_index: Optional[int] = None
        tlb_hit = False

        if self.tlb_enabled:
            frame_index = self.tlb.lookup(key)
            tlb_hit = frame_index is not None

        if frame_index is None:
            table_frame, levels_walked = process.page_table.lookup(vpn)
            self.page_table_accesses += levels_walked
            frame_index = table_frame

        fault = frame_index is None
        replaced_vpn: Optional[int] = None
        if fault:
            self.page_faults += 1
            process.faults += 1
            process.recent_faults.append(1)
            self._recent_faults.append(1)
            frame_index = self._select_victim(process, self.allocations[process.pid])
            frame = self.frames[frame_index]
            if frame.vpn is not None:
                replaced_vpn = frame.vpn
                self._clear_frame(frame_index)
                process.replacements += 1
                self.replacements += 1
            frame.vpn = vpn
            frame.loaded_at = self.tick
            frame.last_used = self.tick
            frame.referenced = True
            process.page_table.map_page(vpn, frame_index)
        else:
            process.recent_faults.append(0)
            self._recent_faults.append(0)
            frame = self.frames[frame_index]
            frame.last_used = self.tick
            frame.referenced = True

        if self.tlb_enabled and not tlb_hit:
            self.tlb.insert(key, frame_index)

        physical_address = frame_index * PAGE_SIZE + offset
        self._resume_due_processes()
        if self.references % 10 == 0:
            self._monitor_memory()
        self._save_snapshot()
        return {
            "tick": self.tick,
            "pid": process.pid,
            "vpn": vpn,
            "offset": offset,
            "virtual_address": virtual_address,
            "physical_address": physical_address,
            "frame": frame_index,
            "fault": fault,
            "tlb_hit": tlb_hit,
            "replaced_vpn": replaced_vpn,
        }

    def step(self) -> Optional[dict]:
        """Simulate one memory reference. Return None when all workloads are done."""
        if self.is_complete:
            return None
        self.tick += 1
        self._resume_due_processes()
        process = self._pick_process()
        if process is None:
            return None
        vpn = process.sequence[process.cursor]
        process.cursor += 1
        result = self._access(process, vpn)
        state = "PAGE FAULT" if result["fault"] else ("TLB HIT" if result["tlb_hit"] else "PAGE-TABLE HIT")
        suffix = f", evicted VPN {result['replaced_vpn']}" if result["replaced_vpn"] is not None else ""
        self._record_event(
            f"{process.pid} read VA {result['virtual_address']} (VPN {vpn}) → frame {result['frame']} "
            f"/ PA {result['physical_address']}: {state}{suffix}."
        )
        return result

    @property
    def is_complete(self) -> bool:
        return all(p.complete for p in self.processes)

    def run(self, count: int = 100) -> List[dict]:
        results: List[dict] = []
        for _ in range(max(0, count)):
            result = self.step()
            if result is None:
                break
            results.append(result)
        return results

    def run_to_completion(self, limit: Optional[int] = None) -> List[dict]:
        results: List[dict] = []
        max_steps = limit if limit is not None else self.sequence_length * len(self.processes) * 4
        while not self.is_complete and len(results) < max_steps:
            result = self.step()
            if result is None:
                break
            results.append(result)
        return results

    def _monitor_memory(self) -> None:
        active = [p for p in self.processes if not p.complete and p.suspended_until <= self.tick]
        current_ws = {p.pid: len(self._working_set(p)) for p in active}
        predicted = 0
        for process in active:
            current = current_ws.get(process.pid, 0)
            previous = self._last_working_sets.get(process.pid, current)
            predicted += min(WORKING_SET_WINDOW, current + max(0, current - previous))
            self._last_working_sets[process.pid] = current

        ws_demand = sum(current_ws.values())
        rolling_rate = self.recent_page_fault_rate
        pressure = (100.0 * ws_demand / self.total_frames) if self.total_frames else 0.0
        predicted_pressure = 100.0 * predicted / self.total_frames
        self.max_memory_pressure_percent = max(self.max_memory_pressure_percent, pressure)
        overloaded = ws_demand > self.total_frames or predicted > self.total_frames
        should_thrash = len(self._recent_faults) >= 10 and rolling_rate >= 0.48 and overloaded

        if should_thrash:
            if not self.thrashing_active:
                self.thrashing_detections += 1
                self._record_event(
                    f"THRASHING DETECTED: recent page-fault rate {rolling_rate:.0%}, "
                    f"working-set demand {ws_demand} / {self.total_frames} frames."
                )
            self.thrashing_active = True
        elif rolling_rate < 0.25 and pressure < 85:
            self.thrashing_active = False

        if not (self.frame_redistribution_enabled or self.process_suspension_enabled):
            return
        if self.tick - self._last_intervention_tick < 20:
            return

        if self.thrashing_active:
            active = [p for p in self.processes if not p.complete and p.suspended_until <= self.tick]
            suspended = False
            if self.process_suspension_enabled and len(active) > 1 and pressure >= 100:
                # Suspend the largest current working set, breaking ties toward lower priority.
                victim = max(active, key=lambda p: (len(self._working_set(p)), -p.priority))
                victim.suspended_until = self.tick + 90
                self.process_suspensions += 1
                self.adaptive_actions += 1
                suspended = True
                self._record_event(
                    f"ADAPTIVE RESPONSE: suspended {victim.pid} for 90 ticks to reduce contention."
                )
                if self.frame_redistribution_enabled:
                    self._rebalance_frames()
                self._last_intervention_tick = self.tick

            if self.frame_redistribution_enabled and not suspended:
                changed = self._rebalance_frames()
                if changed:
                    self.adaptive_actions += 1
                    self._record_event("ADAPTIVE RESPONSE: redistributed frames among active processes.")
                    self._last_intervention_tick = self.tick
        elif self.frame_redistribution_enabled and predicted_pressure >= 115:
            changed = self._rebalance_frames()
            if changed:
                self.adaptive_actions += 1
                self._record_event(
                    f"PREDICTIVE RESPONSE: forecast pressure {predicted_pressure:.0f}%; redistributed frames."
                )
                self._last_intervention_tick = self.tick

    def _rebalance_frames(self) -> bool:
        active = [p for p in self.processes if not p.complete and p.suspended_until <= self.tick]
        if not active:
            return False
        if len(active) > self.total_frames:
            active = active[: self.total_frames]
        weights = {p.pid: max(1, len(self._working_set(p))) for p in active}
        desired = {p.pid: 0 for p in self.processes}
        for p in active:
            desired[p.pid] = 1
        extra = self.total_frames - len(active)
        total_weight = sum(weights.values()) or 1
        fractional: List[Tuple[float, str]] = []
        assigned_extra = 0
        for p in active:
            exact = extra * weights[p.pid] / total_weight
            whole = int(exact)
            desired[p.pid] += whole
            assigned_extra += whole
            fractional.append((exact - whole, p.pid))
        for _, pid in sorted(fractional, reverse=True)[: extra - assigned_extra]:
            desired[pid] += 1

        old = {pid: len(indexes) for pid, indexes in self.allocations.items()}
        donors: List[Tuple[str, int]] = []
        for process in self.processes:
            indexes = self.allocations[process.pid]
            while len(indexes) > desired[process.pid]:
                donors.append((process.pid, indexes.pop()))
        recipients: List[str] = []
        for p in active:
            recipients.extend([p.pid] * max(0, desired[p.pid] - len(self.allocations[p.pid])))
        if not donors and not recipients:
            return False
        while donors and recipients:
            _old_pid, frame_index = donors.pop()
            new_pid = recipients.pop(0)
            self._clear_frame(frame_index)
            self.frames[frame_index].owner = new_pid
            self.allocations[new_pid].append(frame_index)
        # Defensive fallback: under valid inputs, donor/recipient counts always balance.
        for pid, frame_index in donors:
            self.allocations[pid].append(frame_index)
        for indexes in self.allocations.values():
            indexes.sort()
        for frame in self.frames:
            if frame.index not in self.allocations[frame.owner]:
                raise RuntimeError("Frame ownership/allocation invariant broken.")
        changed = old != {pid: len(indexes) for pid, indexes in self.allocations.items()}
        if changed:
            self.frame_redistributions += 1
        return changed

    @property
    def recent_page_fault_rate(self) -> float:
        return (sum(self._recent_faults) / len(self._recent_faults)) if self._recent_faults else 0.0

    @property
    def overall_page_fault_rate(self) -> float:
        return self.page_faults / self.references if self.references else 0.0

    @property
    def tlb_hit_rate(self) -> Optional[float]:
        total = self.tlb.hits + self.tlb.misses
        if not self.tlb_enabled:
            return None
        return self.tlb.hits / total if total else 0.0

    def metrics(self) -> dict:
        active = [p for p in self.processes if not p.complete and p.suspended_until <= self.tick]
        ws_by_pid = {p.pid: len(self._working_set(p)) for p in active}
        ws_demand = sum(ws_by_pid.values())
        predicted_demand = 0
        for p in active:
            current = ws_by_pid[p.pid]
            previous = self._last_working_sets.get(p.pid, current)
            predicted_demand += min(WORKING_SET_WINDOW, current + max(0, current - previous))
        pressure = 100.0 * ws_demand / self.total_frames
        predicted_pressure = 100.0 * predicted_demand / self.total_frames
        rolling = self.recent_page_fault_rate
        # A simulated CPU-utilization proxy: page-fault overhead and excess demand lower it.
        cpu = max(8.0, min(98.0, 96.0 - rolling * 110.0 - max(0.0, pressure - 100.0) * 0.30))
        if self.is_complete:
            status = "COMPLETE"
        elif self.thrashing_active:
            status = "THRASHING DETECTED"
        elif predicted_pressure >= 100:
            status = "HIGH MEMORY PRESSURE"
        else:
            status = "NORMAL"
        return {
            "tick": self.tick,
            "references": self.references,
            "page_faults": self.page_faults,
            "replacements": self.replacements,
            "page_fault_rate": rolling,
            "overall_page_fault_rate": self.overall_page_fault_rate,
            "tlb_hit_rate": self.tlb_hit_rate,
            "tlb_hits": self.tlb.hits,
            "tlb_misses": self.tlb.misses,
            "page_table_accesses": self.page_table_accesses,
            "memory_pressure": pressure,
            "predicted_pressure": predicted_pressure,
            "working_set_demand": ws_demand,
            "predicted_working_set_demand": predicted_demand,
            "available_frames": self.total_frames,
            "cpu_utilization": cpu,
            "status": status,
            "active_processes": len(active),
            "thrashing_detections": self.thrashing_detections,
            "adaptive_actions": self.adaptive_actions,
            "process_suspensions": self.process_suspensions,
        }

    def process_rows(self) -> List[dict]:
        rows = []
        for p in self.processes:
            refs = p.references
            rows.append({
                "pid": p.pid,
                "status": "SUSPENDED" if p.suspended_until > self.tick else ("DONE" if p.complete else "ACTIVE"),
                "priority": p.priority,
                "frames": len(self.allocations[p.pid]),
                "working_set": len(self._working_set(p)),
                "references": refs,
                "faults": p.faults,
                "fault_rate": p.faults / refs if refs else 0.0,
                "replacements": p.replacements,
                "progress": p.cursor / len(p.sequence) if p.sequence else 1.0,
            })
        return rows

    def frame_rows(self) -> List[dict]:
        return [
            {"frame": f.index, "owner": f.owner, "vpn": "—" if f.vpn is None else f.vpn,
             "status": "FREE" if f.vpn is None else "RESIDENT"}
            for f in self.frames
        ]

    def translation_details(self, pid: str, virtual_address: int) -> dict:
        """Explain a hypothetical address translation without changing the run.

        The simulator exposes 64 virtual pages (8 entries at each page-table
        level), so the valid virtual-address range is 0..16383 for 256-byte
        pages. This inspection is read-only: it does not increment TLB stats,
        page faults, or the simulation clock.
        """
        process = self._process(pid)
        if not isinstance(virtual_address, int) or isinstance(virtual_address, bool):
            raise ValueError("Virtual address must be an integer.")
        if not 0 <= virtual_address < PAGE_SIZE * 64:
            raise ValueError(f"Virtual address must be between 0 and {PAGE_SIZE * 64 - 1}.")

        vpn, offset = divmod(virtual_address, PAGE_SIZE)
        l1, l2 = MultiLevelPageTable.split_vpn(vpn)
        frame, levels = process.page_table.lookup(vpn)
        tlb_frame = self.tlb.entries.get((pid, vpn)) if self.tlb_enabled else None
        tlb_cached = tlb_frame is not None and tlb_frame == frame
        source = "TLB" if tlb_cached else ("Page table" if frame is not None else "Page fault required")
        return {
            "pid": pid,
            "virtual_address": virtual_address,
            "vpn": vpn,
            "offset": offset,
            "level_1_index": l1,
            "level_2_index": l2,
            "levels_walked": 0 if tlb_cached else levels,
            "resident": frame is not None,
            "frame": frame,
            "physical_address": frame * PAGE_SIZE + offset if frame is not None else None,
            "tlb_cached": tlb_cached,
            "translation_source": source,
        }

    def _save_snapshot(self) -> None:
        m = self.metrics()
        self.history.append({
            "tick": m["tick"],
            "references": m["references"],
            "page_faults": m["page_faults"],
            "rolling_page_fault_rate": round(m["page_fault_rate"], 5),
            "overall_page_fault_rate": round(m["overall_page_fault_rate"], 5),
            "tlb_hit_rate": "" if m["tlb_hit_rate"] is None else round(m["tlb_hit_rate"], 5),
            "memory_pressure_percent": round(m["memory_pressure"], 2),
            "predicted_pressure_percent": round(m["predicted_pressure"], 2),
            "working_set_demand": m["working_set_demand"],
            "predicted_working_set_demand": m["predicted_working_set_demand"],
            "simulated_cpu_utilization_percent": round(m["cpu_utilization"], 2),
            "status": m["status"],
        })
