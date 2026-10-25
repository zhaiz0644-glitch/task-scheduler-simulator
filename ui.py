"""图形界面模块（UI）

基于 Tkinter 的任务调度模拟器界面，负责：
- 任务输入与管理：表格展示、添加 / 修改 / 删除、从 CSV/JSON 加载、保存。
- 调度控制：算法选择、时间片设置、开始 / 暂停 / 单步 / 运行到底 / 重置、演示速度调节。
- 过程展示：当前模拟时间、正在执行的任务、就绪队列，以及甘特图与“当前时刻”游标。
- 结果统计：逐任务周转 / 等待 / 响应时间及平均值，支持导出 CSV。
- 算法对比：对同一组任务运行三种算法（含 RR 不同时间片），比较平均指标。

设计原则：界面只负责“显示与回放”，调度结果全部由 scheduler.SimulationEngine
预先算好，动画速度仅控制回放节奏，不影响任何调度结果。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from data_loader import load_tasks, save_results, save_tasks
from scheduler import (
    ALGORITHM_FCFS,
    ALGORITHM_NAMES,
    ALGORITHM_PRIO,
    ALGORITHM_RR,
    SimulationEngine,
    SimulationResult,
    run_comparison,
)
from task import Task, validate_tasks

# ------------------------------------------------------------------ #
# 颜色与常量
# ------------------------------------------------------------------ #
STATE_TAG = {
    "未到达": "notarrived",
    "就绪": "ready",
    "运行中": "running",
    "完成": "finished",
}
STATE_BG = {
    "未到达": "#f3f4f6",
    "就绪": "#dbeafe",
    "运行中": "#bbf7d0",
    "完成": "#fde68a",
}
# 甘特图任务配色（按输入顺序循环取用）
TASK_COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    "#6c8ebf", "#d6b656",
]
IDLE_COLOR = "#e5e7eb"
IDLE_TEXT = "#9ca3af"

ALGORITHM_OPTIONS = [ALGORITHM_FCFS, ALGORITHM_PRIO, ALGORITHM_RR]


class TaskSchedulerApp:
    """任务调度模拟器主窗口。"""

    def __init__(self, root: tk.Tk | None = None) -> None:
        self.root = root or tk.Tk()
        self.root.title("任务调度模拟器")
        self.root.geometry("1180x760")

        self.tasks: list[Task] = []
        self.result: SimulationResult | None = None
        self.step_index = 0
        self.playing = False
        self.after_id: str | None = None

        self.algorithm_var = tk.StringVar(value=ALGORITHM_FCFS)
        self.time_slice_var = tk.StringVar(value="2")
        self.speed_var = tk.DoubleVar(value=10.0)

        self._build_style()
        self._build_toolbar()
        self._build_task_panel()
        self._build_gantt()
        self._build_bottom_panel()
        self._update_edit_state()

    # ------------------------------------------------------------------ #
    # 界面搭建
    # ------------------------------------------------------------------ #
    def _build_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(side="top", fill="x")
        self.load_btn = ttk.Button(bar, text="加载数据…", command=self.load_file)
        self.load_btn.pack(side="left")
        ttk.Button(bar, text="保存数据…", command=self.save_file).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        self.add_btn = ttk.Button(bar, text="添加任务", command=self.add_task)
        self.add_btn.pack(side="left")
        self.edit_btn = ttk.Button(bar, text="修改任务", command=self.edit_task)
        self.edit_btn.pack(side="left")
        self.del_btn = ttk.Button(bar, text="删除任务", command=self.delete_task)
        self.del_btn.pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(bar, text="重置", command=self.reset_view).pack(side="left")

    def _build_task_panel(self) -> None:
        container = ttk.Frame(self.root, padding=(8, 0))
        container.pack(side="top", fill="both", expand=True)

        # 左：任务表格
        left = ttk.LabelFrame(container, text="任务列表", padding=6)
        left.pack(side="left", fill="both", expand=True)
        cols = ("id", "name", "arrival", "burst", "priority", "remaining", "state")
        self.task_tree = ttk.Treeview(left, columns=cols, show="headings", height=8)
        headers = {
            "id": "编号", "name": "名称", "arrival": "到达时间",
            "burst": "运行时长", "priority": "优先级",
            "remaining": "剩余时长", "state": "状态",
        }
        widths = {"id": 70, "name": 130, "arrival": 80, "burst": 80,
                  "priority": 70, "remaining": 80, "state": 80}
        for c in cols:
            self.task_tree.heading(c, text=headers[c])
            self.task_tree.column(c, width=widths[c], anchor="center")
        for state, bg in STATE_BG.items():
            self.task_tree.tag_configure(STATE_TAG[state], background=bg)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=vsb.set)
        self.task_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 右：调度控制面板
        right = ttk.LabelFrame(container, text="调度控制", padding=8)
        right.pack(side="right", fill="y", padx=(8, 0))
        ttk.Label(right, text="调度算法：").grid(row=0, column=0, sticky="w")
        for r, alg in enumerate(ALGORITHM_OPTIONS):
            ttk.Radiobutton(
                right, text=ALGORITHM_NAMES[alg], value=alg,
                variable=self.algorithm_var, command=self._on_algorithm_change,
            ).grid(row=r + 1, column=0, sticky="w")

        ttk.Label(right, text="时间片 q（仅 RR）：").grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.slice_spin = ttk.Spinbox(right, from_=1, to=1000, width=8,
                                      textvariable=self.time_slice_var)
        self.slice_spin.grid(row=5, column=0, sticky="w")

        ttk.Label(right, text="演示速度（单位/秒）：").grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Scale(right, from_=1, to=100, variable=self.speed_var, orient="horizontal",
                  length=180).grid(row=7, column=0, sticky="w")

        btns = ttk.Frame(right)
        btns.grid(row=8, column=0, sticky="w", pady=(12, 0))
        ttk.Button(btns, text="开始", command=self.start).pack(side="left")
        self.play_btn = ttk.Button(btns, text="暂停", command=self.toggle_pause)
        self.play_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="单步", command=self.step_once).pack(side="left")
        ttk.Button(btns, text="运行到底", command=self.run_to_end).pack(side="left", padx=4)

        # 状态显示
        status = ttk.LabelFrame(right, text="当前状态", padding=8)
        status.grid(row=9, column=0, sticky="ew", pady=(12, 0))
        self.time_var = tk.StringVar(value="0")
        self.run_var = tk.StringVar(value="空闲")
        self.queue_var = tk.StringVar(value="（空）")
        self.event_var = tk.StringVar(value="")
        ttk.Label(status, text="当前时间：").grid(row=0, column=0, sticky="w")
        ttk.Label(status, textvariable=self.time_var, font=("Consolas", 14, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(status, text="运行中：").grid(row=1, column=0, sticky="w")
        ttk.Label(status, textvariable=self.run_var).grid(row=1, column=1, sticky="w")
        ttk.Label(status, text="就绪队列：").grid(row=2, column=0, sticky="w")
        ttk.Label(status, textvariable=self.queue_var, wraplength=200, justify="left").grid(row=2, column=1, sticky="w")
        ttk.Label(status, textvariable=self.event_var, wraplength=240, justify="left",
                  foreground="#6b7280").grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self._on_algorithm_change()

    def _build_gantt(self) -> None:
        frame = ttk.LabelFrame(self.root, text="甘特图（处理器执行区间 / 空闲区间）", padding=6)
        frame.pack(side="top", fill="x")
        self.gantt = tk.Canvas(frame, height=130, bg="#ffffff", highlightthickness=0)
        self.gantt.pack(fill="x", expand=True)
        self.gantt.bind("<Configure>", lambda e: self._redraw_gantt())

    def _build_bottom_panel(self) -> None:
        bottom = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bottom.pack(side="top", fill="both", expand=True)

        # 左：统计结果
        rframe = ttk.LabelFrame(bottom, text="统计结果（周转 / 等待 / 响应时间）", padding=6)
        rframe.pack(side="left", fill="both", expand=True)
        rcols = ("id", "name", "start", "finish", "turnaround", "waiting", "response")
        self.result_tree = ttk.Treeview(rframe, columns=rcols, show="headings", height=5)
        rheaders = {"id": "编号", "name": "名称", "start": "首次开始 S",
                    "finish": "完成 C", "turnaround": "周转 T", "waiting": "等待 W",
                    "response": "响应 R"}
        for c in rcols:
            self.result_tree.heading(c, text=rheaders[c])
            self.result_tree.column(c, width=70 if c == "id" else 90, anchor="center")
        self.result_tree.pack(side="left", fill="both", expand=True)
        rvsb = ttk.Scrollbar(rframe, orient="vertical", command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=rvsb.set)
        rvsb.pack(side="right", fill="y")
        self.export_btn = ttk.Button(rframe, text="导出结果 CSV…", command=self.export_results,
                                     state="disabled")
        self.export_btn.pack(side="bottom", anchor="e", pady=(4, 0))

        # 右：算法对比
        cframe = ttk.LabelFrame(bottom, text="算法对比（同一组任务）", padding=6)
        cframe.pack(side="right", fill="both", expand=True, padx=(8, 0))
        ccols = ("alg", "q", "avg_t", "avg_w", "avg_r")
        self.cmp_tree = ttk.Treeview(cframe, columns=ccols, show="headings", height=5)
        cheaders = {"alg": "算法", "q": "时间片", "avg_t": "平均周转", "avg_w": "平均等待",
                    "avg_r": "平均响应"}
        for c in ccols:
            self.cmp_tree.heading(c, text=cheaders[c])
            self.cmp_tree.column(c, width=100, anchor="center")
        self.cmp_tree.pack(side="left", fill="both", expand=True)
        cvsb = ttk.Scrollbar(cframe, orient="vertical", command=self.cmp_tree.yview)
        self.cmp_tree.configure(yscrollcommand=cvsb.set)
        cvsb.pack(side="right", fill="y")
        ttk.Button(cframe, text="运行对比", command=self.run_comparison_view).pack(
            side="bottom", anchor="e", pady=(4, 0))

    # ------------------------------------------------------------------ #
    # 任务表格刷新
    # ------------------------------------------------------------------ #
    def _refresh_task_table(self) -> None:
        """按任务列表重建表格，显示初始状态（未到达、剩余=运行时长）。"""
        tree = self.task_tree
        for iid in tree.get_children():
            tree.delete(iid)
        for t in self.tasks:
            tree.insert("", "end", iid=t.task_id, values=(
                t.task_id, t.name, t.arrival_time, t.burst_time, t.priority,
                t.burst_time, "未到达",
            ), tags=(STATE_TAG["未到达"],))

    def _apply_step(self, step) -> None:
        """将某个时间单位的状态快照反映到表格与状态区。"""
        for t in self.tasks:
            tid = t.task_id
            state = step.states.get(tid, "未到达")
            rem = step.remaining.get(tid, t.burst_time)
            self.task_tree.item(tid, values=(
                tid, t.name, t.arrival_time, t.burst_time, t.priority, rem, state,
            ), tags=(STATE_TAG[state],))
        self.time_var.set(str(step.time))
        self.run_var.set(step.running if step.running else "空闲")
        self.queue_var.set("、".join(step.ready) if step.ready else "（空）")
        self.event_var.set(" | ".join(step.events) if step.events else "")
        self._update_cursor(step.time)

    def _show_step(self, index: int) -> None:
        if self.result is None:
            return
        self.step_index = index
        self._apply_step(self.result.steps[index])

    # ------------------------------------------------------------------ #
    # 甘特图绘制
    # ------------------------------------------------------------------ #
    def _redraw_gantt(self) -> None:
        if self.result is None:
            self.gantt.delete("all")
            return
        self._draw_gantt(self.result)
        self._update_cursor(self.result.steps[self.step_index].time)

    def _draw_gantt(self, result: SimulationResult) -> None:
        c = self.gantt
        c.delete("all")
        w = max(c.winfo_width(), 200)
        left, right, top = 40, 20, 24
        bar_top, bar_h = 30, 44
        axis_y = bar_top + bar_h + 14
        plot_w = max(w - left - right, 10)
        total = max(result.total_time, 1)
        scale = plot_w / total
        self.gantt_scale, self.gantt_left, self.gantt_plot = scale, left, plot_w

        color_map = {t.task_id: TASK_COLORS[i % len(TASK_COLORS)]
                     for i, t in enumerate(self.tasks)}

        # 时间轴刻度
        c.create_line(left, axis_y, left + plot_w, axis_y, fill="#9ca3af")
        step = 1 if total <= 20 else (2 if total <= 40 else 5)
        for tick in range(0, total + 1, step):
            x = left + tick * scale
            c.create_line(x, axis_y, x, axis_y + 4, fill="#9ca3af")
            c.create_text(x, axis_y + 14, text=str(tick), font=("Consolas", 8),
                          fill="#4b5563")

        # 执行区间
        for seg in result.segments:
            x0 = left + seg.start * scale
            x1 = left + seg.end * scale
            if seg.task_id is None:
                fill = IDLE_COLOR
                label, text_color = "空闲", IDLE_TEXT
            else:
                fill = color_map[seg.task_id]
                label, text_color = seg.task_id, "#ffffff"
            c.create_rectangle(x0, bar_top, x1, bar_top + bar_h, fill=fill, outline="#ffffff")
            if x1 - x0 >= 24:
                c.create_text((x0 + x1) / 2, bar_top + bar_h / 2, text=label,
                              font=("Consolas", 9), fill=text_color)

    def _update_cursor(self, t: int) -> None:
        if not hasattr(self, "gantt_scale"):
            return
        c = self.gantt
        c.delete("cursor")
        x = self.gantt_left + t * self.gantt_scale
        c.create_line(x, 24, x, 24 + 44 + 14, fill="#ef4444", width=2, tags="cursor")
        c.create_text(x, 16, text=f"t={t}", fill="#ef4444", font=("Consolas", 9, "bold"),
                      tags="cursor")

    # ------------------------------------------------------------------ #
    # 调度引擎调用
    # ------------------------------------------------------------------ #
    def _run_engine(self) -> bool:
        """按当前设置运行引擎，填充甘特图与统计表。返回是否成功。"""
        errs = validate_tasks(self.tasks)
        if errs:
            messagebox.showerror("数据错误", "\n".join(errs))
            return False
        alg = self.algorithm_var.get()
        q = None
        if alg == ALGORITHM_RR:
            try:
                q = int(self.time_slice_var.get())
                if q <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("参数错误", "时间片必须为正整数")
                return False
        try:
            self.result = SimulationEngine(self.tasks, alg, q).run()
        except ValueError as e:
            messagebox.showerror("参数错误", str(e))
            return False
        self.step_index = 0
        self._draw_gantt(self.result)
        self._fill_result_table(self.result)
        self.export_btn.configure(state="normal")
        self._update_edit_state()
        return True

    def _fill_result_table(self, result: SimulationResult) -> None:
        tree = self.result_tree
        for iid in tree.get_children():
            tree.delete(iid)
        for r in result.task_results:
            tree.insert("", "end", values=(
                r.task_id, r.name, r.start_time, r.finish_time,
                r.turnaround, r.waiting, r.response,
            ))
        tree.insert("", "end", values=(
            "平均", "—", "—", "—",
            f"{result.avg_turnaround:.2f}", f"{result.avg_waiting:.2f}",
            f"{result.avg_response:.2f}",
        ), tags=("avgrow",))
        tree.tag_configure("avgrow", background="#eef2ff")

    # ------------------------------------------------------------------ #
    # 播放控制
    # ------------------------------------------------------------------ #
    def _delay_ms(self) -> int:
        return max(5, int(1000 / max(self.speed_var.get(), 0.5)))

    def start(self) -> None:
        if not self.tasks:
            messagebox.showwarning("提示", "请先添加或加载任务")
            return
        if not self._run_engine():
            return
        self._show_step(0)
        self.playing = True
        self._update_play_button()
        if self.step_index < len(self.result.steps) - 1:
            self.after_id = self.root.after(self._delay_ms(), self._tick)

    def _tick(self) -> None:
        if not self.playing or self.result is None:
            return
        if self.step_index < len(self.result.steps) - 1:
            self.step_index += 1
            self._show_step(self.step_index)
            self.after_id = self.root.after(self._delay_ms(), self._tick)
        else:
            self.playing = False
            self._update_play_button()

    def toggle_pause(self) -> None:
        if self.result is None:
            return
        self.playing = not self.playing
        if self.playing:
            self.after_id = self.root.after(self._delay_ms(), self._tick)
        else:
            if self.after_id:
                self.root.after_cancel(self.after_id)
                self.after_id = None
        self._update_play_button()

    def _update_play_button(self) -> None:
        self.play_btn.configure(text="暂停" if self.playing else "继续")
        self.play_btn.configure(state="normal" if self.result else "disabled")

    def step_once(self) -> None:
        if not self.tasks:
            messagebox.showwarning("提示", "请先添加或加载任务")
            return
        if self.result is None:
            if not self._run_engine():
                return
            self.step_index = -1
        if self.step_index < len(self.result.steps) - 1:
            self.step_index += 1
            self._show_step(self.step_index)

    def run_to_end(self) -> None:
        if not self.tasks:
            messagebox.showwarning("提示", "请先添加或加载任务")
            return
        if self.result is None:
            if not self._run_engine():
                return
        self.playing = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self._update_play_button()
        self._show_final()

    def _show_final(self) -> None:
        """展示模拟结束后的最终状态（所有任务完成）。"""
        if self.result is None:
            return
        for r in self.result.task_results:
            self.task_tree.item(r.task_id, values=(
                r.task_id, r.name, r.arrival_time, r.burst_time, r.priority, 0, "完成",
            ), tags=(STATE_TAG["完成"],))
        self.time_var.set(str(self.result.total_time))
        self.run_var.set("空闲")
        self.queue_var.set("（空）")
        self.event_var.set("模拟结束，所有任务完成")
        self._update_cursor(self.result.total_time)

    def reset_view(self) -> None:
        self.playing = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.result = None
        self.step_index = 0
        for t in self.tasks:
            t.reset()
        self._refresh_task_table()
        self.gantt.delete("all")
        self.time_var.set("0")
        self.run_var.set("空闲")
        self.queue_var.set("（空）")
        self.event_var.set("")
        self.result_tree.delete(*self.result_tree.get_children())
        self.cmp_tree.delete(*self.cmp_tree.get_children())
        self.export_btn.configure(state="disabled")
        self._update_edit_state()
        self._update_play_button()

    # ------------------------------------------------------------------ #
    # 任务管理
    # ------------------------------------------------------------------ #
    def _on_algorithm_change(self) -> None:
        state = "normal" if self.algorithm_var.get() == ALGORITHM_RR else "disabled"
        self.slice_spin.configure(state=state)

    def _update_edit_state(self) -> None:
        state = "disabled" if self.result is not None else "normal"
        self.load_btn.configure(state=state)
        self.add_btn.configure(state=state)
        self.edit_btn.configure(state=state)
        self.del_btn.configure(state=state)

    def load_file(self) -> None:
        path = filedialog.askopenfilename(
            title="加载任务数据", filetypes=[("数据文件", "*.csv *.json"), ("所有文件", "*.*")])
        if not path:
            return
        tasks, errs = load_tasks(path)
        if errs:
            messagebox.showerror("加载失败", "\n".join(errs))
            return
        self.tasks = tasks
        self.reset_view()
        self._refresh_task_table()

    def save_file(self) -> None:
        if not self.tasks:
            messagebox.showwarning("提示", "没有可保存的任务")
            return
        path = filedialog.asksaveasfilename(
            title="保存任务数据", defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("JSON 文件", "*.json")])
        if not path:
            return
        save_tasks(self.tasks, path)
        messagebox.showinfo("保存成功", f"任务已保存到：\n{path}")

    def add_task(self) -> None:
        task = self._task_dialog()
        if task is None:
            return
        self.tasks.append(task)
        self._refresh_task_table()

    def edit_task(self) -> None:
        sel = self.task_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在表格中选择要修改的任务")
            return
        tid = sel[0]
        task = next((t for t in self.tasks if t.task_id == tid), None)
        if task is None:
            return
        new_task = self._task_dialog(task)
        if new_task is None:
            return
        idx = self.tasks.index(task)
        self.tasks[idx] = new_task
        self._refresh_task_table()

    def delete_task(self) -> None:
        sel = self.task_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在表格中选择要删除的任务")
            return
        tid = sel[0]
        self.tasks = [t for t in self.tasks if t.task_id != tid]
        self._refresh_task_table()

    def _task_dialog(self, existing: Task | None = None) -> Task | None:
        """弹出添加/修改任务对话框，返回新任务对象（取消则返回 None）。"""
        win = tk.Toplevel(self.root)
        win.title("修改任务" if existing else "添加任务")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        fields = [
            ("编号", "task_id"), ("名称", "name"), ("到达时间", "arrival_time"),
            ("运行时长", "burst_time"), ("优先级", "priority"),
        ]
        entries: dict[str, ttk.Entry] = {}
        defaults = {
            "task_id": existing.task_id if existing else "",
            "name": existing.name if existing else "",
            "arrival_time": str(existing.arrival_time) if existing else "0",
            "burst_time": str(existing.burst_time) if existing else "1",
            "priority": str(existing.priority) if existing else "0",
        }
        for r, (label, key) in enumerate(fields):
            ttk.Label(win, text=label + "：").grid(row=r, column=0, sticky="e", padx=8, pady=4)
            e = ttk.Entry(win, width=22)
            e.insert(0, defaults[key])
            e.grid(row=r, column=1, sticky="w", padx=8, pady=4)
            entries[key] = e

        result: list[Task | None] = [None]

        def on_ok() -> None:
            task_id = entries["task_id"].get().strip()
            name = entries["name"].get().strip()
            try:
                arrival = int(entries["arrival_time"].get())
                burst = int(entries["burst_time"].get())
                priority = int(entries["priority"].get())
            except ValueError:
                messagebox.showerror("输入错误", "到达时间、运行时长、优先级必须为整数", parent=win)
                return
            candidate = Task(task_id, name, arrival, burst, priority)
            seen = {t.task_id for t in self.tasks if t is not existing}
            errs = []
            if not task_id:
                errs.append("任务编号不能为空")
            elif task_id in seen:
                errs.append(f"任务编号重复：{task_id}")
            if not name:
                errs.append("任务名称不能为空")
            if arrival < 0:
                errs.append("到达时间必须为非负整数")
            if burst <= 0:
                errs.append("运行时长必须为正整数")
            if priority < 0:
                errs.append("优先级必须为非负整数")
            if errs:
                messagebox.showerror("输入错误", "\n".join(errs), parent=win)
                return
            result[0] = candidate
            win.destroy()

        btns = ttk.Frame(win)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=10)
        ttk.Button(btns, text="确定", command=on_ok).pack(side="left", padx=8)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="left", padx=8)

        win.bind("<Return>", lambda e: on_ok())
        win.bind("<Escape>", lambda e: win.destroy())
        win.wait_window()
        return result[0]

    # ------------------------------------------------------------------ #
    # 结果导出与对比
    # ------------------------------------------------------------------ #
    def export_results(self) -> None:
        if self.result is None:
            return
        path = filedialog.asksaveasfilename(
            title="导出统计结果", defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        save_results(self.result.task_results, path)
        messagebox.showinfo("导出成功", f"统计结果已导出到：\n{path}")

    def run_comparison_view(self) -> None:
        if not self.tasks:
            messagebox.showwarning("提示", "请先添加或加载任务")
            return
        errs = validate_tasks(self.tasks)
        if errs:
            messagebox.showerror("数据错误", "\n".join(errs))
            return
        tree = self.cmp_tree
        for iid in tree.get_children():
            tree.delete(iid)
        for res in run_comparison(self.tasks, [1, 4]):
            q = str(res.time_slice) if res.time_slice else "—"
            tree.insert("", "end", values=(
                res.algorithm, q,
                f"{res.avg_turnaround:.2f}", f"{res.avg_waiting:.2f}",
                f"{res.avg_response:.2f}",
            ))
        messagebox.showinfo("对比完成", "三种算法（含 RR 时间片 1 与 4）对比结果已显示。\n"
                            "可在左侧选择算法并点击“开始”查看对应甘特图。")


def main() -> None:
    app = TaskSchedulerApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
