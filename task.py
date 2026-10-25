"""任务模型模块（Task）

将一个待调度的任务抽象为包含以下属性的数据对象：

- task_id       任务编号，唯一，不允许重复
- name          任务名称，非空字符串
- arrival_time  到达时间，非负整数，任务进入系统的时刻
- burst_time    运行时长，正整数，任务完成所需的处理时间
- priority      优先级，非负整数，数值越大优先级越高
- remaining_time 剩余运行时间，初始值等于 burst_time
- state         任务状态：未到达 / 就绪 / 运行中 / 完成

任务书统一规定：
- 到达时间相同时，按数据输入顺序处理（用 index 记录输入顺序）。
- 优先级相同时，按到达时间与输入顺序决定执行顺序。

本模块只描述“任务是什么”，不含任何调度逻辑，便于与调度引擎解耦。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskState(str, Enum):
    """任务所处阶段。任务书给出的三态（未到达/就绪/完成）之外，
    为便于界面展示“正在执行的任务”，补充“运行中”这一瞬时状态。"""

    NOT_ARRIVED = "未到达"
    READY = "就绪"
    RUNNING = "运行中"
    FINISHED = "完成"


@dataclass
class Task:
    """一个待调度的任务。"""

    task_id: str
    name: str
    arrival_time: int
    burst_time: int
    priority: int = 0

    # ---- 运行期字段（由调度引擎维护，reset 时恢复） ----
    index: int = field(default=0, init=False)          # 输入顺序，用于稳定排序
    remaining_time: int = field(default=0, init=False)  # 剩余运行时间
    state: TaskState = field(default=TaskState.NOT_ARRIVED, init=False)
    start_time: int | None = field(default=None, init=False)   # 首次开始时间 S_i
    finish_time: int | None = field(default=None, init=False)  # 完成时间 C_i

    def __post_init__(self) -> None:
        self.remaining_time = self.burst_time

    def reset(self) -> None:
        """恢复初始状态，保证多次运行结果一致。"""
        self.remaining_time = self.burst_time
        self.state = TaskState.NOT_ARRIVED
        self.start_time = None
        self.finish_time = None

    # ---- 统计指标（未完成时为 None） ----

    @property
    def turnaround(self) -> int | None:
        """周转时间 T = C - A。"""
        if self.finish_time is None:
            return None
        return self.finish_time - self.arrival_time

    @property
    def waiting(self) -> int | None:
        """等待时间 W = T - B。"""
        t = self.turnaround
        if t is None:
            return None
        return t - self.burst_time

    @property
    def response(self) -> int | None:
        """响应时间 R = S - A。"""
        if self.start_time is None:
            return None
        return self.start_time - self.arrival_time


def validate_task(task: Task, seen_ids: set[str]) -> list[str]:
    """校验单个任务的合法性，返回错误信息列表（空列表表示合法）。

    校验规则（对应任务书“检查重复编号、负数时间、零运行时长等非法输入”）：
    - task_id 非空且不重复
    - name 非空
    - arrival_time 为非负整数
    - burst_time 为正整数
    - priority 为非负整数
    """
    errors: list[str] = []
    if not task.task_id or not str(task.task_id).strip():
        errors.append("任务编号不能为空")
    elif task.task_id in seen_ids:
        errors.append(f"任务编号重复：{task.task_id}")
    if not task.name or not str(task.name).strip():
        errors.append(f"任务 {task.task_id} 的名称不能为空")
    if not isinstance(task.arrival_time, int) or task.arrival_time < 0:
        errors.append(f"任务 {task.task_id} 的到达时间必须为非负整数")
    if not isinstance(task.burst_time, int) or task.burst_time <= 0:
        errors.append(f"任务 {task.task_id} 的运行时长必须为正整数")
    if not isinstance(task.priority, int) or task.priority < 0:
        errors.append(f"任务 {task.task_id} 的优先级必须为非负整数")
    return errors


def validate_tasks(tasks: list[Task]) -> list[str]:
    """批量校验任务列表，返回全部错误信息（去重）。"""
    errors: list[str] = []
    seen: set[str] = set()
    for t in tasks:
        errors.extend(validate_task(t, seen))
        seen.add(t.task_id)
    return errors
