from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api_server import RellSampleHandler


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
EVIDENCE_ROOT = (
    REPO_ROOT / "技术库" / "P020-统一中间表示" / "证据包"
)
SCENARIOS = (
    "quality_profile_drift",
    "recovery_boundary_probe",
    "concept_promote",
    "concept_reject",
)
SOURCE_FILES = (
    "demo_runtime/rell_sample/api_server.py",
    "demo_runtime/rell_sample/cognitive_inquiry_service.py",
    "demo_runtime/rell_sample/concept_core/cognitive_inquiry.py",
    "demo_runtime/rell_sample/concept_core/cognitive_ir.py",
    "demo_runtime/rell_sample/concept_core/rcir_primitives.py",
    "demo_runtime/rell_sample/embodied_scene.py",
    "demo_runtime/rell_sample/embodied_home.html",
    "demo_runtime/rell_sample/validate_cognitive_inquiry_api.py",
    "demo_runtime/rell_sample/validate_rcir_stage_a_b.py",
    "demo_runtime/rell_sample/collect_rcir_evidence.py",
    "demo_runtime/rell_sample/docs/api_contract.md",
    "demo_runtime/rell_sample/docs/rcir_stage_a_b_engineering_evidence.md",
    "schemas/inquiry_contract.schema.json",
    "schemas/rcir_type_relations.json",
)


