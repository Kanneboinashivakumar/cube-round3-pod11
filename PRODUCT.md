# Product brief · CUBE FLOW / Round 3

## Product and audience

CUBE FLOW is a shared warehouse operations surface for receiving operators, fulfilment staff, reviewers, and the pod members integrating specialist agents. The primary user is an operator handling inventory at the dock; reviewers need to reconstruct what happened from the same durable unit passport.

## User problem

Inventory decisions are currently fragmented across manual checks and specialist tools. A shortage, wrong variant, damage, return, or fee can be discovered after its strongest evidence window has passed. Later agents also need trustworthy upstream context rather than independent, disconnected judgments.

## Product direction

Use the supplied WMS dashboard as the visual reference for the shared starting page: compact warehouse navigation, live operational summaries, a clear work queue, and an event-first action. A unit passport ties the product's lifecycle together. The existing DockProof Receiving Manager remains its own first-class workflow and agent, while the orchestrator activates other specialists as business events make them relevant.

## Core user tasks

1. Start a passport when inventory is physically received and provide the PO expectation and receiving photos.
2. Review the Receiving Manager's eight checks: SKU identity, quantity, carton count, units per carton, variant, carton damage, unit damage, and components.
3. Identify the FBA/MFN route when known, activating Prep or Pack—but never both.
4. Add a physical-return event or a fee/charge event later, reusing the existing passport and evidence chain.
5. Review exceptions, uncertain checks, agent failures, source references, overrides, and final outcomes.

## Product principles

- Evidence before outcome; a model observation is not itself the system's commercial decision.
- Missing, unreadable, or ambiguous evidence stays UNCERTAIN. It never silently becomes PASS.
- The orchestrator is the only owner of lifecycle state; agents contribute validated evidence.
- A later event advances the unit journey rather than fabricating future events during initial receipt.
- Each business event is idempotent, auditable, and scoped to one organization and unit.

## Scope and limitations

This branch adds a FastAPI-served responsive operations UI and event entry points to the existing Python orchestrator, plus an adapter for the author's Round 2 DockProof Receiving Manager. It does not replace other pod members' specialist agents or claim ownership of their Round 2 implementations. Their current modules remain the Round 3 repository's in-process agents until their owners integrate their versions.

The default demo uses synthetic CSV fixtures. The live DockProof observation path is optional and requires a Gemini or OpenRouter key plus real image captures. Workflow/evidence persistence remains the starter's local JSON FileStore; authentication, shared durable storage, and public production deployment are out of scope and must be added before an internet-facing launch.
