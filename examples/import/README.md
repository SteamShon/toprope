# Example: start a declaration from what a team already has

Link: none (an example for ADR-0049, A1a). Three sources a team often has, and the proposed
draft `toprope-import` makes from each. Every element it writes is `proposed`, citing the exact
place it came from; a person confirms what is right, and the interview asks what the source
cannot say (who may take each action, what each stage allows).

```bash
uv run toprope-import openapi examples/import/orders.openapi.yaml --domain shop --out /tmp/shop.domain.yaml
uv run toprope-import sql examples/import/orders.sql --domain shop --out /tmp/shop-db.domain.yaml
uv run toprope-import workflow examples/import/support.workflow.json --domain support --out /tmp/support.domain.yaml
```

| Source | Becomes |
|---|---|
| OpenAPI schemas | things and their facts; an `enum` named `status`, `state` or `stage` also becomes the thing's stages |
| OpenAPI POST, PUT, PATCH, DELETE | actions with typed inputs from the request body (a GET changes nothing) |
| SQL `CREATE TYPE … AS ENUM`, `CHECK (… IN …)` | enum facts of the table's thing |
| a workflow export (`statuses`, `transitions` with `from`, `to`, `name`) | stages, actions, and a cell for each allowed move; every other cell stays `undecided`, for the interview |

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