class QuietHandler(RellSampleHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_command(command: list[str]) -> dict[str, Any]:
    started = time.perf_counter_ns()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def git_text(*args: str) -> str:
    result = run_command(["git", *args])
    if result["exit_code"] != 0:
        raise RuntimeError(result["stderr"] or result["stdout"])
    return result["stdout"].strip()


def request_transaction(
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        base_url + path,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    started = time.perf_counter_ns()
    try:
        with urlopen(request, timeout=60) as response:
            status = response.status
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        status = error.code
        response_body = json.loads(error.read().decode("utf-8"))
    return {
        "request": {"method": method, "path": path, "body": body},
        "response": {"status_code": status, "body": response_body},
        "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_output_dir() -> tuple[Path, str, datetime]:
    now = datetime.now().astimezone()
    pack_id = "RCIR-阶段AB-认识目标闭环-" + now.strftime("%Y%m%d-%H%M%S")
    output = EVIDENCE_ROOT / pack_id
    suffix = 1
    while output.exists():
        output = EVIDENCE_ROOT / f"{pack_id}-{suffix:02d}"
        suffix += 1
    output.mkdir(parents=True)
    return output, output.name, now


def copy_source_snapshot(output: Path) -> list[dict[str, Any]]:
    records = []
    for relative in SOURCE_FILES:
        source = REPO_ROOT / relative
        if not source.exists():
            records.append({"path": relative, "status": "missing"})
            continue
        target = output / "源码快照" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append(
            {
                "path": relative,
                "status": "copied",
                "sha256": sha256_file(target),
                "size_bytes": target.stat().st_size,
            }
        )
    return records


def collect_validations(output: Path) -> list[dict[str, Any]]:
    commands = (
        [sys.executable, "demo_runtime/rell_sample/validate_cognitive_inquiry_api.py"],
        [sys.executable, "demo_runtime/rell_sample/validate_rcir_stage_a_b.py"],
        [sys.executable, "demo_runtime/rell_sample/validate_cognitive_ir.py"],
        [sys.executable, "demo_runtime/rell_sample/validate_simulated_robot_sample.py"],
        ["git", "diff", "--check"],
    )
    records = []
    for index, command in enumerate(commands, start=1):
        record = run_command(command)
        records.append(record)
        name = Path(command[-1]).stem if command[-1].endswith(".py") else "git_diff_check"
        write_text(
            output / "验证日志" / f"{index:02d}-{name}.txt",
            "COMMAND: "
            + subprocess.list2cmdline(command)
            + f"\nEXIT_CODE: {record['exit_code']}\nELAPSED_MS: {record['elapsed_ms']}\n\n"
            + record["stdout"]
            + ("\nSTDERR:\n" + record["stderr"] if record["stderr"] else ""),
        )
    return records


def main() -> None:
    output, pack_id, collected_at = create_output_dir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        catalog = request_transaction(base_url, "GET", "/cognitive/inquiry/catalog")
        write_json(output / "原始事务" / "01-认识目标目录.json", catalog)

        session_request = {
            "scene_id": "home_semantic_3d_a",
            "executor_profile_id": "home_humanoid",
        }
        initial = request_transaction(
            base_url, "POST", "/embodied/session/start", session_request
        )
        write_json(output / "原始事务" / "02-初始会话.json", initial)
        session = initial["response"]["body"]
        session_id = session["session_id"]
        write_json(
            output / "账本快照" / "01-运行前WorldFactLedger.json",
            session["world_fact_ledger"],
        )

        results: dict[str, dict[str, Any]] = {}
        for index, scenario in enumerate(SCENARIOS, start=3):
            transaction = request_transaction(
                base_url,
                "POST",
                "/cognitive/inquiry/run",
                {"session_id": session_id, "scenario": scenario},
            )
            write_json(
                output / "原始事务" / f"{index:02d}-{scenario}.json", transaction
            )
            results[scenario] = transaction["response"]["body"]

        final = request_transaction(
            base_url, "GET", f"/embodied/session/{session_id}"
        )
        write_json(output / "原始事务" / "07-最终会话.json", final)
        final_session = final["response"]["body"]
        write_json(
            output / "账本快照" / "02-运行后WorldFactLedger.json",
            final_session["world_fact_ledger"],
        )
        write_json(
            output / "账本快照" / "03-认识目标压缩历史.json",
            final_session["cognitive_inquiry_history"],
        )

        negative_controls = {
            "missing_session": request_transaction(
                base_url,
                "POST",
                "/cognitive/inquiry/run",
                {"session_id": "missing", "scenario": "quality_profile_drift"},
            ),
            "unknown_scenario": request_transaction(
                base_url,
                "POST",
                "/cognitive/inquiry/run",
                {"session_id": session_id, "scenario": "unknown"},
            ),
        }
        write_json(output / "原始事务" / "08-负向控制.json", negative_controls)

        with urlopen(base_url + "/embodied", timeout=30) as response:
            page = response.read().decode("utf-8")
        write_text(output / "界面证据" / "embodied页面响应.html", page)
        write_json(
            output / "界面证据" / "界面入口断言.json",
            {
                "http_status": 200,
                "inquiry_mode_present": 'id="inquiryMode"' in page,
                "run_button_present": 'id="runInquiry"' in page,
                "result_region_present": 'id="inquiryResult"' in page,
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    quality = results["quality_profile_drift"]
    recovery = results["recovery_boundary_probe"]
    promoted = results["concept_promote"]
    rejected = results["concept_reject"]
    summary = {
        "pack_id": pack_id,
        "session_id": session_id,
        "world_revision": session["world_revision"],
        "single_fact_authority": {
            "ledger_id": session["world_fact_ledger"]["ledger_id"],
            "all_responses_share_ledger": all(
                item["fact_authority_ref"]
                == session["world_fact_ledger"]["ledger_id"]
                for item in results.values()
            ),
            "all_planning_explanation_readbacks_match": all(
                all(item["shared_readback"].values()) for item in results.values()
            ),
        },
        "quality_profile_drift": {
            "diagnostic": quality["diagnostic_summary"],
            "hypotheses": quality["competing_hypotheses"],
            "selected": quality["selected_hypothesis"],
            "observation": quality["observation_or_probe_receipt"],
            "transitions": quality["transition_log"],
        },
        "recovery_boundary_probe": {
            "diagnostic": recovery["diagnostic_summary"],
            "hypotheses": recovery["competing_hypotheses"],
            "selected": recovery["selected_hypothesis"],
            "p018": recovery["p018_arbitration"],
            "p016": recovery["p016_runtime_receipt"],
        },
        "concept_validation": {
            "episode_count": promoted["diagnostic_summary"]["pattern_episode_count"],
            "promote": promoted["concept_decision"],
            "reject": rejected["concept_decision"],
            "distinct_inquiry_ids": promoted["inquiry_id"] != rejected["inquiry_id"],
        },
        "execution_boundary": {
            "all_p018_authorized": all(
                item["p018_arbitration"]["decision"] == "authorized"
                for item in results.values()
            ),
            "all_p016_referenced": all(
                item["p016_verification_ref"] == item["evidence_ref"]
                for item in results.values()
            ),
            "all_direct_execution_false": all(
                item["direct_execution_allowed"] is False
                for item in results.values()
            ),
            "all_runtime_fact_commit_false": all(
                item["runtime_fact_committed_by_inquiry"] is False
                for item in results.values()
            ),
        },
        "negative_controls": {
            "missing_session_status": negative_controls["missing_session"]["response"][
                "status_code"
            ],
            "unknown_scenario_status": negative_controls["unknown_scenario"][
                "response"
            ]["status_code"],
        },
    }
    write_json(output / "09-实施例关键事实摘要.json", summary)

    validations = collect_validations(output)
    validation_matrix = [
        {
            "command": subprocess.list2cmdline(item["command"]),
            "exit_code": item["exit_code"],
            "elapsed_ms": item["elapsed_ms"],
            "passed": item["exit_code"] == 0,
        }
        for item in validations
    ]
    write_json(output / "10-验证矩阵.json", validation_matrix)

    source_records = copy_source_snapshot(output)
    write_json(output / "源码状态" / "源码SHA256.json", source_records)
    tracked_sources = [path for path in SOURCE_FILES if (REPO_ROOT / path).exists()]
    patch_result = run_command(["git", "diff", "--binary", "--", *tracked_sources])
    write_text(output / "源码状态" / "当前工作区补丁.patch", patch_result["stdout"])
    scoped_status = git_text("status", "--short", "--", *tracked_sources)
    write_text(output / "源码状态" / "相关文件状态.txt", scoped_status + "\n")

    environment = {
        "pack_id": pack_id,
        "collected_at_asia_shanghai": collected_at.isoformat(),
        "collected_at_utc": collected_at.astimezone(timezone.utc).isoformat(),
        "repository_root": str(REPO_ROOT),
        "git_head": git_text("rev-parse", "HEAD"),
        "git_branch": git_text("branch", "--show-current"),
        "git_worktree_clean_for_evidence_sources": not bool(scoped_status),
        "python": sys.version,
        "platform": platform.platform(),
        "collection_mode": "local_ephemeral_http_server",
        "physical_hardware_used": False,
    }
    write_json(output / "11-采集环境.json", environment)

    reproduction = f"""# 在仓库根目录运行
python .\\demo_runtime\\rell_sample\\validate_cognitive_inquiry_api.py
python .\\demo_runtime\\rell_sample\\validate_rcir_stage_a_b.py
python .\\demo_runtime\\rell_sample\\validate_cognitive_ir.py
python .\\demo_runtime\\rell_sample\\validate_simulated_robot_sample.py
git diff --check

# 重新生成新的独立证据包
python .\\demo_runtime\\rell_sample\\collect_rcir_evidence.py
"""
    write_text(output / "12-复现命令.ps1", reproduction)

    index = f"""# RCIR 阶段 A/B 与认识目标闭环证据包

## 证据标识

- 证据包：`{pack_id}`
- 采集时间（Asia/Shanghai）：`{collected_at.isoformat()}`
- Git HEAD：`{environment['git_head']}`
- 当前实现包含未提交改动：`{str(not environment['git_worktree_clean_for_evidence_sources']).lower()}`
- 实际运行方式：本机临时 HTTP 服务，调用真实 API 处理链

## 可用于实施例的证据

1. `原始事务/03-quality_profile_drift.json`：质量均值从 0.72 漂移到 0.51、容差 0.08、三个竞争假设、主动观察和闭环迁移。
2. `原始事务/04-recovery_boundary_probe.json`：8 次窗口内 5 次同类恢复、P018 安全试验授权、P016 双通道验真和模板边界结论。
3. `原始事务/05-concept_promote.json` 与 `06-concept_reject.json`：相同认识方法在陌生实例上分别晋级和否决候选概念。
4. `账本快照/`：运行前后 WorldFactLedger 以及压缩认识历史，证明会话绑定和引用留存。
5. `09-实施例关键事实摘要.json`：从原始事务机械提取的核心事实，不能代替原始事务。
6. `源码状态/`：实际运行源码副本、每个文件 SHA-256、工作区补丁和 Git 基线。
7. `验证日志/` 与 `10-验证矩阵.json`：验证命令、退出码、耗时和原始标准输出。

## 完整性规则

- `SHA256SUMS.txt` 对证据包内除其自身外的文件逐项校验。
- 说明书引用时应同时引用原始事务、源码哈希和验证日志，不应只引用摘要。
- 原始事务保存请求、响应状态码、响应正文和本机耗时；摘要没有改写原始响应。

## 证据边界

- 本包证明的是本机软件实施例，不是真机实验记录。
- 恢复边界闭环实际调用仓库的 `run_simulated_runtime_sample(..., "simulated_success")`，P016 为模拟执行体双通道验真。
- 当前认识闭环由 API/UI 显式触发，尚未证明运行异常能够自动创建认识目标。
- 会话认识历史为内存态；本包通过最终会话响应将其固化到文件。
- 本包只覆盖 RCIR 阶段 A/B 和认识目标服务接入，不代表整个具身系统全量验收。
"""
    write_text(output / "00-证据索引.md", index)

    artifact_records = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            artifact_records.append(
                {
                    "path": path.relative_to(output).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "schema_version": "1.0.0",
        "pack_id": pack_id,
        "artifact_count_before_manifest": len(artifact_records),
        "artifacts": artifact_records,
        "integrity_algorithm": "SHA-256",
    }
    write_json(output / "13-证据清单.json", manifest)

    checksum_lines = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksum_lines.append(
                f"{sha256_file(path)}  {path.relative_to(output).as_posix()}"
            )
    write_text(output / "SHA256SUMS.txt", "\n".join(checksum_lines) + "\n")

    if not all(item["passed"] for item in validation_matrix):
        raise SystemExit(f"evidence collected but validation failed: {output}")
    print(json.dumps({"pack_id": pack_id, "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
