# Project-scoped orchestrator

The orchestrator owns workflow state and invokes only the stages declared in the selected project's flow. It validates and stores each agent's evidence, applies retry / uncertainty policy, derives the final outcome, and records reasoned overrides.

## Active project

The receiving UI uses `project_id=receiving` and [`projects/receiving/flow.json`](projects/receiving/flow.json). That flow contains only `receiving`, the DockProof eight-check agent. Other agent modules in the repository are not active features of this project.

```sh
make serve
curl 'http://localhost:8100/health?project_id=receiving'
curl 'http://localhost:8100/receiving?verdict=EXCEPTION'
```

## Add a future project flow

1. Create `orchestration/projects/<project_id>/flow.json` with a unique `flow_id`, ordered `steps`, and explicit failure / uncertainty defaults.
2. Register each stage in `agents/<stage>/agent.json` and implement `GET /health` + `POST /run` according to [`../shared/contracts/agent-api.md`](../shared/contracts/agent-api.md).
3. Start a workflow with `POST /events` including its `project_id`; inspect that project's health with `GET /health?project_id=<project_id>`.
4. Keep workflow state and final outcome in the orchestrator. An agent returns evidence only and must not invoke another agent directly.

Project ID is included in workflow IDs and stored in workflow context, preventing collisions when separate projects use the same org/unit identifiers. Existing calls that omit a project retain their legacy workflow IDs.

## Core modules

| File | Responsibility |
| --- | --- |
| `orchestrator.py` | Starts, advances, resumes, validates, and overrides workflows. |
| `rollup.py` | Derives state and final outcome from workflow evidence. |
| `store.py` | Memory and local JSON stores. |
| `clients.py` | In-process / HTTP agent clients and manifest loading. |
| `api.py` | FastAPI UI and API entry points. |
| `flow.json` | Receiving-only legacy/default flow. |
| `flow.cube.json` | Receiving-only compatibility flow retained for the earlier event UI. |

The API and JSON store are demo infrastructure, not a production security boundary; add authentication, authorization, and shared persistence before public deployment.
