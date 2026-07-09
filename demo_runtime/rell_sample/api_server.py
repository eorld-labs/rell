from __future__ import annotations

import json
import os
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
DEFAULT_PORT = int(os.environ.get("RELL_SAMPLE_PORT", "8876"))
SPACE_PRIOR_FILE = DATA / "digital_kitchen_semantic_prior.json"
COGNITIVE_MODEL_FILE = DATA / "digital_kitchen_cognitive_model.json"

TIMELINE_SCENARIOS = {
    "success": "mock_timeline_success.json",
    "no_flow": "mock_timeline_no_flow.json",
    "channel_conflict": "mock_timeline_channel_conflict.json",
}
SIMULATED_SCENARIOS = {"simulated_success", "simulated_no_water", "simulated_channel_conflict"}
SCENARIOS = {**TIMELINE_SCENARIOS, **{name: name for name in SIMULATED_SCENARIOS}}

TASK_LIBRARY = {
    "pour_water": {
        "display_name": "倒水",
        "process_template": "pour_water",
        "default_scenario": "simulated_success",
        "required_bindings": ["CUP_OBJECT", "KETTLE_OBJECT", "CAMERA_SENSOR", "POUR_OPERATION_REGION", "WALKABLE_REGION"],
    }
}

PROCESS_CHAIN_KEYWORDS = [
    ("move_to_counter", ["走向操作台", "走到操作台", "到操作台", "去操作台"]),
    ("pick_up_cup", ["拿起杯子", "拿杯子", "取杯子", "抓取杯子"]),
    ("move_to_water_source", ["到水源", "去水源", "走到水源", "水源处"]),
    ("fill_cup_at_water_source", ["接一杯水", "接水", "装水", "取水"]),
    ("pour_water", ["倒水", "倒一杯水", "给客人倒水", "杯水"]),
]

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
    #taskMetric { font-size: 14px; line-height: 1.25; }
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
    .sim {
      border: 1px solid var(--line);
      margin-bottom: 14px;
      display: grid;
      grid-template-columns: minmax(260px, 1.1fr) minmax(220px, .9fr);
      min-height: 230px;
      background: #fbfcfd;
    }
    .scene {
      position: relative;
      overflow: hidden;
      min-height: 230px;
      border-right: 1px solid var(--line);
      background: linear-gradient(#f8fafb 0 72%, #eef3f1 72% 100%);
    }
    .counter {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 34px;
      height: 8px;
      background: #9aa5aa;
    }
    .kettle {
      position: absolute;
      width: 82px;
      height: 92px;
      left: 58px;
      bottom: 46px;
      transform-origin: 74px 82px;
      transform: translateX(var(--kettle-x, 0px)) rotate(var(--kettle-tilt, 0deg));
      transition: transform .18s linear;
    }
    .kettle-body {
      position: absolute;
      left: 8px;
      top: 22px;
      width: 58px;
      height: 58px;
      border: 3px solid #263238;
      background: #dfe8e7;
    }
    .kettle-spout {
      position: absolute;
      right: -4px;
      top: 36px;
      width: 28px;
      height: 10px;
      border-top: 3px solid #263238;
      transform: rotate(-8deg);
    }
    .kettle-handle {
      position: absolute;
      left: -2px;
      top: 36px;
      width: 18px;
      height: 30px;
      border: 3px solid #263238;
      border-right: 0;
    }
    .cup {
      position: absolute;
      left: 278px;
      bottom: 47px;
      width: 78px;
      height: 78px;
      border: 3px solid #263238;
      border-top: 0;
      background: #ffffff;
      overflow: hidden;
    }
    .cup-water {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: var(--water-level, 0%);
      background: #55a7b5;
      transition: height .18s linear;
    }
    .stream {
      position: absolute;
      left: var(--stream-x, 212px);
      top: 98px;
      width: 8px;
      height: var(--stream-height, 0px);
      background: #55a7b5;
      opacity: var(--stream-opacity, 0);
      transform: rotate(16deg);
      transform-origin: top center;
      transition: height .18s linear, opacity .12s linear;
    }
    .state-panel {
      padding: 12px;
      display: grid;
      gap: 8px;
      align-content: start;
    }
    .state-item {
      border-bottom: 1px solid var(--line);
      padding-bottom: 8px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 14px;
    }
    .state-item span { color: var(--muted); }
    .state-item strong { text-align: right; overflow-wrap: anywhere; }
    .space-map {
      position: relative;
      border: 1px solid var(--line);
      margin-bottom: 14px;
      min-height: 260px;
      background: #f9fbfa;
      overflow: hidden;
    }
    .map-region {
      position: absolute;
      border: 1px solid #7d8c88;
      background: rgba(255,255,255,.75);
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 6px;
      font-size: 12px;
      color: var(--ink);
    }
    .map-walkway { left: 10%; top: 45%; width: 76%; height: 33%; background: #eaf4ef; }
    .map-counter { left: 56%; top: 14%; width: 28%; height: 16%; background: #eef1f5; }
    .map-water { left: 18%; top: 14%; width: 20%; height: 16%; background: #e4f3f7; }
    .map-cup { left: 59%; top: 17%; width: 8%; height: 9%; background: #fff; border-width: 2px; }
    .map-service { left: 72%; top: 58%; width: 15%; height: 16%; border-radius: 999px; background: #fff8e8; }
    .map-door { left: 5%; top: 55%; width: 9%; height: 18%; background: #f4efe6; }
    .map-risk { left: 84%; top: 13%; width: 12%; height: 18%; background: #f9e7e5; border-color: #b66a61; color: #7e2e27; }
    .map-object {
      position: absolute;
      width: 18px;
      height: 18px;
      border: 2px solid #263238;
      background: #fff;
    }
    .map-kettle { left: 28%; top: 19%; }
    .map-sensor { left: 43%; top: 62%; border-radius: 999px; background: #172026; }
    .map-robot {
      position: absolute;
      width: 24px;
      height: 24px;
      border: 2px solid #172026;
      background: var(--accent);
      left: var(--robot-x, 28%);
      top: var(--robot-y, 60%);
      transform: translate(-50%, -50%);
      transition: left .24s linear, top .24s linear;
    }
    .map-path {
      position: absolute;
      left: 30%;
      top: 60%;
      width: 36%;
      height: 2px;
      border-top: 2px dashed #7c918a;
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
      .grid, .runtime, .sim { grid-template-columns: 1fr; }
      .scene { border-right: 0; border-bottom: 1px solid var(--line); }
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
          <option value="auto">自动：翻译层选择</option>
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
        <div class="sim">
          <div id="scene" class="scene">
            <div class="counter"></div>
            <div id="kettle" class="kettle">
              <div class="kettle-body"></div>
              <div class="kettle-spout"></div>
              <div class="kettle-handle"></div>
            </div>
            <div id="stream" class="stream"></div>
            <div class="cup"><div id="cupWater" class="cup-water"></div></div>
          </div>
          <div class="state-panel">
            <div class="state-item"><span>壶嘴距离</span><strong id="distanceValue">-</strong></div>
            <div class="state-item"><span>倾角</span><strong id="tiltValue">-</strong></div>
            <div class="state-item"><span>水流速度</span><strong id="flowValue">-</strong></div>
            <div class="state-item"><span>杯中液位</span><strong id="levelValue">-</strong></div>
            <div class="state-item"><span>验真状态</span><strong id="factValue">-</strong></div>
          </div>
        </div>
        <div id="spaceMap" class="space-map">
          <div class="map-region map-water">水源区</div>
          <div class="map-region map-counter">操作台</div>
          <div class="map-region map-walkway">可行动区</div>
          <div class="map-region map-cup">杯</div>
          <div class="map-region map-service">服务位</div>
          <div class="map-region map-door">门</div>
          <div class="map-region map-risk">风险区</div>
          <div class="map-path"></div>
          <div class="map-object map-kettle" title="object_kettle_steel_1l"></div>
          <div class="map-object map-sensor" title="sensor_depth_front"></div>
          <div id="mapRobot" class="map-robot" title="simulated_pouring_robot"></div>
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
    const scene = document.getElementById("scene");
    const distanceValue = document.getElementById("distanceValue");
    const tiltValue = document.getElementById("tiltValue");
    const flowValue = document.getElementById("flowValue");
    const levelValue = document.getElementById("levelValue");
    const factValue = document.getElementById("factValue");
    const mapRobot = document.getElementById("mapRobot");

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
      resetScene();
      serviceState.textContent = "待运行";
    }

    function resetScene() {
      scene.style.setProperty("--kettle-x", "0px");
      scene.style.setProperty("--kettle-tilt", "0deg");
      scene.style.setProperty("--water-level", "0%");
      scene.style.setProperty("--stream-height", "0px");
      scene.style.setProperty("--stream-opacity", "0");
      scene.style.setProperty("--stream-x", "212px");
      mapRobot.style.setProperty("--robot-x", "28%");
      mapRobot.style.setProperty("--robot-y", "60%");
      setText(distanceValue, "-");
      setText(tiltValue, "-");
      setText(flowValue, "-");
      setText(levelValue, "-");
      setText(factValue, "-");
    }

    function readPayloadValue(summary, name) {
      const match = summary.match(new RegExp(name + "=([0-9.\\-]+)"));
      return match ? Number(match[1]) : null;
    }

    function updateSceneFromEvent(event) {
      const summary = event.payload_summary || "";
      const distance = readPayloadValue(summary, "spout_to_cup_distance");
      if (distance !== null) {
        const x = Math.max(0, Math.min(145, (8 - distance) * 19));
        scene.style.setProperty("--kettle-x", `${x}px`);
        const robotX = Math.max(30, Math.min(63, 30 + (8 - distance) * 4.2));
        mapRobot.style.setProperty("--robot-x", `${robotX}%`);
        mapRobot.style.setProperty("--robot-y", "60%");
        setText(distanceValue, `${distance.toFixed(1)} cm`);
      }
      const tilt = readPayloadValue(summary, "tilt_angle");
      if (tilt !== null) {
        scene.style.setProperty("--kettle-tilt", `${tilt.toFixed(1)}deg`);
        setText(tiltValue, `${tilt.toFixed(1)}°`);
      }
      const flow = readPayloadValue(summary, "water_flow_rate");
      if (flow !== null) {
        scene.style.setProperty("--stream-height", flow > 0 ? "84px" : "0px");
        scene.style.setProperty("--stream-opacity", flow > 0 ? "1" : "0");
        if (flow > 0) {
          mapRobot.style.setProperty("--robot-x", "64%");
          mapRobot.style.setProperty("--robot-y", "36%");
        }
        setText(flowValue, `${flow.toFixed(1)} ml/s`);
      }
      const gap = readPayloadValue(summary, "water_surface_gap");
      if (gap !== null) {
        const level = Math.max(0, Math.min(86, (3 - gap) / 2.65 * 86));
        scene.style.setProperty("--water-level", `${level.toFixed(0)}%`);
        setText(levelValue, `gap ${gap.toFixed(2)} cm`);
      }
      if (summary.includes("cup_has_water")) {
        const value = summary.split("cup_has_water:")[1] || summary;
        setText(factValue, value.replace(" adapter=simulated_pouring_robot", ""));
      }
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
      if (result.intent_translation) {
        rows.push(`<div class="stage-row"><strong>翻译层</strong><span>${result.intent_translation.task_type}: ${result.intent_translation.reason}</span></div>`);
      }
      if (result.space_admission) {
        rows.push(`<div class="stage-row"><strong>空间准入</strong><span>${result.space_admission.decision}: ${result.space_admission.reason}</span></div>`);
      }
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
      const profile = result.admission_decision?.executor_profile;
      if (profile) {
        rows.push(`<div class="stage-row"><strong>执行体画像</strong><span>${profile.executor_type} / ${profile.body_profile} / ${profile.end_effector_type}</span></div>`);
        rows.push(`<div class="stage-row"><strong>空间约束预留</strong><span>${profile.spatial_entry_constraints?.body_envelope?.shape || "reserved"} envelope, P008 entry constraints reserved</span></div>`);
      }
      const space = result.space_context;
      if (space) {
        rows.push(`<div class="stage-row"><strong>数字空间</strong><span>${space.space_id} / ${space.cognitive_model_id}</span></div>`);
        rows.push(`<div class="stage-row"><strong>空间节点</strong><span>${space.region_count} regions, ${space.relation_count} relations, ${space.object_count} objects</span></div>`);
      }
      factsEl.innerHTML = rows.join("");
    }

    async function runProcess() {
      clearView();
      runButton.disabled = true;
      serviceState.textContent = "运行中";
      appendLog("接收任务：" + document.getElementById("utterance").value.trim());
      const utterance = document.getElementById("utterance").value.trim();
      appendLog("执行翻译层解析...");
      try {
        const translated = await fetch("/intent/translate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance })
        }).then(r => r.json());
        appendLog("翻译结果：" + JSON.stringify(translated, null, 2));
        appendLog("执行准入检查...");
        const admit = await fetch("/process/admit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ utterance })
        }).then(r => r.json());
        setText(admitMetric, admit.decision || "unknown", admit.allowed ? "ok" : "bad");
        appendLog("准入结果：" + JSON.stringify(admit, null, 2));

        const scenario = document.getElementById("scenario").value;
        if (admit.allowed) {
          appendLog("加载过程模板：pour_water");
          appendLog("绑定当前环境：home_a_kitchen_daytime");
        }
        appendLog("启动场景：" + scenario);
        const result = await fetch("/process/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario, utterance })
        }).then(r => r.json());

        setText(taskMetric, result.task_id || "-");
        setText(stateMetric, result.stage_runtime_state.runtime_state);
        const outcomeClass = result.audit_summary.outcome === "completed" ? "ok" : (result.audit_summary.outcome === "cannot_do" ? "bad" : "warn");
        setText(outcomeMetric, result.audit_summary.outcome, outcomeClass);

        const events = result.execution_trace.events || [];
        for (const event of events) {
          await new Promise(resolve => setTimeout(resolve, 180));
          appendLog(describeTrace(event));
          updateSceneFromEvent(event);
        }
        renderFacts(result);
        serviceState.textContent = result.audit_summary.outcome === "completed" ? "完成" : (result.audit_summary.outcome === "cannot_do" ? "不会做" : "等待人工确认");
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


def translate_intent(utterance: str) -> dict[str, Any]:
    text = (utterance or "").strip()
    if not text:
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "unknown",
            "decision": "unsupported",
            "reason": "空任务输入",
            "candidate_process": None,
        }
    detected_steps = detect_process_chain(text)
    has_sequence_marker = any(marker in text for marker in ["然后", "再", "接着", "之后", "，", ","])
    if len(detected_steps) > 1 or (has_sequence_marker and detected_steps and detected_steps != ["pour_water"]):
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "process_chain",
            "decision": "unsupported",
            "reason": "检测到多过程任务链，第一阶段仅支持单过程倒水，未执行以避免跳过前置动作",
            "candidate_process": None,
            "candidate_process_chain": detected_steps,
            "unsupported_steps": [step for step in detected_steps if step != "pour_water"],
        }
    if any(keyword in text for keyword in ["快递", "下楼", "电梯", "楼下"]):
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "long_chain_delivery",
            "decision": "unsupported",
            "reason": "长程多过程任务尚未进入第一阶段技能库",
            "candidate_process": None,
        }
    if any(keyword in text for keyword in ["炉灶", "火", "热源"]):
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "risk_area_action",
            "decision": "blocked",
            "reason": "任务涉及数字空间中的风险区域，第一阶段阻断执行",
            "candidate_process": None,
        }
    if any(keyword in text for keyword in ["倒水", "倒一杯水", "给客人倒水", "杯水"]):
        scenario = "simulated_success"
        if any(keyword in text for keyword in ["没水", "无水", "空壶"]):
            scenario = "simulated_no_water"
        if any(keyword in text for keyword in ["冲突", "看不清", "遮挡"]):
            scenario = "simulated_channel_conflict"
        return {
            "schema_version": "1.0.0",
            "utterance": text,
            "task_type": "pour_water",
            "decision": "executable",
            "reason": "命中第一阶段倒水技能",
            "candidate_process": "pour_water",
            "recommended_scenario": scenario,
            "goal_fact": "cup_has_water",
        }
    return {
        "schema_version": "1.0.0",
        "utterance": text,
        "task_type": "unknown",
        "decision": "unsupported",
        "reason": "技能库未匹配到可执行过程模板",
        "candidate_process": None,
    }


def detect_process_chain(text: str) -> list[str]:
    steps: list[tuple[int, str]] = []
    for step_id, keywords in PROCESS_CHAIN_KEYWORDS:
        positions = [text.find(keyword) for keyword in keywords if keyword in text]
        if positions:
            steps.append((min(positions), step_id))
    return [step_id for _, step_id in sorted(steps, key=lambda item: item[0])]


def evaluate_space_admission(intent: dict[str, Any], cognitive_model: dict[str, Any]) -> dict[str, Any]:
    if intent["decision"] != "executable":
        return {
            "allowed": False,
            "decision": intent["decision"],
            "reason": intent["reason"],
            "checks": [{"check_id": "intent_executable", "passed": False, "notes": intent["reason"]}],
        }
    task = TASK_LIBRARY[intent["task_type"]]
    bindings = cognitive_model.get("binding_candidates", {})
    object_index = cognitive_model.get("object_region_index", {})
    regions = {item["region_id"]: item for item in cognitive_model.get("space_region_table", [])}
    missing_bindings = [name for name in task["required_bindings"] if name not in bindings]
    required_objects = [bindings.get("CUP_OBJECT"), bindings.get("KETTLE_OBJECT"), bindings.get("CAMERA_SENSOR")]
    missing_objects = [item for item in required_objects if item and item not in object_index]
    required_regions = [bindings.get("POUR_OPERATION_REGION"), bindings.get("WALKABLE_REGION")]
    missing_regions = [item for item in required_regions if item and item not in regions]
    risk_regions = cognitive_model.get("risk_region_table", [])
    checks = [
        {"check_id": "intent_executable", "passed": True, "notes": intent["reason"]},
        {"check_id": "space_bindings_complete", "passed": not missing_bindings, "notes": ",".join(missing_bindings)},
        {"check_id": "objects_indexed", "passed": not missing_objects, "notes": ",".join(missing_objects)},
        {"check_id": "required_regions_available", "passed": not missing_regions, "notes": ",".join(missing_regions)},
        {"check_id": "risk_regions_known", "passed": True, "notes": f"{len(risk_regions)} risk region(s) guarded"},
    ]
    allowed = all(item["passed"] for item in checks)
    return {
        "allowed": allowed,
        "decision": "allowed" if allowed else "blocked",
        "reason": "空间上下文满足倒水过程准入" if allowed else "空间上下文缺失必要绑定",
        "checks": checks,
    }


def build_cannot_do_result(utterance: str, intent: dict[str, Any], space_admission: dict[str, Any]) -> dict[str, Any]:
    cognitive_model = get_cognitive_model()
    task_id = "task_unexecutable"
    return {
        "task_id": task_id,
        "scenario": "not_executed",
        "intent_translation": intent,
        "space_admission": space_admission,
        "admission_decision": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "allowed": False,
            "decision": "blocked" if intent["decision"] == "blocked" else "unsupported",
            "checks": space_admission["checks"],
            "missing_items": [intent["reason"]],
        },
        "audit_summary": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": "not_created",
            "outcome": "cannot_do",
            "stage_summary": [],
            "fact_summary": [],
            "stop_reason": intent["reason"],
        },
        "stage_runtime_state": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": "not_created",
            "current_stage_id": None,
            "runtime_state": "cannot_do",
            "utterance": utterance,
        },
        "execution_trace": {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "process_instance_id": "not_created",
            "events": [],
        },
        "space_context": build_space_context(cognitive_model),
    }


def admit_process(utterance: str = "给客人倒一杯水") -> dict[str, Any]:
    queue = SerialEventQueue()
    process_instance = read_json(DATA / "pour_water_process_instance.json")
    initial_state = read_json(DATA / "stage_runtime_state_initial.json")
    timeline = read_json(DATA / "mock_timeline_success.json")
    adapter = MockRobotAdapter(timeline, queue)
    runtime = P016Runtime(process_instance, initial_state, adapter)
    intent = translate_intent(utterance)
    cognitive_model = get_cognitive_model()
    space_admission = evaluate_space_admission(intent, cognitive_model)
    admission = runtime.admit()
    admission["intent_translation"] = intent
    admission["space_admission"] = space_admission
    if not space_admission["allowed"]:
        admission["allowed"] = False
        admission["decision"] = space_admission["decision"]
        admission["checks"].extend(space_admission["checks"])
        admission["missing_items"].append(space_admission["reason"])
    else:
        admission["checks"].extend(space_admission["checks"])
    return admission


def build_space_context(cognitive_model: dict[str, Any]) -> dict[str, Any]:
    return {
        "space_id": cognitive_model["local_environment_summary"]["space_id"],
        "cognitive_model_id": cognitive_model["cognitive_model_id"],
        "region_count": cognitive_model["local_environment_summary"]["region_count"],
        "relation_count": cognitive_model["local_environment_summary"]["relation_count"],
        "object_count": cognitive_model["local_environment_summary"]["object_count"],
        "binding_candidates": cognitive_model["binding_candidates"],
    }


def run_process(scenario: str = "success", utterance: str = "给客人倒一杯水") -> dict[str, Any]:
    intent = translate_intent(utterance)
    cognitive_model = get_cognitive_model()
    space_admission = evaluate_space_admission(intent, cognitive_model)
    if not space_admission["allowed"]:
        return build_cannot_do_result(utterance, intent, space_admission)
    if scenario == "auto":
        scenario = intent.get("recommended_scenario", "simulated_success")
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
        "intent_translation": intent,
        "space_admission": space_admission,
        "admission_decision": result["admission_decision"],
        "audit_summary": result["audit_summary"],
        "stage_runtime_state": result["stage_runtime_state"],
        "execution_trace": result["execution_trace"],
        "space_context": build_space_context(cognitive_model),
    }


def get_space_prior() -> dict[str, Any]:
    return read_json(SPACE_PRIOR_FILE)


def get_cognitive_model() -> dict[str, Any]:
    return read_json(COGNITIVE_MODEL_FILE)


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
        if path == "/space/prior":
            self._send_json(get_space_prior())
            return
        if path == "/space/cognitive-model":
            self._send_json(get_cognitive_model())
            return
        if path == "/skills":
            self._send_json({"schema_version": "1.0.0", "skills": TASK_LIBRARY})
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
        if path == "/intent/translate":
            intent = translate_intent(body.get("utterance", ""))
            cognitive_model = get_cognitive_model()
            self._send_json({"intent_translation": intent, "space_admission": evaluate_space_admission(intent, cognitive_model)})
            return
        if path == "/process/admit":
            self._send_json(admit_process(body.get("utterance", "给客人倒一杯水")))
            return
        if path == "/process/run":
            result = run_process(body.get("scenario", "success"), body.get("utterance", "给客人倒一杯水"))
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
