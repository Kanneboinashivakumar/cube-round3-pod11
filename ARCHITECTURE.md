# DockProof Receiving Manager architecture

This branch runs the Receiving Manager as its only active product agent. A project-scoped orchestrator flow calls that agent, validates its output, owns workflow state, and records immutable evidence. The same integration boundary can host other teams' compatible agents and project flows later, without showing those agents as active receiving features today.

## System architecture

```text
Browser · operator / reviewer
        │
        ├── FastAPI receiving UI (web/index.html, web/static/)
        ├── GET /receiving ───────────── data/sample/receiving_sample.csv
        └── POST /events · GET /workflows · review / evidence
                         │
                 Project flow resolver
             orchestration/projects/<project>/flow.json
                         │
             Shared orchestrator + FileStore
       route · validate · retry · audit · derive outcome
                         │ Agent Input / Agent Output
                 Receiving Manager agent
                   agents/receiving/
                         │
          eight checks · evidence record · SHA-256
                         │
                  Evidence FileStore
```

The active project is `receiving`, with flow `receiving-manager-v1`. That flow has one stage: `receiving`. Prep, Pack, Returns, Recovery, and other peers are not called by this project's flow and are not presented as available application features.

## Components

| Component | Code | Responsibility |
| --- | --- | --- |
| Receiving UI | `web/index.html`, `web/static/app.js`, `web/static/app.css` | Receiving dashboard, ledger, shipment grouping, inspection details, review queue, evidence, catalogue, quality summary, settings, and receipt intake. |
| HTTP API | `orchestration/api.py` | Reads the receiving fixture, accepts receipt events, exposes workflows / evidence / health, and records reviewer overrides. |
| Project flow | `orchestration/projects/receiving/flow.json` | Names the currently active project and its Receiving Manager stage. |
| Orchestrator | `orchestration/orchestrator.py`, `rollup.py` | Runs stages from flow data; validates agent output; records errors, retries, transitions, overrides, and final outcomes. |
| Agent client | `orchestration/clients.py` | Invokes an agent in-process or through its HTTP contract, based on the agent manifest. |
| Receiving Manager | `agents/receiving/app.py`, `vlm.py` | Produces eight check results from the supplied fixture or the optional live vision adapter. |
| Shared contract | `shared/schemas/`, `shared/contracts/agent-api.md` | Defines the stage-independent Agent Input, Agent Output, evidence, workflow, and final-outcome data shapes. |
| Persistence | `orchestration/store.py` | Stores workflow state and immutable evidence using the local JSON `FileStore`. |
| Sample data | `data/sample/receiving_sample.csv` | The 100 supplied receipt rows used by the ledger and offline fixture adapter. |

## Data flow

1. The UI loads receiving rows from `GET /receiving`. Each row is mapped to the eight checks and one of `PASS`, `EXCEPTION`, or `UNCERTAIN`. The source remains the supplied CSV; fixture rows explicitly say that referenced photos were not analyzed.
2. An operator submits `PRODUCT_RECEIVED` to `POST /events` with `project_id`, organization, unit, expected PO fields, and optional photos. For a known sample unit, the Receiving Manager resolves the row from the same tenant-scoped fixture. For a new unit, supplied expectations and uploaded photos are used.
3. The API resolves the requested project's flow. `receiving` selects `orchestration/projects/receiving/flow.json`. The orchestrator constructs the workflow from the flow and sends an Agent Input with available captures and context.
4. The Receiving Manager returns one structured output containing SKU identity, total quantity, carton count, units per carton, variant, carton damage, product damage, and component checks. If the model/evidence is unavailable, the adapter returns pending / uncertain evidence rather than a pass.
5. The orchestrator validates stage, workflow, tenant/subject, schema, content hash, and output/evidence consistency. Accepted evidence is stored immutably; failures become explicit degraded evidence. The orchestrator derives the final outcome.
6. A reviewer may add an override with actor and reason. It references the source evidence and appends to the audit trail; it does not replace the original record.
7. The UI reads the workflow bundle for the inspection and evidence views. Search, filters, PO grouping, and sample quality summaries are derived from the same receiving rows.

## Multi-project and multi-agent extension

Each project gets an independent flow at `orchestration/projects/<project_id>/flow.json`. `POST /events` and `GET /health` accept `project_id`; the resolver rejects projects with no registered flow. Workflow identifiers include the project namespace, so identical unit IDs in two projects do not collide. Omitting `project_id` from legacy workflows preserves the original ID format.

Evidence record IDs share one global store as well; agents used by multiple projects must include the project key in their record IDs. The Receiving Manager emits IDs such as `RCV-receiving-0001` for the active project.

To integrate another team's agent:

1. Put its implementation in an isolated `agents/<stage>/` package or run it as a service.
2. Add an `agent.json` manifest naming its stage, `agent_id`, owner, and `inproc` or `http` connection mode.
3. Implement `GET /health` and `POST /run` using `shared/contracts/agent-api.md` and the JSON schemas. The agent returns evidence; it must not write workflow state or call peer agents directly.
4. Add the stage to that project's flow only after its owner has integrated it. Keep uncertainty, retry, and failure policies explicit.
5. Reuse the shared orchestrator, evidence store, and project namespace. Do not add the other team's feature cards to the Receiving Manager UI unless the product owner asks for a shared multi-agent workspace.

This design allows separate projects to use the same application/orchestrator contract while preserving project-specific flow order and state. It does not claim those integrations are already deployed.

## Model and agent usage

- `VLM_MODE=mock` is the offline default: the adapter maps supplied CSV fields to checks. This is a deterministic fixture replay, not image understanding.
- `VLM_MODE=live` can use Gemini or OpenRouter. One multimodal request covers all eight checks and the available receiving photos.
- The observation schema is validated before deterministic rules assign decisions. Model prose cannot overrule a failed check or convert missing evidence into a pass.
- Confidence and evidence references are included when supplied. Unreadable or absent visual evidence is an explicit uncertainty.

## Important engineering decisions

| Decision | Reason / tradeoff |
| --- | --- |
| One active Receiving Manager flow | Keeps this contribution scoped to the agent already built; peer teams can integrate later through the generic contract. |
| Project-scoped flow files and workflow IDs | Lets multiple projects share one orchestrator without colliding unit IDs or forcing identical stage sequences. |
| Shared language-agnostic agent contract | A teammate can use a Python in-process agent or any HTTP service without changing orchestrator semantics. |
| Orchestrator-owned state | Agents supply evidence only; one component controls retries, status, audit history, and final outcome. |
| `UNCERTAIN` is first-class | Missing or ambiguous evidence must not silently become a commercial pass. |
| Deterministic decision rollup | Any failed check remains an exception; otherwise uncertainty remains open; only all-pass checks pass. |
| Fixture and live observation are labeled separately | The sample CSV enables a reproducible demo, but it cannot be represented as image inspection. |
| Local JSON persistence for the demo | Easy to run without an external database; not sufficient for authenticated, multi-instance production use. |

## Boundaries

The current API has no authentication, and `FileStore` is local. Do not expose it publicly without tenant authentication and authorization, shared transactional persistence, durable image storage, and deployment hardening. The CSV's `photo_refs` are fixture references; the repository does not guarantee corresponding image files.
