# Product brief · DockProof Receiving Manager

## Product and audience

DockProof is a receiving application for warehouse operators, reviewers, administrators, and evaluators. Its shared WMS-style surface keeps the inbound ledger, purchase-order context, inspection decisions, and evidence together. The current product contribution is the Receiving Manager only.

## User problem

At receipt, operators need to decide whether inventory matches the purchase order and arrived in acceptable condition. Spot checks and delayed reporting make shortages, wrong variants, damaged cartons, and missing components difficult to resolve with suppliers. A usable decision must preserve uncertainty when the available evidence is insufficient.

## Product direction

Use the supplied WMS dashboard screenshot as the visual reference: compact left navigation, a light neutral canvas, clear operational totals, a receiving queue, and direct access to the selected receipt. Translate that composition to DockProof's purchase orders, shipments, inspections, review queue, evidence, catalogue, evaluation, and settings. Keep only receiving features in the active surface; do not present Prep, Pack, Returns, Recovery, or other teams' agents as integrated product features.

## Core user tasks

1. Review arrivals and shipment / PO-line information from the supplied receiving dataset.
2. Record a receipt with PO and catalogue expectations, operator context, and optional receiving photos.
3. Inspect eight checks: SKU identity, quantity, carton count, units per carton, colour / variant, carton damage, product damage, and components.
4. Review exceptions and uncertain checks; an authorized reviewer can record a reasoned override without erasing the original evidence.
5. Inspect and export the agent's structured evidence record, including provenance and content hash.
6. Reference the product catalogue, quality evaluation data, and receiving runtime settings.

## Product principles

- Evidence supports the outcome; a model narrative does not decide commercial acceptance.
- Missing, unreadable, or ambiguous observations remain `UNCERTAIN`.
- A failed check produces an exception; otherwise uncertainty remains visible; only all-pass checks produce a pass.
- The orchestrator owns workflow state and preserves immutable evidence and the override audit trail.
- Fixture values are labeled as fixtures and are never described as a photo inspection.

## Scope and limitations

The active UI and `orchestration/projects/receiving/flow.json` invoke only the Receiving Manager. The orchestration core remains generic: each project can register a project-scoped flow and contract-compatible agent without making that agent part of this receiving UI. Other agent folders in the shared starter are not presented as integrated features here.

The default UI dataset is `data/sample/receiving_sample.csv`, matching the 100-row file supplied for this task. The bundled row values and photo references are synthetic fixtures; the default adapter does not inspect photo pixels. Live image analysis remains optional and requires a configured Gemini or OpenRouter key and real image uploads. Workflow persistence is local JSON storage; the API is unauthenticated and must not be exposed publicly without adding authentication, authorization, shared durable storage, and deployment hardening.
