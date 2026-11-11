# Domain guide: `library` (version 2)

_Generated from the declaration at build time. Do not edit: change the declaration._

## Purpose

Members borrow the library's books, and nobody can tell who has which.

**Success metric:** share of lent books with a known borrower (up is better)

> Every lent book now has a borrower on record.

## People and things

**Roles:** `librarian`. Agents act only on a person's behalf, with a grant.

- **Book**: A book the library lends. Stages: `shelved`, `lent` (starts `None`).
  - facts: `title` (string), `borrower` (string, optional)

## Actions

🔒 only a person may take it · 📝 recorded as a decision

| action | who | on | needs first | changes | starts | event |
| --- | --- | --- | --- | --- | --- | --- |
| `lend` | librarian | **Book**; params `borrower` (string) | — | the stage (per the matrix); `target.borrower` ← `params.borrower` | — | `BookLend` |
| `take_back` | librarian | **Book** | — | the stage (per the matrix) | — | `BookTakeBack` |
| `renew` | librarian | **Book** | — | the stage (per the matrix) | — | `BookRenew` |

## Transitions

For each stage: may the action happen, and where does it lead? A missing cell is undecided; nothing is ever silently allowed.

### Book (`stage`)

| stage | `lend` | `take_back` | `renew` |
| --- | --- | --- | --- |
| `shelved` | → `lent` | denied: The book is on the shelf. | **undecided** |
| `lent` | denied: The book is lent already. | → `shelved` | **undecided** |

**Undecided cells (2):** `Book.shelved.renew`, `Book.lent.renew`

## Examples and scenarios

- 1 example object(s): Book `B1`

## How to work in this domain

Generated from the actions, their actors, the matrix and the kernel calls: for each thing, how it comes to exist, then what can happen in each stage and who does it. Steps marked **a person only** are never taken by an agent.

### Book


**In `shelved`:**

- **lend** by `librarian` → `lent`. Run: `toprope-run --domain library.domain.yaml lend ID --borrower BORROWER`

**In `lent`:**

- **take_back** by `librarian` → `shelved`. Run: `toprope-run --domain library.domain.yaml take_back ID`

### Other actions

- **renew** by `librarian`. Run: `toprope-run --domain library.domain.yaml renew ID`

## What is generated

- **Command line** `toprope-run --domain library.domain.yaml ...`: one subcommand per action, with the same rules as every other surface (ADR-0036), plus `get`, `history`, `allowed` and `guide`.
- **MCP server** `toprope:library`: one tool per action (3), plus `get_object`, `history`, `attempts`, `allowed_actions`, `describe_domain`, `world_map` and `how_to_reach`.
- **Events**: one per action (`BookLend`, `BookRenew`, `BookTakeBack`); the current state is the events replayed in order.
- **World map** (`world-map.json`): every object, link, stage and (stage, action) edge.
- **Harness**: passes; decided cells covered per level: model 4/4, execution 4/4; 0 finding(s).
