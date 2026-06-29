from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from run_demo import DATA_DIR, OUTPUT_DIR, plan_precheck, read_json, run_pipeline


HOST = "127.0.0.1"
PORT = 8765


def response(status: str, data: Any = None, reason_codes: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason_codes": reason_codes or [],
        "data": data,
    }


def read_body(handler: BaseHTTPRequestHandler) -> Any:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw)


def write_response(handler: BaseHTTPRequestHandler, status_code: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class DemoApiHandler(BaseHTTPRequestHandler):
    server_version = "WorldModelDemoAPI/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            write_response(self, 200, response("ok", {"service": "demo_runtime_api"}))
            return

        if parsed.path.startswith("/audit/"):
            audit_id = parsed.path.rsplit("/", 1)[-1]
            audit_path = OUTPUT_DIR / "audit_summary.json"
            if not audit_path.exists():
                write_response(self, 404, response("error", reason_codes=["audit_not_found"]))
                return
            audit = read_json(audit_path)
            if audit.get("audit_id") != audit_id:
                write_response(self, 404, response("error", reason_codes=["audit_id_mismatch"]))
                return
            write_response(self, 200, response("ok", audit))
            return

        if parsed.path == "/outputs":
            if not OUTPUT_DIR.exists():
                write_response(self, 200, response("ok", {"files": []}))
                return
            files = sorted(str(path.relative_to(OUTPUT_DIR)).replace("\\", "/") for path in OUTPUT_DIR.glob("*.json"))
            write_response(self, 200, response("ok", {"files": files}))
            return

        write_response(self, 404, response("error", reason_codes=["not_found"]))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/plans/precheck":
                body = read_body(self)
                objects = {item["object_id"]: item for item in read_json(DATA_DIR / "objects.json")}
                rules = read_json(DATA_DIR / "rules.json")
                plan = body.get("plan") or read_json(DATA_DIR / "plan.json")
                result = plan_precheck(plan, objects, rules)
                write_response(self, 200, response("ok", result))
                return

            if parsed.path == "/demo/run":
                audit = run_pipeline()
                write_response(self, 200, response("ok", audit))
                return

            if parsed.path == "/experience/record":
                body = read_body(self)
                out_path = OUTPUT_DIR / "external_experience_records.json"
                records = read_json(out_path) if out_path.exists() else []
                record = {
                    "experience_id": body.get("experience_id", f"external_exp_{len(records) + 1:03d}"),
                    "payload": body,
                }
                records.append(record)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
                write_response(self, 200, response("ok", record))
                return

            write_response(self, 404, response("error", reason_codes=["not_found"]))
        except Exception as exc:
            write_response(self, 500, response("error", {"message": str(exc)}, ["internal_error"]))


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), DemoApiHandler)
    print(f"Demo API server listening on http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
