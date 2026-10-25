"""网页版构建脚本

将内置任务数据集注入模板 template.html，生成可直接双击打开的自包含网页 index.html。
之所以把数据内嵌进 HTML，是因为浏览器以 file:// 协议打开本地文件时，fetch() 读取
同目录 CSV/JSON 会被同源策略拦截；内嵌后无需任何服务器即可运行。

使用方法（在项目根目录下）：
    python web/build.py
"""

from __future__ import annotations

import csv
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE), "data")

# key -> (数据文件名, 显示名称)
DATASETS = {
    "example": ("example.csv", "任务书示例数据"),
    "same_arrival": ("same_arrival.csv", "同时到达"),
    "mixed": ("mixed.csv", "长短任务混合"),
    "priority_mix": ("priority_mix.csv", "优先级混合"),
    "idle_gap": ("idle_gap.csv", "存在空闲区间"),
}

PLACEHOLDER = "__DATASETS_JSON__"


def load_csv(path: str) -> list[dict]:
    tasks = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            tasks.append({
                "id": row["task_id"].strip(),
                "name": row["name"].strip(),
                "arrival": int(row["arrival_time"]),
                "burst": int(row["burst_time"]),
                "priority": int(row["priority"]),
            })
    return tasks


def main() -> None:
    with open(os.path.join(BASE, "template.html"), "r", encoding="utf-8") as f:
        html = f.read()

    bundled = {}
    for key, (filename, label) in DATASETS.items():
        bundled[key] = {"name": label, "tasks": load_csv(os.path.join(DATA_DIR, filename))}

    # JSON 序列化结果本身就是合法的 JavaScript 对象字面量
    blob = json.dumps(bundled, ensure_ascii=False)
    assert PLACEHOLDER in html, "模板中未找到占位符"
    html = html.replace(PLACEHOLDER, blob, 1)

    out = os.path.join(BASE, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(out) / 1024
    print(f"已生成：{out}")
    print(f"文件大小：{size_kb:.0f} KB")
    for key, data in bundled.items():
        print(f"  内置 {key}: {data['name']}（{len(data['tasks'])} 任务）")


if __name__ == "__main__":
    main()
