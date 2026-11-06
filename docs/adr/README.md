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
| [0029](0029-authoring-and-delivery-as-semantic-git.md) | ① ② ⑥ | Authoring as an immutable commit log with approval tags and a semantic diff (re-confirm only direct changes); Delivery points an environment at one commit |
| [0030](0030-fidelity-is-measured-on-an-application-domain.md) | ① ② | ② is judged in M2 on an application domain; M1 judges ① and self-compile; self-domain gold becomes an optional smoke set |
| [0031](0031-self-domains-confirmed-by-interview.md) | ① ⑥ | The self domains are confirmed by interview, regeneration check, probes and sign-off; no correctness set; M1 freezes four ① instruments |
| [0032](0032-domain-knowledge-as-git-and-github.md) | ① ④ ⑤ | Domain knowledge managed like git + GitHub: the full mapping; no PR object, comments are questions, review requests are decision requests, check records on commits, one approver in M1; adds author, element log, checkout |
| [0033](0033-branches-from-the-start.md) | ① ④ ⑥ | **Accepted.** Branches from the start: protected `main`, approval = merge into `main`, element-level 3-way merge plus the change check, deploy only approved `main` commits, ancestry decides "newer" |
| [0034](0034-m1-is-a-pilot-for-iterate-safely.md) | ① ⑥ | **Accepted.** M1 pilots ① and ⑥ on the self domains and gives no link verdict; the ① verdict moves to M2; the self domains' M1 instruments are exempt from the human-only rule (agents may draft, the researcher selects and freezes); sub-PR 8 no longer waits on the change list and key |
| [0035](0035-mechanical-tests-without-examples.md) | ① ③ | **Accepted.** Two harness layers: a mechanical layer (every cell, inductive invariants, reachability from creation) that needs no examples, and a semantic layer (the expert's examples and scenarios) that is the evidence for ② |
| [0036](0036-generated-command-line-and-workflow.md) | ③ ④ | **Accepted.** A command line generated from the declaration (`toprope-run`), and a generated "how to work in this domain" section in the domain guide; hand-written guides keep only the kernel |
| [0037](0037-switch-over-to-the-generated-self-domains.md) | self-compile ③ | **Accepted.** Switch-over: only the kernel stays hand-built; `toprope-author`/`toprope-deploy` and their guides are replaced by the generated self domains; interview operations become kernel services |
| [0038](0038-m1-binding-joins-the-self-domain-exception.md) | ① ⑥ (pilot) | **Accepted.** The M1 binding joins ADR-0034's exception: an agent may draft it on request; the researcher selects and freezes it |
| [0039](0039-github-approval-as-a-human-channel.md) | ③ ⑥ | **Accepted.** A GitHub environment approval is a human channel: the researcher approves a request file's steps by pressing "Approve and deploy"; the approver's login is the identity |
| [0041](0041-world-model-and-context-graph.md) | ① ② ⑤ | **Accepted.** A domain keeps two graphs: the world model (objects, links, actions, functions, and the rules and permissions adopted over them; enforced) and the context graph (observations, memory, hypotheses, preferences, decisions, sources and history; not enforced); something crosses only through a reviewed change; approval refuses proposed elements; `rationale` on decisions; `actor.principal` in checks |
