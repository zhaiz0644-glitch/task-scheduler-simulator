"""算法自检脚本（无界面）

在开发界面之前，先在控制台用少量任务验证三种调度算法的正确性，
并与任务书给出的 FCFS 预期结果逐项核对。

运行方式（在项目根目录下）：
    python scripts/verify.py

预期 FCFS（任务书示例数据）：
    T1: 执行区间 [0,5)   周转 5  等待 0
    T2: 执行区间 [5,8)   周转 7  等待 4
    T3: 执行区间 [8,9)   周转 7  等待 6
    T4: 执行区间 [9,11)  周转 7  等待 5
    平均周转 6.50，平均等待 3.75
"""

from __future__ import annotations

import os
import sys

# 使脚本能以 `python scripts/verify.py` 方式导入项目根目录下的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task import Task
from scheduler import (
    ALGORITHM_FCFS,
    ALGORITHM_PRIO,
    ALGORITHM_RR,
    SimulationEngine,
    run_comparison,
)

EXAMPLE = [
    Task("T1", "任务A", 0, 5, 2),
    Task("T2", "任务B", 1, 3, 1),
    Task("T3", "任务C", 2, 1, 3),
    Task("T4", "任务D", 4, 2, 1),
]


def fmt_segments(res) -> str:
    parts = []
    for s in res.segments:
        label = s.task_id if s.task_id else "空闲"
        parts.append(f"{label}[{s.start},{s.end})")
    return " ".join(parts)


def show(res) -> None:
    print(f"\n===== {res.algorithm}"
          + (f" (时间片 q={res.time_slice})" if res.time_slice else "")
          + " =====")
    print("甘特区间:", fmt_segments(res))
    print(f"{'任务':<6}{'到达':<6}{'运行':<6}{'S':<4}{'C':<4}{'周转':<6}{'等待':<6}{'响应':<6}")
    for r in res.task_results:
        print(f"{r.task_id:<6}{r.arrival_time:<6}{r.burst_time:<6}"
              f"{r.start_time:<4}{r.finish_time:<4}"
              f"{r.turnaround:<6}{r.waiting:<6}{r.response:<6}")
    print(f"平均周转 {res.avg_turnaround:.2f}   平均等待 {res.avg_waiting:.2f}   平均响应 {res.avg_response:.2f}")


def check_fcfs() -> bool:
    res = SimulationEngine(EXAMPLE, ALGORITHM_FCFS).run()
    expect = {
        "T1": (0, 5, 5, 0),
        "T2": (5, 8, 7, 4),
        "T3": (8, 9, 7, 6),
        "T4": (9, 11, 7, 5),
    }
    ok = True
    for r in res.task_results:
        s, c, t, w = expect[r.task_id]
        if (r.start_time, r.finish_time, r.turnaround, r.waiting) != (s, c, t, w):
            ok = False
            print(f"[FAIL] {r.task_id}: 得到 (S={r.start_time},C={r.finish_time},"
                  f"T={r.turnaround},W={r.waiting})，预期 (S={s},C={c},T={t},W={w})")
    if abs(res.avg_turnaround - 6.5) > 1e-9 or abs(res.avg_waiting - 3.75) > 1e-9:
        ok = False
        print(f"[FAIL] 平均值不一致: 得到 T={res.avg_turnaround}, W={res.avg_waiting}，预期 6.5 / 3.75")
    return ok


def main() -> None:
    print("任务书示例数据：")
    for r in EXAMPLE:
        print(f"  {r.task_id} {r.name} 到达={r.arrival_time} 运行={r.burst_time} 优先级={r.priority}")

    if check_fcfs():
        print("\n[PASS] FCFS 结果与任务书预期完全一致。")

    show(SimulationEngine(EXAMPLE, ALGORITHM_FCFS).run())
    show(SimulationEngine(EXAMPLE, ALGORITHM_PRIO).run())
    show(SimulationEngine(EXAMPLE, ALGORITHM_RR, 1).run())
    show(SimulationEngine(EXAMPLE, ALGORITHM_RR, 4).run())

    print("\n===== 算法对比（平均指标）=====")
    for res in run_comparison(EXAMPLE, [1, 4]):
        label = res.algorithm + (f"(q={res.time_slice})" if res.time_slice else "")
        print(f"{label:<16} 平均周转 {res.avg_turnaround:>6.2f}   平均等待 {res.avg_waiting:>6.2f}   平均响应 {res.avg_response:>6.2f}")


if __name__ == "__main__":
    main()
