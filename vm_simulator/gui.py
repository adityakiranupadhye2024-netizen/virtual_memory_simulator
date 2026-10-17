"""Tkinter dashboard for the virtual-memory simulator."""
from __future__ import annotations

import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .core import MemorySimulator


class MemorySimulatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Predictive & Adaptive Virtual Memory Management")
        self.root.geometry("1320x850")
        self.root.minsize(1080, 720)

        self.process_var = tk.IntVar(value=4)
        self.frames_var = tk.IntVar(value=16)
        self.translation_process_var = tk.StringVar(value="P1")
        self.translation_address_var = tk.StringVar(value="0")
        self.translation_result_var = tk.StringVar(value="Enter a virtual address and click Inspect.")
        self.algorithm_var = tk.StringVar(value="LRU")
        self.tlb_var = tk.BooleanVar(value=True)
        self.adaptive_var = tk.BooleanVar(value=True)
        self.batch_var = tk.IntVar(value=50)
        self.simulator = self._new_simulator()
        self._last_event_count = 0

        self._build_ui()
        self._refresh_ui()

    def _new_simulator(self) -> MemorySimulator:
        processes = max(1, self.process_var.get())
        frames = max(processes, self.frames_var.get())
        self.frames_var.set(frames)
        return MemorySimulator(
            total_frames=frames,
            num_processes=processes,
            algorithm=self.algorithm_var.get(),
            tlb_enabled=self.tlb_var.get(),
            adaptive_enabled=self.adaptive_var.get(),
        )

    def _build_ui(self) -> None:
        controls = ttk.LabelFrame(self.root, text="Simulation Controls", padding=8)
        controls.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(controls, text="Processes").grid(row=0, column=0, padx=(0, 4), sticky="w")
        ttk.Spinbox(controls, from_=1, to=8, width=5, textvariable=self.process_var).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(controls, text="Physical frames").grid(row=0, column=2, padx=(0, 4), sticky="w")
        ttk.Spinbox(controls, from_=2, to=64, width=5, textvariable=self.frames_var).grid(row=0, column=3, padx=(0, 12))
        ttk.Label(controls, text="Replacement").grid(row=0, column=4, padx=(0, 4), sticky="w")
        ttk.Combobox(controls, textvariable=self.algorithm_var, values=MemorySimulator.ALGORITHMS,
                     state="readonly", width=10).grid(row=0, column=5, padx=(0, 12))
        ttk.Checkbutton(controls, text="TLB enabled", variable=self.tlb_var).grid(row=0, column=6, padx=(0, 10))
        ttk.Checkbutton(controls, text="Adaptive control", variable=self.adaptive_var).grid(row=0, column=7, padx=(0, 10))
        ttk.Label(controls, text="Batch size").grid(row=0, column=8, padx=(0, 4), sticky="w")
        ttk.Spinbox(controls, from_=1, to=1000, increment=10, width=6, textvariable=self.batch_var).grid(row=0, column=9, padx=(0, 12))

        ttk.Button(controls, text="Step", command=self._step).grid(row=0, column=10, padx=3)
        ttk.Button(controls, text="Run Batch", command=self._run_batch).grid(row=0, column=11, padx=3)
        ttk.Button(controls, text="Run to End", command=self._run_to_end).grid(row=0, column=12, padx=3)
        ttk.Button(controls, text="Reset", command=self._reset).grid(row=0, column=13, padx=3)
        ttk.Button(controls, text="Export CSV", command=self._export_csv).grid(row=0, column=14, padx=3)

        notice = ttk.Label(
            self.root,
            text="Educational simulation only. CPU utilization and memory pressure are simulated metrics, not live macOS measurements.",
            foreground="#7a4b00",
        )
        notice.pack(fill="x", padx=12, pady=(0, 5))

        translation_box = ttk.LabelFrame(self.root, text="Virtual Address Translation Inspector (read-only)", padding=6)
        translation_box.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Label(translation_box, text="Process").grid(row=0, column=0, padx=(0, 4), sticky="w")
        self.translation_process_combo = ttk.Combobox(
            translation_box, textvariable=self.translation_process_var,
            values=tuple(f"P{i}" for i in range(1, self.process_var.get() + 1)),
            state="readonly", width=6,
        )
        self.translation_process_combo.grid(row=0, column=1, padx=(0, 10))
        ttk.Label(translation_box, text="Virtual address (0–16383)").grid(row=0, column=2, padx=(0, 4), sticky="w")
        ttk.Entry(translation_box, textvariable=self.translation_address_var, width=10).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(translation_box, text="Inspect", command=self._inspect_translation).grid(row=0, column=4, padx=(0, 12))
        ttk.Label(translation_box, textvariable=self.translation_result_var, wraplength=930, justify="left").grid(
            row=0, column=5, sticky="w"
        )
        translation_box.columnconfigure(5, weight=1)

        self.metric_frame = ttk.Frame(self.root)
        self.metric_frame.pack(fill="x", padx=10, pady=5)
        self.metric_labels: dict[str, ttk.Label] = {}
        metric_specs = [
            ("fault_rate", "Recent page-fault rate"), ("tlb_rate", "TLB hit rate"),
            ("pressure", "Memory pressure"), ("cpu", "Simulated CPU utilization"),
            ("working_set", "Working-set demand"), ("status", "System status"),
        ]
        for i, (key, title) in enumerate(metric_specs):
            card = ttk.LabelFrame(self.metric_frame, text=title, padding=(8, 4))
            card.grid(row=0, column=i, padx=4, sticky="nsew")
            value = ttk.Label(card, text="—", font=("Arial", 14, "bold"), width=16)
            value.pack(anchor="center", pady=2)
            self.metric_labels[key] = value
            self.metric_frame.columnconfigure(i, weight=1)

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=10, pady=5)
        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=3)
        main.add(right, weight=2)

        process_box = ttk.LabelFrame(left, text="Process Memory / Workload Statistics", padding=5)
        process_box.pack(fill="both", expand=True, pady=(0, 5))
        columns = ("pid", "state", "frames", "ws", "refs", "faults", "fault_rate", "replacements", "progress")
        self.process_tree = ttk.Treeview(process_box, columns=columns, show="headings", height=6)
        headings = {
            "pid": "Process", "state": "State", "frames": "Frames", "ws": "Working set",
            "refs": "References", "faults": "Faults", "fault_rate": "Fault rate",
            "replacements": "Replacements", "progress": "Progress",
        }
        widths = {"pid": 60, "state": 90, "frames": 60, "ws": 86, "refs": 80, "faults": 65, "fault_rate": 80, "replacements": 95, "progress": 80}
        for col in columns:
            self.process_tree.heading(col, text=headings[col])
            self.process_tree.column(col, width=widths[col], anchor="center")
        self.process_tree.pack(fill="both", expand=True)

        chart_box = ttk.LabelFrame(left, text="Performance Over Time", padding=5)
        chart_box.pack(fill="both", expand=True)
        self.figure = Figure(figsize=(7.0, 3.2), dpi=90, layout="constrained")
        self.ax_fault = self.figure.add_subplot(211)
        self.ax_pressure = self.figure.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_box)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        frame_box = ttk.LabelFrame(right, text="Physical Memory Frames", padding=5)
        frame_box.pack(fill="both", expand=True, pady=(0, 5))
        self.frame_tree = ttk.Treeview(frame_box, columns=("frame", "owner", "vpn", "state"), show="headings", height=10)
        for col, title, width in (("frame", "Frame", 55), ("owner", "Allocated to", 90), ("vpn", "Resident VPN", 90), ("state", "State", 90)):
            self.frame_tree.heading(col, text=title)
            self.frame_tree.column(col, width=width, anchor="center")
        self.frame_tree.pack(fill="both", expand=True)

        log_box = ttk.LabelFrame(right, text="Simulation Event Log", padding=5)
        log_box.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_box, height=12, wrap="word", state="disabled", font=("Menlo", 9))
        log_scroll = ttk.Scrollbar(log_box, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        footer = ttk.Label(self.root, text="Address translation uses 256-byte pages and a two-level page table (8 × 8 VPN index structure).", foreground="#555555")
        footer.pack(fill="x", padx=12, pady=(0, 8))

    def _step(self) -> None:
        self.simulator.step()
        self._refresh_ui()

    def _run_batch(self) -> None:
        try:
            count = max(1, min(1000, int(self.batch_var.get())))
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid batch size", "Enter an integer between 1 and 1000.")
            return
        self.simulator.run(count)
        self._refresh_ui()

    def _run_to_end(self) -> None:
        self.simulator.run_to_completion()
        self._refresh_ui()

    def _reset(self) -> None:
        try:
            self.simulator = self._new_simulator()
        except ValueError as exc:
            messagebox.showerror("Invalid configuration", str(exc))
            return
        self._last_event_count = 0
        valid_processes = tuple(f"P{i}" for i in range(1, len(self.simulator.processes) + 1))
        self.translation_process_combo.configure(values=valid_processes)
        if self.translation_process_var.get() not in valid_processes:
            self.translation_process_var.set(valid_processes[0])
        self.translation_result_var.set("Simulation reset. Address inspection does not change statistics.")
        self._refresh_ui()

    def _inspect_translation(self) -> None:
        try:
            pid = self.translation_process_var.get()
            address = int(self.translation_address_var.get().strip())
            detail = self.simulator.translation_details(pid, address)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Invalid virtual address", str(exc))
            return

        if detail["resident"]:
            result = (
                f"VA {detail['virtual_address']} → VPN {detail['vpn']}, offset {detail['offset']} | "
                f"L1 index {detail['level_1_index']}, L2 index {detail['level_2_index']} | "
                f"{detail['translation_source']} | frame {detail['frame']} → "
                f"PA {detail['physical_address']}"
            )
        else:
            result = (
                f"VA {detail['virtual_address']} → VPN {detail['vpn']}, offset {detail['offset']} | "
                f"L1 index {detail['level_1_index']}, L2 index {detail['level_2_index']} | "
                "not resident: a page fault is required before physical translation"
            )
        self.translation_result_var.set(result)

    def _export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export performance history",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"),),
            initialfile="virtual_memory_performance.csv",
        )
        if not path:
            return
        try:
            history = self.simulator.history
            if not history:
                messagebox.showinfo("Nothing to export", "Run the simulation before exporting.")
                return
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(history[0].keys()))
                writer.writeheader()
                writer.writerows(history)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        messagebox.showinfo("Export complete", f"Saved {len(self.simulator.history)} history rows to:\n{path}")

    def _refresh_ui(self) -> None:
        m = self.simulator.metrics()
        self.metric_labels["fault_rate"].configure(text=f"{m['page_fault_rate']:.0%}")
        self.metric_labels["tlb_rate"].configure(text="OFF" if m["tlb_hit_rate"] is None else f"{m['tlb_hit_rate']:.0%}")
        self.metric_labels["pressure"].configure(text=f"{m['memory_pressure']:.0f}%  (forecast {m['predicted_pressure']:.0f}%)")
        self.metric_labels["cpu"].configure(text=f"{m['cpu_utilization']:.0f}%")
        self.metric_labels["working_set"].configure(text=f"{m['working_set_demand']} / {m['available_frames']} frames")
        self.metric_labels["status"].configure(text=m["status"])

        for tree in (self.process_tree, self.frame_tree):
            for item in tree.get_children():
                tree.delete(item)
        for row in self.simulator.process_rows():
            self.process_tree.insert("", "end", values=(
                row["pid"], row["status"], row["frames"], row["working_set"], row["references"],
                row["faults"], f"{row['fault_rate']:.0%}", row["replacements"], f"{row['progress']:.0%}",
            ))
        for row in self.simulator.frame_rows():
            self.frame_tree.insert("", "end", values=(row["frame"], row["owner"], row["vpn"], row["status"]))

        history = self.simulator.history
        self.ax_fault.clear()
        self.ax_pressure.clear()
        if history:
            x = [r["references"] for r in history]
            y_fault = [100 * r["rolling_page_fault_rate"] for r in history]
            y_pressure = [r["memory_pressure_percent"] for r in history]
            y_forecast = [r["predicted_pressure_percent"] for r in history]
            self.ax_fault.plot(x, y_fault, linewidth=1.3, label="Rolling page faults")
            self.ax_fault.set_ylabel("Fault rate (%)")
            self.ax_fault.set_ylim(0, 100)
            self.ax_fault.grid(True, alpha=0.25)
            self.ax_fault.legend(loc="upper right", fontsize=8)
            self.ax_pressure.plot(x, y_pressure, linewidth=1.3, label="Current pressure")
            self.ax_pressure.plot(x, y_forecast, linewidth=1.0, linestyle="--", label="Predicted pressure")
            self.ax_pressure.axhline(100, linewidth=1.0, linestyle=":", label="Frame capacity")
            self.ax_pressure.set_xlabel("Memory references processed")
            self.ax_pressure.set_ylabel("Demand / capacity (%)")
            self.ax_pressure.grid(True, alpha=0.25)
            self.ax_pressure.legend(loc="upper right", fontsize=8)
        self.canvas.draw_idle()

        new_events = list(self.simulator.events)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "\n".join(new_events[-100:]))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self._last_event_count = len(new_events)


def launch() -> None:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("clam")
    except tk.TclError:
        pass
    MemorySimulatorApp(root)
    root.mainloop()
