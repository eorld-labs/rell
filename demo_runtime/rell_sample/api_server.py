from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from runtime_core import (
    MockRobotAdapter,
    P016Runtime,
    SerialEventQueue,
    read_json,
    run_runtime_sample,
    run_simulated_runtime_sample,
)


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8876

TIMELINE_SCENARIOS = {
    "success": "mock_timeline_success.json",
    "no_flow": "mock_timeline_no_flow.json",
    "channel_conflict": "mock_timeline_channel_conflict.json",
}
SIMULATED_SCENARIOS = {"simulated_success", "simulated_no_water", "simulated_channel_conflict"}
SCENARIOS = {**TIMELINE_SCENARIOS, **{name: name for name in SIMULATED_SCENARIOS}}

AUDIT_STORE: dict[str, dict[str, Any]] = {}
STATE_STORE: dict[str, dict[str, Any]] = {}
TRACE_STORE: dict[str, dict[str, Any]] = {}


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RELL 真实世界经验引擎样品</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172026;
      --muted: #5d6872;
      --line: #d8dee4;
      --surface: #ffffff;
      --band: #f4f7f8;
      --accent: #1f7a64;
      --warn: #a15c10;
      --bad: #a33636;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background: var(--band);
    }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0;
      display: grid;
      gap: 16px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 14px;
    }
    h1 { margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0; }
    .status-pill {
      min-width: 132px;
      height: 34px;
      border: 1px solid var(--line);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--surface);
      font-size: 14px;
    }
    section {
      background: var(--surface);
      border: 1px solid var(--line);
      padding: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 16px;
      align-items: start;
    }
    label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
    textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      color: var(--ink);
      background: #fff;
      font: inherit;
    }
    textarea {
      min-height: 92px;
      resize: vertical;
      padding: 10px;
      line-height: 1.5;
    }
    select {
      height: 38px;
      padding: 0 10px;
      margin-bottom: 12px;
    }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    button {
      height: 38px;
      border: 1px solid var(--ink);
      background: var(--ink);
      color: #fff;
      font: inherit;
      cursor: pointer;
    }
    button.secondary {
      background: #fff;
      color: var(--ink);
      border-color: var(--line);
    }
    button:disabled {
      opacity: .55;
      cursor: wait;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      padding: 10px;
      min-height: 68px;
      background: #fbfcfd;
    }
    .metric span { display: block; color: var(--muted); font-size: 12px; }
    .metric strong { display: block; margin-top: 5px; font-size: 16px; overflow-wrap: anywhere; }
    .runtime {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .log, .facts {
      border: 1px solid var(--line);
      min-height: 360px;
      max-height: 520px;
      overflow: auto;
      background: #0f171b;
      color: #d8efe8;
      padding: 12px;
      font: 13px/1.55 Consolas, "Microsoft YaHei", monospace;
      white-space: pre-wrap;
    }
    .facts {
      background: #fff;
      color: var(--ink);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
    }
    .stage-row {
      border-bottom: 1px solid var(--line);
      padding: 10px 0;
      display: grid;
      gap: 4px;
    }
    .stage-row:last-child { border-bottom: 0; }
    .stage-row strong { font-size: 14px; }
    .stage-row span { color: var(--muted); font-size: 13px; }
    .ok { color: var(--accent); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    @media (max-width: 860px) {
      .grid, .runtime { grid-template-columns: 1fr; }
      .summary { grid-template-columns: 1fr 1fr; }
      header { align-items: start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>RELL 真实世界经验引擎样品</h1>
      <div id="serviceState" class="status-pill">待运行</div>
    </header>
    <div class="grid">
      <section>
        <label for="utterance">任务输入</label>
        <textarea id="utterance">给客人倒一杯水</textarea>
        <label for="scenario">运行场景</label>
        <select id="scenario">
          <option value="simulated_success">模拟执行体：成功倒水</option>
          <option value="simulated_no_water">模拟执行体：壶内无水</option>
          <option value="simulated_channel_conflict">模拟执行体：双通道冲突</option>
          <option value="success">Mock剧本：成功倒水</option>
          <option value="no_flow">Mock剧本：无水流失败</option>
          <option value="channel_conflict">Mock剧本：双通道冲突</option>
        </select>
        <div class="actions">
          <button id="runButton" title="运行过程实例">▶ 运行</button>
          <button id="clearButton" class="secondary" title="清空当前日志">清空</button>
        </div>
      </section>
      <section>
        <div class="summary">
          <div class="metric"><span>准入</span><strong id="admitMetric">-</strong></div>
          <div class="metric"><span>阶段状态</span><strong id="stateMetric">-</strong></div>
          <div class="metric"><span>运行结果</span><strong id="outcomeMetric">-</strong></div>
          <div class="metric"><span>任务</span><strong id="taskMetric">-</strong></div>
        </div>
        <div class="runtime">
          <div id="log" class="log"></div>
          <div id="facts" class="facts"></div>
        </div>
      </section>
    </div>
  </main>
  <script>
    const runButton = document.getElementById("runButton");
    const clearButton = document.getElementById("clearButton");
    const logEl = document.getElementById("log");
    const factsEl = document.getElementById("facts");
    const serviceState = document.getElementById("serviceState");
    const admitMetric = document.getElementById("admitMetric");
    const stateMetric = document.getElementById("stateMetric");
    const outcomeMetric = document.getElementById("outcomeMetric");
    const taskMetric = document.getElementById("taskMetric");

    const eventLabel = {
      stage_started: "阶段启动",
      state_update: "连续状态变量更新",
      observation_update: "目标因果事实观测",
      failure_event: "失败事件",
      runtime_failure: "Runtime 失败"
    };

    function setText(node, value, className = "") {
      node.textContent = value;
      node.className = className;
    }

    function appendLog(line) {
      logEl.textContent += line + "\\n";
      logEl.scrollTop = logEl.scrollHeight;
    }

    function clearView() {
      logEl.textContent = "";
      factsEl.innerHTML = "";
      setText(admitMetric, "-");
      setText(stateMetric, "-");
      setText(outcomeMetric, "-");
      setText(taskMetric, "-");
      serviceState.textContent = "待运行";
    }

    function describeTrace(event) {
      const label = eventLabel[event.trigger_reason] || event.trigger_reason;
      const payload = event.payload_summary ? " | " + event.payload_summary : "";
      return `[${String(event.consumed_sequence).padStart(2, "0")}] ${label} | ${event.before_state} -> ${event.after_state}${payload}`;
    }

    function renderFacts(result) {
      const audit = result.audit_summary;
      const stages = audit.stage_summary || [];
      const facts = audit.fact_summary || [];
      const rows = [];
      rows.push(`<div class="stage-row"><strong>阶段结果</strong><span>${stages.length ? "" : "暂无阶段摘要"}</span></div>`);
      for (const stage of stages) {
        rows.push(`<div class="stage-row"><strong>${stage.stage_id}: ${stage.result}</strong><span>${stage.notes || ""}</span></div>`);
      }
      rows.push(`<div class="stage-row"><strong>事实验真</strong><span>${facts.length ? "" : "暂无事实摘要"}</span></div>`);
      for (const fact of facts) {
        rows.push(`<div class="stage-row"><strong>${fact.fact_id}: ${fact.state}</strong><span>${fact.channel_notes || ""}</span></div>`);
      }
      if (audit.stop_reason) {
        rows.push(`<div class="stage-row"><strong>停止原因</strong><span>${audit.stop_reason}</span></div>`);
      }
      factsEl.innerHTML = rows.join("");
    }

    async function runProcess() {
      clearView();
      runButton.disabled = true;
      serviceState.textContent = "运行中";
      appendLog("接收任务：" + document.getElementById("utterance").value.trim());
      appendLog("执行准入检查...");
      try {
        const admit = await fetch("/process/admit", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(r => r.json());
        setText(admitMetric, admit.decision || "unknown", admit.allowed ? "ok" : "bad");
        appendLog("准入结果：" + JSON.stringify(admit, null, 2));
        if (!admit.allowed) {
          serviceState.textContent = "未准入";
          return;
        }

        const scenario = document.getElementById("scenario").value;
        appendLog("加载过程模板：pour_water");
        appendLog("绑定当前环境：home_a_kitchen_daytime");
        appendLog("启动场景：" + scenario);
        const result = await fetch("/process/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario, utterance: document.getElementById("utterance").value.trim() })
        }).then(r => r.json());

        setText(taskMetric, result.task_id || "-");
        setText(stateMetric, result.stage_runtime_state.runtime_state);
        const outcomeClass = result.audit_summary.outcome === "completed" ? "ok" : "warn";
        setText(outcomeMetric, result.audit_summary.outcome, outcomeClass);

        const events = result.execution_trace.events || [];
        for (const event of events) {
          await new Promise(resolve => setTimeout(resolve, 180));
          appendLog(describeTrace(event));
        }
        renderFacts(result);
        serviceState.textContent = result.audit_summary.outcome === "completed" ? "完成" : "等待人工确认";
      } catch (error) {
        serviceState.textContent = "异常";
        appendLog("运行异常：" + error.message);
      } finally {
        runButton.disabled = false;
      }
    }

    runButton.addEventListener("click", runProcess);
    clearButton.addEventListener("click", clearView);
    clearView();
  </script>
</body>
</html>
"""


def admit_process() -> dict[str, Any]:
    queue = SerialEventQueue()
    process_instance = read_json(DATA / "pour_water_process_instance.json")
    initial_state = read_json(DATA / "stage_runtime_state_initial.json")
    timeline = read_json(DATA / "mock_timeline_success.json")
    adapter = MockRobotAdapter(timeline, queue)
    runtime = P016Runtime(process_instance, initial_state, adapter)
    return runtime.admit()


def run_process(scenario: str = "success") -> dict[str, Any]:
    if scenario not in SCENARIOS:
        return {
            "error": "unknown_scenario",
            "allowed_scenarios": sorted(SCENARIOS),
        }
    if scenario in SIMULATED_SCENARIOS:
        result = run_simulated_runtime_sample(DATA, scenario)
    else:
        result = run_runtime_sample(DATA, TIMELINE_SCENARIOS[scenario])
    task_id = result["audit_summary"]["task_id"]
    AUDIT_STORE[task_id] = result["audit_summary"]
    STATE_STORE[task_id] = result["stage_runtime_state"]
    TRACE_STORE[task_id] = result["execution_trace"]
    return {
        "task_id": task_id,
        "scenario": scenario,
        "audit_summary": result["audit_summary"],
        "stage_runtime_state": result["stage_runtime_state"],
        "execution_trace": result["execution_trace"],
    }


def get_audit(task_id: str) -> dict[str, Any]:
    audit = AUDIT_STORE.get(task_id)
    if not audit:
        return {"error": "audit_not_found", "task_id": task_id}
    return audit


def get_status(task_id: str) -> dict[str, Any]:
    state = STATE_STORE.get(task_id)
    if not state:
        return {"error": "status_not_found", "task_id": task_id}
    return state


class RellSampleHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._send_html(INDEX_HTML)
            return
        if path == "/health":
            self._send_json({"status": "ok", "service": "rell_sample"})
            return
        if path.startswith("/audit/"):
            task_id = path.removeprefix("/audit/")
            self._send_json(get_audit(task_id), status=200 if task_id in AUDIT_STORE else 404)
            return
        if path.startswith("/process/status/"):
            task_id = path.removeprefix("/process/status/")
            self._send_json(get_status(task_id), status=200 if task_id in STATE_STORE else 404)
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()
        if path == "/process/admit":
            self._send_json(admit_process())
            return
        if path == "/process/run":
            result = run_process(body.get("scenario", "success"))
            self._send_json(result, status=400 if "error" in result else 200)
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_html(self, html: str, status: int = 200) -> None:
        encoded = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    server = HTTPServer((DEFAULT_HOST, DEFAULT_PORT), RellSampleHandler)
    print(f"RELL sample API listening on http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    print(f"Demo page: http://{DEFAULT_HOST}:{DEFAULT_PORT}/")
    print("Endpoints: POST /process/admit, POST /process/run, GET /audit/{task_id}")
    server.serve_forever()


if __name__ == "__main__":
    main()
