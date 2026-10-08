# DockProof Receiving Manager · CUBE Round 3

DockProof captures inventory condition at the point of receipt. It compares the purchase-order expectation with observed or supplied receiving data, keeps uncertainty explicit, and records the Receiving Manager's evidence through a project-scoped orchestrator.

This contribution is **receiving-only**: its active flow calls the Receiving Manager, not the other agents present in the shared starter. The orchestrator is structured so other teams can add contract-compatible agents and project-specific flows when they are ready.

## Problem understanding

Manual spot checks and delayed discrepancy reports make shortages, wrong products, variant mismatches, carton damage, and missing components difficult to resolve with a supplier. Receiving evidence must be recorded while freight is available. If the expected values or evidence are insufficient, `UNCERTAIN` is a valid result and must not be auto-passed.

## Solution overview

- A responsive WMS-style receiving workspace organizes the arrival ledger, shipments, inspection details, exceptions, evidence, catalogue, evaluation summary, and settings.
- The Receiving Manager evaluates eight checks: SKU identity, total quantity, carton count, units per carton, colour / variant, carton damage, product damage, and expected components.
- Deterministic rules produce `PASS`, `EXCEPTION`, or `UNCERTAIN`; the model does not own the commercial decision.
- The orchestrator validates the agent contract, owns workflow state, retries failures, stores immutable evidence, and supports reasoned reviewer overrides.
- A project ID namespaces workflows and resolves that project's flow file, so identical unit IDs in separate projects do not collide.

## Dataset and fixture boundary

The UI reads [`data/sample/receiving_sample.csv`](data/sample/receiving_sample.csv), the same 100-row CSV supplied for the Receiving Manager. The offline adapter replays structured fixture fields; it does **not** analyze pixels. `photo_refs` in the sample are fixture references and are not guaranteed to point to local images. The UI labels these values accordingly.

Live inspection can be enabled with Gemini or OpenRouter credentials and actual uploaded photos. A live model failure or insufficient image evidence remains pending / uncertain; there is no silent fallback to a fixture pass.

## Setup

Requirements: Python 3.11+.

```sh
make setup
make serve
```

Open [http://localhost:8100](http://localhost:8100). `make setup` creates the local virtual environment and `.env`; the sample receiving UI is available without an API key. The API is a local demo service and is not authenticated for public deployment.

## Usage

1. Open **Overview** to see totals derived from the provided CSV and a small queue of receipts requiring attention.
2. Search or filter **Receipts**, **Shipments**, and **Inspections** by unit, PO, supplier, or SKU.
3. Open a receipt to compare expected and received data across the eight checks.
4. Choose **Run receiving inspection** to create a project-scoped workflow and evidence record. On fixture units the agent clearly identifies the CSV as its source; new receipts can include real photos.
5. Review failed or uncertain items in **Review queue**. A reviewer override requires an actor and reason and appends to the evidence audit trail.
6. Open **Evidence** to inspect agent output. The **Product catalogue** and **Quality lab** are derived from supplied sample records; the lab is descriptive fixture coverage, not live-model accuracy.

For a new receipt, submit the PO expectation and optional JPEG, PNG, or WebP photos using the in-app form. Live vision requires a provider key and `VLM_MODE=live` in `.env`.

## Orchestrator and teammate integration

The active project flow is [`orchestration/projects/receiving/flow.json`](orchestration/projects/receiving/flow.json). To add an agent to a different project, add `orchestration/projects/<project_id>/flow.json`, register each agent in `agents/<stage>/agent.json`, and implement the shared [Agent HTTP API](shared/contracts/agent-api.md). The orchestrator can invoke an in-process Python agent or a language-independent HTTP agent; it validates and stores evidence before moving to the next configured stage. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for ownership, event flow, extension steps, and boundaries.

## Validation

```sh
make test
make serve
```

The repository test suite validates the starter orchestration and agent contracts. The UI's offline fixture decisions should not be reported as vision-model benchmark results.

## Assumptions and limitations

- Synthetic CSV values are for repeatable demonstration only; referenced photos may not exist locally.
- Live image inspection requires real photos and a configured provider key.
- The FastAPI demo has no user authentication. Do not expose it publicly without authentication, authorization, and request / upload limits.
- `FileStore` and local captures are not shared or production-durable. Production use needs shared transactional persistence and durable object storage.
- Multi-project support provides project-scoped flow configuration and workflow IDs; it does not mean other team agents have already been integrated or tested in this product.
