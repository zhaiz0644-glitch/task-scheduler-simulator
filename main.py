"""任务调度模拟器 —— 程序入口

运行方式：
    python main.py                            # 启动空界面，手动添加/加载任务
    python main.py data/example.csv           # 启动并加载任务书示例数据
    python main.py data/<任意 .csv 或 .json>   # 启动并加载指定数据文件

依赖：仅使用 Python 标准库（tkinter、heapq、csv、json、dataclasses 等），无需额外安装。
"""

from __future__ import annotations

import os
import sys

from data_loader import load_tasks
from ui import TaskSchedulerApp


def main() -> None:
    app = TaskSchedulerApp()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        if not os.path.exists(path):
            print(f"未找到数据文件：{path}")
        else:
            tasks, errs = load_tasks(path)
            if errs:
                print("加载失败：")
                for e in errs:
                    print(" -", e)
            else:
                app.tasks = tasks
                app._refresh_task_table()

    app.root.mainloop()


if __name__ == "__main__":
    main()
