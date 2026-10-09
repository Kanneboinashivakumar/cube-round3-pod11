# agents/pack/  ·  Pack Manager

This agent adapts PackGuard's deterministic Pack Manager verifier to the Round 3 agent contract. It compares expected and operator-observed SKU quantities and produces `items_present`, `quantities_correct`, and `no_extra_items` checks with a traceable evidence record.

Provide `context.case.pack.order_lines` and `context.case.pack.observed_in_box` as semicolon-separated `SKU:quantity` pairs. For example: `SKU-A:2;SKU-B:1`. The expected and observed strings must come from the order and an operator/capture process. Photos are cited when supplied but are not analyzed by this verifier; no visual count is claimed. Missing/malformed data yields UNCERTAIN and human review.

The CUBE flow routes `route == "mfn"` units to Pack and skips Pack for FBA. Run the agent with `uvicorn agents.pack.app:app --port 8103` or use the in-process orchestrator configuration.

See [PROVENANCE.md](PROVENANCE.md) for source revision and scope.
