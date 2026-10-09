# Prep Manager provenance

- Round 2 repository: https://github.com/Manvith111/cube26-prp-0319-manvith111
- Source checkout reviewed: `f5f8ad98fa8085a092c796b0681689d52ffc871e`
- Integration in this folder: Python Round 3 contract adapter calling the Round 2 Next.js `POST /api/inspect` entry point. The adapter maps its returned deterministic rule-engine checks, rule citations, and uncertainty to the shared Evidence Record; it does not reimplement the vision or rules engine.
- Runtime: configure `PREP_MANAGER_URL` for the independently running Prep Manager service. If that service/product/image input is missing or fails, the adapter emits a pending UNCERTAIN record. It never claims a successful inspection in that case.
- This adapter does not copy the complete Next.js application. The Pod must decide whether to vendor/run that service within this repository before a self-contained deployment.
