"""调度引擎模块（Scheduler / SimulationEngine）

实现三种核心调度算法，统一采用**逐时间单位模拟**（每推进一个时间单位，就处理一次
到达事件、一次调度决策，并记录一帧状态快照）：

- FCFS   先来先服务：FIFO 队列，后到达的任务不能插队，任务开始后执行到完成。
- PRIO   非抢占式优先级调度：每次从就绪任务中选择优先级最高者执行到完成；
         高优先级任务到达时不中断正在运行的任务（非抢占）。
- RR     时间片轮转：按队列顺序分配时间片 q，未完成任务重新进入队尾。

RR 边界规则（严格遵循任务书）：
- 时间片内新到达的任务按到达顺序进入队尾；
- 恰好在时间片结束时到达的任务，**先入队**，再将未完成的当前任务放回队尾。
  实现方式：在每个时间单位边界先处理到达，再判断“时间片是否耗尽”，从而保证
  新到达任务排在刚被换下的当前任务之前。

复杂度（设任务数为 n，总运行时长 B = Σ burst_time，模拟总时长 M ≈ B + 空闲）：
- FCFS：每次取队首 O(1)，入队 O(1)；总时间 O(M)，空间 O(n)。
- 优先级调度：每次用线性扫描选取最高优先级 O(n)；总时间 O(M·n)，空间 O(n)。
  若改用二叉堆则选取为 O(log n)，但需额外处理同优先级稳定排序。
- RR：每时间单位一次队首出队 + 队尾入队 O(1)；总时间 O(M)，空间 O(n)。

所有结果仅由任务数据、算法与时间片决定，与界面动画速度无关。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from task import Task, TaskState


@dataclass
class Step:
    """一个时间单位开始时刻的系统状态快照。"""

    time: int                      # 当前模拟时刻 t（执行 [t, t+1) 之前）
    running: str | None            # 正在运行的任务编号，None 表示空闲
    ready: list[str]               # 就绪队列（按调度顺序）
    states: dict[str, str]         # 各任务在此刻的状态（字符串，便于界面直接展示）
    remaining: dict[str, int]      # 各任务在此刻的剩余运行时间
    events: list[str] = field(default_factory=list)  # 本时刻边界发生的事件描述


@dataclass
class Segment:
    """甘特图中的一个连续执行区间（相邻同任务/空闲区间合并而成）。"""

    start: int
    end: int
    task_id: str | None            # None 表示处理器空闲区间


@dataclass
class TaskResult:
    """单个任务完成后的统计结果。"""

    task_id: str
    name: str
    arrival_time: int
    burst_time: int
    priority: int
    start_time: int
    finish_time: int
    turnaround: int
    waiting: int
    response: int


@dataclass
class SimulationResult:
    """一次完整模拟的全部输出。"""

    algorithm: str                 # "FCFS" / "优先级" / "RR"
    time_slice: int | None         # 仅 RR 有效
    steps: list[Step]
    segments: list[Segment]
    task_results: list[TaskResult]
    avg_turnaround: float
    avg_waiting: float
    avg_response: float
    total_time: int


ALGORITHM_FCFS = "FCFS"
ALGORITHM_PRIO = "优先级"
ALGORITHM_RR = "RR"

ALGORITHM_NAMES = {
    ALGORITHM_FCFS: "先来先服务（FCFS）",
    ALGORITHM_PRIO: "非抢占式优先级调度",
    ALGORITHM_RR: "时间片轮转（RR）",
}


class SimulationEngine:
    """任务调度仿真引擎，按指定算法与时间片预计算完整调度轨迹。

    采用“先算好、再演示”的方式：`run()` 一次性生成全部时间单位快照，
    界面只需按快照逐帧回放，因此动画速度不影响调度结果。
    """

    def __init__(self, tasks: list[Task], algorithm: str = ALGORITHM_FCFS,
                 time_slice: int | None = None) -> None:
        if algorithm not in ALGORITHM_NAMES:
            raise ValueError(f"未知算法: {algorithm}")
        if algorithm == ALGORITHM_RR and (time_slice is None or time_slice <= 0):
            raise ValueError("RR 算法必须设置正整数时间片")
        self.tasks = tasks
        self.algorithm = algorithm
        self.time_slice = time_slice

    # ------------------------------------------------------------------ #
    # 对外接口
    # ------------------------------------------------------------------ #
    def run(self) -> SimulationResult:
        """执行完整模拟，返回 SimulationResult。"""
        # 重置运行期状态，保证结果可复现
        for t in self.tasks:
            t.reset()
        for i, t in enumerate(self.tasks):
            t.index = i

        by_id = {t.task_id: t for t in self.tasks}
        order = list(self.tasks)            # 按输入顺序
        n = len(order)
        q = self.time_slice

        rem = {t.task_id: t.burst_time for t in order}
        finished: set[str] = set()
        ready: list[str] = []               # FIFO（FCFS/RR）；优先级调度按 key 选取
        running: str | None = None
        slice_used = 0

        steps: list[Step] = []
        t = 0

        while len(finished) < n:
            events: list[str] = []

            # 1. 到达事件：到达时间相同的任务按输入顺序依次入队
            for task in order:
                if task.arrival_time == t and task.task_id not in finished \
                        and task.task_id not in ready and task.task_id != running:
                    ready.append(task.task_id)
                    events.append(f"{task.task_id} 到达")

            # 2. RR 时间片耗尽：恰在此时刻到达的任务已先入队，再把当前任务放回队尾
            if (self.algorithm == ALGORITHM_RR and running is not None
                    and slice_used >= q and rem[running] > 0):
                ready.append(running)
                events.append(f"{running} 时间片耗尽，回到队尾")
                running = None

            # 3. 处理器空闲时，选取下一个任务
            if running is None and ready:
                if self.algorithm == ALGORITHM_PRIO:
                    running = self._pick_highest(ready, by_id)
                    ready.remove(running)
                else:
                    running = ready.pop(0)
                if by_id[running].start_time is None:
                    by_id[running].start_time = t   # 记录首次开始时间 S
                slice_used = 0

            # 4. 记录当前状态快照
            states = {task.task_id: self._state_of(task.task_id, finished, running, ready)
                      for task in order}
            steps.append(Step(t, running, list(ready), states, dict(rem), events))

            # 5. 执行一个时间单位 [t, t+1)
            if running is not None:
                rem[running] -= 1
                if self.algorithm == ALGORITHM_RR:
                    slice_used += 1
                if rem[running] == 0:
                    finished.add(running)
                    by_id[running].finish_time = t + 1   # 记录完成时间 C
                    running = None
            t += 1

        # 同步最终剩余时间到任务对象
        for task in order:
            task.remaining_time = rem[task.task_id]

        segments = self._build_segments(steps)
        task_results = [self._to_result(t) for t in order]
        avg_t, avg_w, avg_r = self._averages(task_results)

        return SimulationResult(
            algorithm=self.algorithm,
            time_slice=self.time_slice,
            steps=steps,
            segments=segments,
            task_results=task_results,
            avg_turnaround=avg_t,
            avg_waiting=avg_w,
            avg_response=avg_r,
            total_time=t,
        )

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def _pick_highest(ready: list[str], by_id: dict[str, Task]) -> str:
        """从就绪任务中选出优先级最高者。

        比较关键字为 (-priority, arrival_time, index)，取最小者，等价于：
        优先级数值大者优先；同优先级则先到达者优先；再相同则输入顺序靠前者优先。
        """
        best: str | None = None
        best_key = None
        for tid in ready:
            task = by_id[tid]
            key = (-task.priority, task.arrival_time, task.index)
            if best_key is None or key < best_key:
                best_key = key
                best = tid
        assert best is not None
        return best

    @staticmethod
    def _state_of(task_id: str, finished: set[str], running: str | None,
                  ready: list[str]) -> str:
        if task_id in finished:
            return TaskState.FINISHED.value
        if task_id == running:
            return TaskState.RUNNING.value
        if task_id in ready:
            return TaskState.READY.value
        return TaskState.NOT_ARRIVED.value

    @staticmethod
    def _build_segments(steps: list[Step]) -> list[Segment]:
        """把逐时间单位快照合并为连续区间，用于绘制甘特图。"""
        segments: list[Segment] = []
        cur: Segment | None = None
        for s in steps:
            if cur is None or cur.task_id != s.running:
                if cur is not None:
                    segments.append(cur)
                cur = Segment(s.time, s.time + 1, s.running)
            else:
                cur.end = s.time + 1
        if cur is not None:
            segments.append(cur)
        return segments

    @staticmethod
    def _to_result(task: Task) -> TaskResult:
        return TaskResult(
            task_id=task.task_id,
            name=task.name,
            arrival_time=task.arrival_time,
            burst_time=task.burst_time,
            priority=task.priority,
            start_time=task.start_time or 0,
            finish_time=task.finish_time or 0,
            turnaround=task.turnaround or 0,
            waiting=task.waiting or 0,
            response=task.response or 0,
        )

    @staticmethod
    def _averages(results: list[TaskResult]) -> tuple[float, float, float]:
        n = len(results) or 1
        avg_t = sum(r.turnaround for r in results) / n
        avg_w = sum(r.waiting for r in results) / n
        avg_r = sum(r.response for r in results) / n
        return avg_t, avg_w, avg_r


def run_comparison(tasks: list[Task],
                   time_slices: list[int] | None = None) -> list[SimulationResult]:
    """对同一组任务分别运行三种算法，并比较 RR 在不同时间片下的表现。

    每次运行前由引擎内部调用 reset() 恢复初始状态，保证比较公平。
    """
    results = [
        SimulationEngine(tasks, ALGORITHM_FCFS).run(),
        SimulationEngine(tasks, ALGORITHM_PRIO).run(),
    ]
    for q in (time_slices or [1, 4]):
        results.append(SimulationEngine(tasks, ALGORITHM_RR, q).run())
    return results
