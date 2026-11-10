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
