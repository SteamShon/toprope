# ADR-0008: Representation is a separately compiled layer that hosts can override

- Link: ④ shared language · Status: accepted · 2026-11-04 · decided by: SteamShon

## Context
- A domain author should declare how a domain is *represented* to people, and the
  user-facing UI should be generated from that declaration. OpenUI and CopilotKit were
  examples of "declaration → generated UI"; any generative-UI stack is acceptable.
  CopilotKit fits the Aegra stack (AG-UI) and supports A2UI, a pure-data component format
  that can be emitted without an LLM.
- Representation changes far more often than domain meaning. Recompiling the domain (MCP,
  execution checks) for a layout change is waste.
- Whoever hosts a Toprope domain must be able to inject their own UI: their components,
  layouts and branding.

ADR-0004 allows extending the minimal core only with an ADR that names the need. This is
that ADR for representation.

## Decision

### 1. Two layers, two compilations
- **Domain** (`*.domain.yaml`) holds meaning: objects, links, actions, glossary. Compiling it
  produces MCP, the execution checks, and a **domain interface**: the list of objects,
  fields, links, actions (params, reasons) and glossary terms. It is versioned by the
  compiler from the diff (removal or rename = major, addition = minor, text only = patch),
  and every element has a content hash. The name avoids "contract", which ADR-0004 reserves
  for a deferred execution concept.
- **Representation** (`*.representation.yaml`) holds how it is shown: views per object
  (`list`, `detail`, `board`, …), forms per action, field order and grouping, and where
  actions appear. It declares the interface major range it targets.
- The representation compiler reads **only the domain interface**, never the domain source.
  - A representation change recompiles only the views. MCP and execution are untouched.
  - A domain change recompiles the domain and re-validates every representation against the
    new interface. Broken references (a removed field or renamed action) fail the build.
    Views whose referenced elements kept their hashes are reused.
- The two layers are versioned separately. The record of a released UI is a pair:
  (domain version, representation version).

### 2. Layered representation with host injection
Representation is resolved in layers, and later layers override earlier ones:

1. **Schema defaults**: generated from the interface for anything undeclared.
2. **Base representation**: written by the domain author.
3. **Host overlay**: written by whoever hosts the domain. It can override views, layouts and
   field widgets. It names the base versions it accepts and the interface range it targets,
   and is re-validated whenever the domain, the base or the overlay changes. Maps merge by
   key. Keyed lists (sections by title, fields, columns and actions by name) merge by key,
   and `{replace: [...]}` replaces a whole list (docs/domain-schema.md).

The host can also register **custom components** in the renderer's catalog (for example,
React components in CopilotKit) and reference them from its overlay. Custom components:
- receive data and the currently allowed actions through the domain interface
- invoke actions only through Execution, so preconditions and roles are still enforced on
  the server, whatever the UI does
- cannot add actions, rules or fields that are not in the interface.

### 3. Generation
- **Declared views** (any layer) compile deterministically to A2UI and render via
  CopilotKit. The same layers and state give the same screen.
- **Ad-hoc requests** with no declared view (e.g. "compare the blocked experiments") are
  composed by an LLM at runtime, from the catalog (built-in and host components) and the
  allowed actions only.

### 4. Terminology stays shared
Representation never redefines meaning. Labels, descriptions and denial reasons come from
the glossary, `description` and `reason`. A host that needs different wording declares an
**alias** that maps to the glossary term, so agents and people can still be mapped to the
same term. Host components receive labels with aliases applied. The compiler cannot
inspect inside opaque host components, so text hardcoded there is the host's
responsibility and is not checked. Only declared aliases are guaranteed to stay mapped.

## Rationale
④ needs one shared reference for meaning. Separating representation lets the frequent
change (presentation) move fast without touching the rare, governed change (meaning). The
interface boundary keeps host customization from becoming a second source of meaning.

## Consequences
- Compiler outputs: from the domain, MCP + execution checks + domain interface. From the
  representation layers plus the interface, A2UI views + a component/action catalog for the
  generative layer.
- Representation changes are lighter decisions than domain changes. They are recorded, but
  they do not need a domain-change approval. Whether they count as a third accumulated
  decision kind is open (⑤).
- M0 proves this with a toy domain:
  - a representation-only change rebuilds without touching MCP
  - a domain change flags a broken view
  - a host overlay injects one custom component.
