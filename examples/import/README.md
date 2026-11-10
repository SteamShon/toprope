# Example: start a declaration from what a team already has

Link: none (an example for ADR-0049, A1a and A1b). Four sources a team often has, and the proposed
draft `toprope-import` makes from each. Every element it writes is `proposed`, citing the exact
place it came from; a person confirms what is right, and the interview asks what the source
cannot say (who may take each action, what each stage allows).

```bash
uv run toprope-import openapi examples/import/orders.openapi.yaml --domain shop --out /tmp/shop.domain.yaml
uv run toprope-import sql examples/import/orders.sql --domain shop --out /tmp/shop-db.domain.yaml
uv run toprope-import workflow examples/import/support.workflow.json --domain support --out /tmp/support.domain.yaml
uv run toprope-import rules examples/import/rules --via tree --questions /tmp/rules.yaml
```

| Source | Becomes |
|---|---|
| OpenAPI schemas | things and their facts; an `enum` named `status`, `state` or `stage` also becomes the thing's stages |
| OpenAPI POST, PUT, PATCH, DELETE | actions with typed inputs from the request body (a GET changes nothing) |
| SQL `CREATE TYPE … AS ENUM`, `CHECK (… IN …)` | enum facts of the table's thing |
| a workflow export (`statuses`, `transitions` with `from`, `to`, `name`) | stages, actions, and a cell for each allowed move; every other cell stays `undecided`, for the interview |
| an MCP server's tools (`mcp`, read with the `mcp` reader from its command or URL) | a proposed action for each tool that changes something, with its call and reply; read-only tools as read bindings; a draft binding (`--binding-out`) |
| `AGENTS.md`, skill files, any Markdown (`rules`; a folder with `--via tree`) | no element: each sentence that binds someone (must, never, only, cannot, do not, always, before) becomes a question citing its file and line; two that say opposite things about the same thing are a conflict, both places named. Code, headings and skill front matter are skipped |

`examples/import/rules/` holds an `AGENTS.md` and a skill that contradict each other on purpose
(push a release tag to `main` by hand: never, and always). An agent works from the questions
(`--questions` writes them as YAML) and proposes elements from the answers; nothing in the text
becomes a rule by itself (ADR-0041). Run it on this repository's own `AGENTS.md` to see about
fifty candidates and no conflict.

It reads only sentences with a binding word. An imperative without one ("Keep PRs small") is not
read; the interview asks for what the text leaves out. Some descriptive sentences ("these cannot
be enforced from the files") become questions too, which a person dismisses. Two rules conflict
when most of the shorter one's words are shared (`options: {overlap: 0.8}` in the profile);
after 100 conflicts the rest are counted.

## Several sources, one draft

`--into` joins another source to a draft. What the draft lacks is added, proposed and citing its
place. What it already says the same is left alone. What it says differently is a conflict that
names both places, and the draft's own is kept: nothing is overwritten.

```bash
uv run toprope-import openapi examples/import/orders.openapi.yaml --domain shop --out /tmp/shop.domain.yaml
uv run toprope-import sql examples/import/orders.sql --into /tmp/shop.domain.yaml   # adds Order.channel
```

## Into the change loop

`--patch FILE` takes an import through theme 1's loop instead of writing a file. The source
becomes a source of the workspace, so every element's citation resolves. A file inside the
workspace is registered where it is; anything else is kept as a snapshot under
`.toprope/imports/<id>/`. The elements, joined to the workspace's draft, become a patch for
`toprope-change`. A new workspace file is made when `--workspace` names none.

```bash
uv run toprope-import openapi api.yaml --domain shop --patch import.yaml --workspace toprope.shop.workspace.yaml
uv run toprope-run open_draft shop --domain-id shop --declaration shop.domain.yaml --branch work   # a new domain
uv run toprope-run add_source S-shop-openapi --kind repository --path api.yaml
uv run toprope-change "import from api.yaml" --patch import.yaml --workspace toprope.shop.workspace.yaml --draft shop
```

The command prints these next steps. `toprope-change` proposes each element, checks the working
copy and writes one human request. The person confirms from one diff (`toprope-run review`).

## Questions as records

`--questions` writes each question and conflict as a record an agent can act on:

```yaml
- id: Q-import-4a76571ed1
  kind: actor                       # actor, target, creation, call, stage, cell, rule, contradiction, ...
  text: Who may refund an order (refund_order)?
  decides: [actions.refund_order.actor]      # the paths an answer settles
  places: ["api.yaml#/paths/~1orders~1{id}~1refund/post"]
  # for a written rule also: quote (the sentence), modality (never, must, only, before), terms
```

`toprope-run ask_question <id> --stage import --text "<text>"` puts one in the interview.

## What the OpenAPI draft asks

An operation's effect is drafted only when its call is named, as `x-toprope-call: mcp:<tool>` on
the operation or `options: {calls: {refundOrder: mcp:refund_order}}` in the profile. Then the
action gets `call:` with every argument passed on, a reply action, and `undecided` cells for the
reply. Otherwise a question asks what carries the operation out. A thing that no operation creates
gets a question: how is it created?

A draft whose actions name only `unassigned` is not ready: no one may take them. `validate`
warns (`unassigned-actor`), and `toprope-harness` says so after its result.

An MCP server's tools are a source too (`toprope-import mcp "<command>"`): see
[`examples/proxy/`](../proxy/).

## Profiles

A team's conventions go in a profile instead of code (ADR-0051):

```yaml
# our-conventions.yaml
stage_fields: [phase]          # our stage field is `phase`
roles_from: x-roles            # an operation lists its roles under `x-roles`
rename: {refundOrder: give_money_back}
ignore: [createOrder]
```

`uv run toprope-import openapi api.yaml --profile our-conventions.yaml`. A new kind of source (a
Notion export, a Jira API) plugs in as a package with an entry point in `toprope.readers` or
`toprope.extractors`; `toprope-import --list` shows what is installed.

`tests/test_importers.py` checks that each draft parses, validates, and cites its sources.
`tests/test_import_loop.py` takes an import through the change loop.
