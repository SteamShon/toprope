# Decision Records

Each record names its link in the claim chain, the decision, who decided, and why.
A record is superseded rather than deleted when a decision changes. History before
2026-11-04 was reset when Toprope's definition was agreed; it remains in git.

| ADR | Link | Decision |
|---|---|---|
| [0001](0001-claim-chain-is-the-backbone.md) | all | The claim chain is the backbone |
| [0002](0002-self-compile-first-then-dogfood.md) | ① ② | First domain = Toprope itself, then dogfood |
| [0003](0003-raw-material-order.md) | ① ② | Raw material order: system → records → interview → use |
| [0004](0004-minimal-core-with-provenance.md) | ① ② | Minimal core with provenance and status |
| [0005](0005-docs-language-and-visibility.md) | none | English docs, Korean notes; private until first results |
| [0006](0006-defer-runtime-and-host.md) | none | Defer runtime and host (superseded by 0007) |
| [0007](0007-aegra-adapter-python-core.md) | ① ④ | Python core; Aegra as runtime adapter; TypeScript frontend |
| [0008](0008-representation-layer.md) | ③ | Representation is a separately compiled layer that hosts can override |
| [0009](0009-change-safety-is-the-compiler-core.md) | ① ② | Premise P0; ① = iterate safely; change safety is the compiler's core job |
