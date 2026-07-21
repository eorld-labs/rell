from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api_server import RellSampleHandler


ROOT = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def request_json(
    base_url: str, path: str, body: dict | None = None
) -> tuple[int, dict]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        base_url + path,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), RellSampleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, catalog = request_json(base_url, "/cognitive/inquiry/catalog")
        require(status == 200 and len(catalog["scenarios"]) == 4, str(catalog))
        require(catalog["direct_execution_allowed"] is False, str(catalog))

        status, session = request_json(
            base_url,
            "/embodied/session/start",
            {
                "scene_id": "home_semantic_3d_a",
                "executor_profile_id": "home_humanoid",
            },
        )
        require(status == 200 and session.get("session_id"), str(session))
        session_id = session["session_id"]
        results = {}
        for expected_count, scenario in enumerate(
            (
                "quality_profile_drift",
                "recovery_boundary_probe",
                "concept_promote",
                "concept_reject",
            ),
            start=1,
        ):
            status, result = request_json(
                base_url,
                "/cognitive/inquiry/run",
                {"session_id": session_id, "scenario": scenario},
            )
            require(status == 200, str(result))
            require(result["inquiry_status"] == "closed", str(result))
            require(result["direct_execution_allowed"] is False, str(result))
            require(result["runtime_fact_committed_by_inquiry"] is False, str(result))
            require(result["p018_arbitration"]["gateway"] == "P018", str(result))
            require(result["p016_verification_ref"] == result["evidence_ref"], str(result))
            require(all(result["shared_readback"].values()), str(result))
            require(
                result["session_binding_receipt"]["history_count"]
                == expected_count,
                str(result),
            )
            require(
                result["fact_authority_ref"]
                == result["session_binding_receipt"]["fact_authority_ref"],
                str(result),
            )
            results[scenario] = result

        channels = results["recovery_boundary_probe"]["p016_runtime_receipt"]
        require(
            channels["p016_outcome"] == "completed"
            and len(channels["channel_notes"]) >= 2,
            str(channels),
        )
        require(
            results["concept_promote"]["concept_decision"]["decision"]
            == "promoted"
            and results["concept_reject"]["concept_decision"]["decision"]
            == "rejected",
            str(results),
        )
        require(
            results["concept_promote"]["inquiry_id"]
            != results["concept_reject"]["inquiry_id"],
            "distinct validation runs collapsed into one inquiry identity",
        )

        status, live_session = request_json(
            base_url, f"/embodied/session/{session_id}"
        )
        require(
            status == 200
            and len(live_session["cognitive_inquiry_history"]) == 4
            and live_session["world_fact_ledger"][
                "cognitive_extension_is_secondary_fact_source"
            ]
            is False,
            str(live_session),
        )

        status, invalid = request_json(
            base_url,
            "/cognitive/inquiry/run",
            {"session_id": "missing", "scenario": "quality_profile_drift"},
        )
        require(status == 404 and invalid["error"] == "embodied_session_not_found", str(invalid))
        status, unknown = request_json(
            base_url,
            "/cognitive/inquiry/run",
            {"session_id": session_id, "scenario": "unknown"},
        )
        require(
            status == 400
            and unknown["error"] == "cognitive_inquiry_scenario_not_found",
            str(unknown),
        )

        html = (ROOT / "embodied_home.html").read_text(encoding="utf-8")
        require(
            'id="inquiryMode"' in html
            and 'id="runInquiry"' in html
            and 'id="inquiryResult"' in html,
            "embodied inquiry controls missing",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print(
        "Validated: inquiry catalog, four session-bound loops, P018/P016 gates, "
        "shared ledger readback, errors, and embodied controls."
    )


if __name__ == "__main__":
    main()
