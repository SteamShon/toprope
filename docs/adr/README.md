# Decision Records

Each record names its link in the claim chain, the decision, who decided, and why.
A record is superseded rather than deleted when a decision changes. History before
2026-11-04 was reset when Toprope's definition was agreed; it remains in git.

| ADR | Link | Decision |
|---|---|---|
| [0001](0001-claim-chain-is-the-backbone.md) | all | The claim chain is the backbone (superseded by 0009) |
| [0002](0002-self-compile-first-then-dogfood.md) | ① ② | First domain = Toprope itself, then dogfood |
| [0003](0003-raw-material-order.md) | ① ② | Raw material order: system → records → interview → use |
| [0004](0004-minimal-core-with-provenance.md) | ① ② | Minimal core with provenance and status |
| [0005](0005-docs-language-and-visibility.md) | none | English docs, Korean notes; private until first results |
| [0006](0006-defer-runtime-and-host.md) | none | Defer runtime and host (superseded by 0007) |
| [0007](0007-aegra-adapter-python-core.md) | ① ⑤ | Python core; Aegra as runtime adapter; TypeScript frontend (hosting part superseded by 0017) |
| [0008](0008-representation-layer.md) | ④ | Representation is a separately compiled layer that hosts can override |
| [0009](0009-change-safety-is-the-compiler-core.md) | all | Chain v2 is the backbone: premise P0; ① = iterate safely; change safety is the compiler's core job |
| [0010](0010-matrix-invariants-harness.md) | ① ② ③ ④ | Transition matrix, invariants and a small world drive a generated harness |
| [0011](0011-correctness-layer-and-software-factory.md) | ③, all | Correctness layer + software factory; chain v3 adds ③ works as built; greenfield and brownfield from M0; hosting open (hosting decided by 0017) |
| [0012](0012-event-sourcing-in-the-core.md) | ③ ⑤ | Event sourcing owned by the core; generated read-only query tools; Aegra consumes |
| [0013](0013-incremental-impact-and-test-selection.md) | ① | Incremental rebuilds: impact analysis, affected-only testing, result cache, background soundness run |
| [0014](0014-interview-design.md) | ① ② | Interview design: defaults, grouped cells, priorities, stop rule, privacy |
| [0015](0015-expressiveness-beyond-the-state-machine.md) | ② ③ | Timers, aggregate/cross invariants with reservations, function ports, external events, multi-party approval |
| [0016](0016-authorization-and-actor-identity.md) | ③ ④ | Relationship-based permissions; agents act on behalf of a principal with grants |
| [0017](0017-deployment-shapes.md) | ③ ④ | Core library, `toprope-server` first, shell, optional runtime; Aegra off the critical path until M4 |
| [0018](0018-live-data-migration.md) | ① ③ | In-flight check and migration plans in the change check and deploy gate |
| [0019](0019-thin-slice-first-and-milestone-specs.md) | all | Thin slice first (M0a → M1 → M0b), semantics before code, milestone spec PRs, third M1 arm |
| [0020](0020-world-map.md) | ④ ① | World map: a compiled skill-tree view of states, transitions, unlock requirements and fog; for people, agents and docs |
| [0021](0021-semantics-clarifications-from-the-oracle.md) | ① ③ | Semantics clarifications from the oracle: command validation, existence after role check, multi-role cells, principals are people, fail-closed effects, idempotency claims |
| [0022](0022-two-self-domains-authoring-and-delivery.md) | ① ② ③ ⑥ | Two self domains, Authoring and Delivery, joined by a typed handoff; staged bootstrap |
| [0023](0023-schema-v1.md) | ① ② ③ ④ | Schema v1: the whole declaration language defined up front, JSON Schemas, unimplemented constructs refused |
| [0024](0024-handoff-outbox-string-join-and-deploy-floor.md) | ③ ⑥ | Handoff outbox in the event log, resolutions, string joining, the local deploy floor |
| [0025](0025-staged-authoring-interview.md) | ① ② | Staged authoring interview: one question bundle per stage (sources → purpose → cast → actions → transitions → invariants → world → handoffs → review), with progress; link sources |
| [0026](0026-domain-composition.md) | ④ ⑥ ① | Domains compose, never inherit; a composition file declares members and wiring; receivers accept only wired senders; composed world map |
| [0027](0027-what-the-kernel-is.md) | ② ③ | The kernel is the hand-built toolchain (Execution semantics, compiler and change check, harness runtime, deploy floor); hand-built self-domain tools are not; a test for borderline facts |
| [0028](0028-self-domains-generated-end-to-end.md) | ① ② ③ | Self domains are generated end to end: kernel services called as declared effects, results back through `external:kernel`, a regeneration check; adds one M0a sub-PR |
| [0029](0029-authoring-and-delivery-as-semantic-git.md) | ① ② ⑥ | **Proposed.** Authoring as an immutable commit log with approval tags and a semantic diff (re-confirm only direct changes); Delivery points an environment at one commit |
