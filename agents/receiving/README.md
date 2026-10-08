# DockProof Receiving Manager · Round 3 adapter

**Owner:** [@chapalaumesh209](https://github.com/chapalaumesh209)

**Round 2 source:** [cube26-rcv-0068-chapalaumesh209](https://github.com/chapalaumesh209/cube26-rcv-0068-chapalaumesh209)

This adapter brings the Round 2 DockProof Receiving Manager into the Pod's Agent Input / Agent Output contract. It preserves the eight-check inspection: identity, quantity, cartons, units per carton, variant, carton damage, unit damage, and expected components. The orchestrator still owns workflow state and records this agent's sealed evidence with its downstream context.

## Evidence and model behavior

- A live observation uses one multimodal request for all available receipt images. Configure either Gemini or OpenRouter as described in the repository `.env.example`.
- The default is offline/mock mode. Known organiser rows are explicitly identified as synthetic CSV fixtures, not photo inspections.
- A new receipt with no known fixture and no live vision returns UNCERTAIN checks. A missing PO expectation also makes its related check UNCERTAIN.
- A provider, timeout, image, or structured-output error creates a pending/error UNCERTAIN evidence record. It never turns into PASS or a hidden mock fallback.
- Uploaded captures are stored beneath an organization- and unit-scoped `data/input/` path; evidence stores relative references and hashes, not client-provided filesystem paths.
- Receiving scope is `po_line`, keeping a supplier-side shortfall distinct from a channel-side unit loss (Round 3 finding F-10).

## Run

Run the integrated app from the repository root:

```sh
make setup
make serve
# Open http://localhost:8100 and choose Receiving or Business events.
```

For live image inspection, set `VLM_MODE=live` and either `GEMINI_API_KEY` (optionally `GEMINI_MODEL`) or `OPENROUTER_API_KEY` (optionally `OPENROUTER_MODEL`). Keep keys only in an ignored `.env`; never commit them.

## Limits

The receiving bridge is implemented in Python to speak the Pod contract; the Round 2 Next.js app remains the source of its inspection rules and prompts. This branch does not copy the old app's auth/database/UI into the pod. Live visual analysis requires operator-entered PO expectations and actual images. The demo's file-backed workflow store is local and has no authentication; do not expose it publicly before adding identity, tenancy enforcement at the API boundary, and shared durable storage.
