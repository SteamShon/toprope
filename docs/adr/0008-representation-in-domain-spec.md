# ADR-0008: Representation is declared in the domain spec; UI is generated from it

- Link: ③ shared language · Status: accepted · 2026-11-04 · decided by: SteamShon

## Context
The intent is that a domain author declares not only what the domain *means* (objects,
links, actions) but also how it is *represented* to people, in the same spec. The user-facing
UI is then generated automatically. OpenUI and CopilotKit were named as examples of
"declaration → generated UI"; any generative-UI stack is acceptable. CopilotKit fits the
Aegra stack (AG-UI) and supports A2UI, a pure-data component format that can be emitted
without an LLM.

ADR-0004 allows extending the minimal core only with an ADR that names the need. This is
that ADR for `representation`.

## Decision
- The domain spec gains a **`representation`** section: views per object (`list`, `detail`,
  `board`, …), forms per action, field order and grouping, and which actions appear where.
  See docs/domain-schema.md.
- Representation never redefines meaning. Labels, descriptions and denial reasons come from
  the glossary, `description` and `reason`. A view can show an action only if the model
  allows it in the current state.
- **Declared views are generated deterministically.** The same spec and the same state give
  the same screen, compiled to A2UI and rendered via CopilotKit.
- **Undeclared views get schema defaults.** Objects and actions without a representation
  still get a generated list, detail view and form.
- **Undeclared, ad-hoc requests go to the LLM.** For example, "compare the blocked
  experiments". The LLM composes the screen at runtime from the *declared* components and
  the model's actions only. It cannot introduce actions or rules.

## Rationale
③ needs one shared reference. Declared, deterministic views are that reference for people,
as the generated MCP is for agents. Generative UI adds flexibility at the edges without
becoming a second source of meaning.

## Consequences
The compiler has three outputs from one spec: MCP, A2UI views, and a component and action
catalog that constrains the generative layer. M0 renders declared views. The generative
layer comes later (M3 at the latest, where ③ is tested).
