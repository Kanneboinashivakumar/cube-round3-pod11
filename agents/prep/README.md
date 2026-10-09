# agents/prep/  ·  Prep Manager

This agent adapts the existing Prep Manager service at `Manvith111/cube26-prp-0319-manvith111` to the Round 3 in-process contract. The Next.js `/api/inspect` endpoint runs its existing batched visual observation and deterministic FBA rules engine. The adapter maps applicable PASS, FAIL and UNCERTAIN checks, preserves rule references, photo references, and the source inspection ID, and excludes `NOT_APPLICABLE` / `NOT_VERIFIABLE` from the common verdict rollup while retaining them in payload.

## Run

Set `PREP_MANAGER_URL` to the running Prep Manager base URL, then start the orchestrator as usual. Supply `context.case.prep.product` using the Prep Manager `ProductInput` fields, and save images under `data/input/<org_id>/<unit_id>/prep/`. The adapter verifies tenant path and SHA-256 before sending images to `POST /api/inspect`.

Optional timeout: `PREP_MANAGER_TIMEOUT_S` (default 90). Without a configured service, product, or usable photo, it records a pending UNCERTAIN result. A service failure remains visible as pending; it never becomes PASS.

## Limits

The Prep Manager service is a separate Next.js runtime and is not vendored here yet. Visual analysis and rule evaluation are performed by that source service, not this Python adapter. No weight/dimension measurement is inferred from images; `payload.measurements` contains only explicitly supplied `context.case.prep.measurements`.

See [PROVENANCE.md](PROVENANCE.md) for source revision and integration scope.
