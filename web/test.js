// 网页版算法自检：从 index.html 中提取内联 JS，在 Node 中运行纯函数部分。
// 校验 JS 调度引擎与桌面版 scheduler.py 结果一致（以任务书示例数据为准）。
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('未找到内联 script'); process.exit(1); }

const api = new Function(m[1] + '\n;return {simulate, runComparison, DATASETS};')();

function assert(cond, msg) {
  if (!cond) { console.error('FAIL: ' + msg); process.exit(1); }
  console.log('  ok - ' + msg);
}
function near(a, b) { return Math.abs(a - b) < 1e-9; }

// 任务书示例数据
const example = api.DATASETS.example.tasks;

// FCFS 预期（与任务书第 9 页一致）
const fcfs = api.simulate(example, 'FCFS', null);
assert(near(fcfs.avgTurnaround, 6.50) && near(fcfs.avgWaiting, 3.75),
  `FCFS 平均周转 ${fcfs.avgTurnaround} / 平均等待 ${fcfs.avgWaiting} === 6.50 / 3.75`);
const expect = { T1: [0, 5, 5, 0], T2: [5, 8, 7, 4], T3: [8, 9, 7, 6], T4: [9, 11, 7, 5] };
for (const r of fcfs.taskResults) {
  const [S, C, T, W] = expect[r.id];
  assert(r.start === S && r.finish === C && r.turnaround === T && r.waiting === W,
    `FCFS ${r.id} S=${r.start} C=${r.finish} T=${r.turnaround} W=${r.waiting}`);
}

// 优先级调度预期
const prio = api.simulate(example, '优先级', null);
assert(near(prio.avgTurnaround, 6.00) && near(prio.avgWaiting, 3.25),
  `优先级 平均周转 ${prio.avgTurnaround} / 平均等待 ${prio.avgWaiting} === 6.00 / 3.25`);
assert(prio.segments.map(s => s.task + '[' + s.start + ',' + s.end + ')').join(' ') ===
  'T1[0,5) T3[5,6) T2[6,9) T4[9,11)',
  '优先级 执行区间 T1[0,5) T3[5,6) T2[6,9) T4[9,11)');

// RR q=1 与 q=4 预期
const rr1 = api.simulate(example, 'RR', 1);
assert(near(rr1.avgTurnaround, 6.50) && near(rr1.avgResponse, 0.75),
  `RR(q=1) 平均周转 ${rr1.avgTurnaround} / 平均响应 ${rr1.avgResponse} === 6.50 / 0.75`);
const rr4 = api.simulate(example, 'RR', 4);
assert(near(rr4.avgTurnaround, 7.25), `RR(q=4) 平均周转 ${rr4.avgTurnaround} === 7.25`);

// 完备性：每个数据集都能跑通、所有任务完成、区间覆盖 [0, totalTime)
for (const key of Object.keys(api.DATASETS)) {
  const data = api.DATASETS[key];
  for (const cfg of [['FCFS', null], ['优先级', null], ['RR', 1], ['RR', 4]]) {
    const res = api.simulate(data.tasks, cfg[0], cfg[1]);
    assert(res.taskResults.length === data.tasks.length, `${key} ${cfg[0]}${cfg[1] || ''} 所有任务完成`);
    const seg = res.segments;
    assert(seg[0].start === 0 && seg[seg.length - 1].end === res.totalTime,
      `${key} ${cfg[0]}${cfg[1] || ''} 区间覆盖 [0,${res.totalTime})`);
    assert(res.steps.length === res.totalTime, `${key} ${cfg[0]}${cfg[1] || ''} 逐时间单位快照完整`);
  }
}

console.log('\n全部通过 ✅  JS 引擎与桌面版 scheduler.py 结果一致');
