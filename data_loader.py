"""任务数据加载 / 保存模块

支持两种数据格式：
- CSV：任务书示例格式，首行为表头 `task_id,name,arrival_time,burst_time,priority`，
  后续每行一个任务，字段顺序与表头一致（数值字段自动转整数）。
- JSON：结构化格式，便于程序之间交换。

示例（CSV）：
    task_id,name,arrival_time,burst_time,priority
    T1,任务A,0,5,2
    T2,任务B,1,3,1

示例（JSON）：
    {
      "tasks": [
        {"task_id": "T1", "name": "任务A", "arrival_time": 0, "burst_time": 5, "priority": 2}
      ]
    }

加载时会逐条校验，并返回任务列表与错误信息；任何一条不合法都不会被静默忽略。
"""

from __future__ import annotations

import csv
import json

from task import Task, validate_tasks


def load_tasks(path: str) -> tuple[list[Task], list[str]]:
    """根据扩展名加载任务文件，返回 (任务列表, 错误信息列表)。"""
    if path.lower().endswith(".json"):
        return load_json(path)
    return load_csv(path)


def load_csv(path: str) -> tuple[list[Task], list[str]]:
    tasks: list[Task] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                tasks.append(Task(
                    task_id=str(row["task_id"]).strip(),
                    name=str(row["name"]).strip(),
                    arrival_time=int(row["arrival_time"]),
                    burst_time=int(row["burst_time"]),
                    priority=int(row.get("priority", 0) or 0),
                ))
            except (KeyError, ValueError) as e:
                return [], [f"CSV 解析失败（{row}）：{e}"]
    return tasks, validate_tasks(tasks)


def load_json(path: str) -> tuple[list[Task], list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    tasks: list[Task] = []
    try:
        for item in data["tasks"]:
            tasks.append(Task(
                task_id=str(item["task_id"]).strip(),
                name=str(item["name"]).strip(),
                arrival_time=int(item["arrival_time"]),
                burst_time=int(item["burst_time"]),
                priority=int(item.get("priority", 0)),
            ))
    except (KeyError, TypeError, ValueError) as e:
        return [], [f"JSON 解析失败：{e}"]
    return tasks, validate_tasks(tasks)


def save_tasks(tasks: list[Task], path: str) -> None:
    """将任务列表保存为 CSV 或 JSON（按扩展名）。"""
    if path.lower().endswith(".json"):
        data = {"tasks": [
            {
                "task_id": t.task_id,
                "name": t.name,
                "arrival_time": t.arrival_time,
                "burst_time": t.burst_time,
                "priority": t.priority,
            }
            for t in tasks
        ]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["task_id", "name", "arrival_time", "burst_time", "priority"])
            for t in tasks:
                writer.writerow([t.task_id, t.name, t.arrival_time, t.burst_time, t.priority])


def save_results(results: list, path: str) -> None:
    """将调度统计结果导出为 CSV。

    results 为 TaskResult 列表（顺序与任务输入顺序一致）。
    """
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "task_id", "name", "arrival_time", "burst_time", "priority",
            "start_time", "finish_time", "turnaround", "waiting", "response",
        ])
        for r in results:
            writer.writerow([
                r.task_id, r.name, r.arrival_time, r.burst_time, r.priority,
                r.start_time, r.finish_time, r.turnaround, r.waiting, r.response,
            ])
