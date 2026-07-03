# Demo Runtime

This demo runs the first minimal execution-governance loop for the world model project.

It demonstrates:

1. Plan precheck.
2. Action declaration.
3. Provenance-chain verification.
4. Agency-budget evaluation.
5. Decision-token issuing.
6. Controlled execution.
7. Experience recording.
8. Audit-summary generation.

## Run

From the repository root:

```powershell
python .\demo_runtime\run_demo.py
```

The script resets the demo workspace on every run, executes the governed plan, and writes outputs to:

```text
demo_runtime/output
```

## Expected Result

The expected audit summary is:

```json
{
  "total_steps": 6,
  "allowed": 2,
  "limited_allowed": 2,
  "blocked": 1,
  "metadata_only": 1
}
```

Expected workspace state:

1. `项目说明书.md` is moved to `workspace/organized/docs`.
2. `临时记录.txt` is moved to `workspace/organized/archive`.
3. `专利权利要求草稿.md` remains in `workspace/inbox` and receives a candidate action.
4. `合同扫描件.pdf` remains in `workspace/inbox` and receives a candidate action.
5. `未知来源资料.docx` remains in `workspace/inbox` and is blocked because its source is unverified.

## Output Files

The demo generates:

1. `precheck.json`
2. `action_declarations.json`
3. `source_chains.json`
4. `budget_decisions.json`
5. `decision_tokens.json`
6. `candidate_actions.json`
7. `experience_records.json`
8. `audit_summary.json`
9. `final_objects.json`

These files are intended as implementation evidence for the first phase.

## Skill Co-Creation Demo

Run the skill co-creation MVP:

```powershell
python .\demo_runtime\run_skill_cocreation.py
```

The script reads:

```text
demo_runtime/skill_data/scenario.json
demo_runtime/skill_data/robot_capability.json
```

It writes reproducible outputs to:

```text
demo_runtime/output/skill_cocreation
```

Expected summary:

```json
{
  "total_steps": 6,
  "experiences": 6,
  "recoveries": 1,
  "preferences": 2,
  "skill_steps": 5
}
```

Generated files:

1. `scenario_context.json`
2. `robot_capability.json`
3. `task_plan.json`
4. `training_session.json`
5. `experience_records.json`
6. `recovery_records.json`
7. `preference_records.json`
8. `concept_patterns.json`
9. `skill_package.json`
10. `skill_audit.json`

## API Server

Start the demo API server:

```powershell
python .\demo_runtime\api_server.py
```

Default URL:

```text
http://127.0.0.1:8765
```

Available endpoints:

1. `GET /health`
2. `POST /plans/precheck`
3. `POST /demo/run`
4. `POST /experience/record`
5. `GET /audit/audit_demo_001`
6. `GET /outputs`

Example:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/health"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8765/demo/run"
Invoke-RestMethod -Uri "http://127.0.0.1:8765/audit/audit_demo_001"
```

## Evidence Chain

The code-to-technology evidence chain is documented at:

```text
技术库/代码-技术对应证据链.md
```
