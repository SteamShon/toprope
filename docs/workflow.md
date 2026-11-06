# Who does what, when: workflows and commands

Link: none (an operating guide). This page lists every command Toprope has, in the order you
use them, with who runs each step. Until the M1 switch-over (ADR-0022), these hand-built
commands are how Authoring and Delivery are done; afterwards the same steps are actions of the
generated Authoring and Delivery domains (`domains/*.guide.md`).

**Who.** *Owner*: the person who owns a domain (in M1, the researcher). *Agent*: an AI agent
working for the owner (for example Claude Code, through the authoring MCP or the CLI).
*Maintainer*: whoever releases. Some steps are **owner only**: an agent never runs them, even
when told the owner agrees in chat (probe P01: "the agent does not decide on its own").

Every command runs from the repository root as `uv run <command>`. Install `uv` first
(`brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh | sh`), then `uv sync`.
With several domains in one repository, name the workspace file: `--workspace
toprope.authoring.workspace.yaml`.

## 1. Build a domain: the staged interview (ADR-0025)

| Step | Who | Command | What happens |
|---|---|---|---|
| Set up a workspace | owner or agent | `toprope-author init` | writes `toprope.workspace.yaml`: the declaration path and the sources |
| Connect your agent | owner | `claude mcp add toprope-authoring -- uv run --directory <repo> toprope-author serve --workspace <file>` | the agent gets the authoring tools (read sources, propose, answer, questions) |
| Fetch link sources | agent | `toprope-author fetch [SOURCE]` | a link is snapshotted once |
| See where it stands | anyone | `toprope-author progress` | each stage: done, current, todo |
| Get the current questions | agent | `toprope-author questions [--stage NAME]` | the bundle for the current stage, conflicts first |
| Draft from sources | agent | (authoring MCP `propose`) | elements are `proposed`, each citing a real source chunk; system first, then records, then the interview |
| Answer | **owner** | in chat; the agent records it with MCP `answer` | your words go to `interview/…/log.jsonl`; their decisions become proposed elements citing that line |
| Skip an optional stage | **owner** | `toprope-author skip STAGE --reason "..."` | invariants or handoffs can be empty, on the record |
| Check the draft | anyone | `toprope-author check` | parses, validates, runs the model-level harness |
| Read the domain | anyone | `toprope-worldmap --domain D --out wm.json --harness --guide D.guide.md` | the domain guide: purpose, actions, matrix, what is generated |
| Confirm | **owner only** | `toprope-author confirm PATH... [--yes]`, or `confirm --all-proposed` | marks elements `confirmed`; logs who (your git identity) and how. `--all-proposed` lists every element still proposed (objects, links, actions, preconditions, matrix cells, invariants, handoffs) and asks once |

Stages, in order: sources → purpose → people and things → actions → transitions →
invariants → examples and scenarios → handoffs → review (confirm, glossary). See
[`domain-model.md`](domain-model.md) for what each part is.

## 2. Change a domain: commits, checks, approval (ADR-0029, ADR-0032, ADR-0033)

| Step | Who | Command | What happens |
|---|---|---|---|
| Edit the working copy | agent (owner answers) | the interview, as in §1 | |
| Commit | owner or agent | `toprope-author commit -m "..." [--branch B]` | an immutable commit on a branch (`work` by default); reports what to re-confirm since the merge base |
| See what changed | anyone | `toprope-author diff [FROM] TO` | the semantic diff: changed, added, removed elements |
| Check the change | owner or agent | `toprope-author change-check [COMMIT] [--env DIR] [--full]` | structural, semantic, scenarios, harness (examples and mechanical), log replay, in-flight, NL; recorded on the commit; exits 1 on failure |
| Re-confirm what changed | **owner only** | `toprope-author confirm --all-proposed` | only directly changed elements need it |
| Approve | **owner only** | `toprope-author approve COMMIT [--yes]` | merges into the protected `main` and tags it; refused on conflicts |
| Resolve conflicts | agent drafts, **owner** decides | `toprope-author merge [--branch B]`, then `commit --merge MAIN` | writes the merge into the working copy and lists conflicts by element |
| History of an element | anyone | `toprope-author log ELEMENT [--at C]` | who changed it, when, citing what |
| Go back to a commit | owner | `toprope-author checkout COMMIT [--force]` | loads it into the working copy; committing it is the revert |
| Branches | anyone | `toprope-author branches` | every branch and its commit |

## 3. Deliver a commit (ADR-0022, ADR-0029)

| Step | Who | Command | What happens |
|---|---|---|---|
| Preview | owner or agent | `toprope-deploy --env ENV --commits .toprope/commits preview DOMAIN COMMIT` | builds artifacts, runs the harness, writes `world-map.json` and `domain-guide.md`; changes no environment |
| Review what the deploy changes | **owner** | `toprope-author diff DEPLOYED COMMIT` | every change since the last deploy (probe P06) |
| Deploy | **owner only** | `toprope-deploy … deploy DOMAIN COMMIT --approver NAME` | under the fixed floor: approved on `main`, newest, harness passed, a person, nothing stranded |
| Status | anyone | `toprope-deploy --env ENV status` | the deployed commit and every attempt |
| Serve the deployed domain | owner | `toprope-server $(toprope-deploy --env ENV server-args) --identity FILE` | the generated MCP server for people and agents |
| Verify in use | **owner** | try it; the probes | a deploy that happened, checked by a person |

## 4. Inspect and test

| Command | What it does |
|---|---|
| `toprope-harness --domain D [--levels model,execution,mcp]` | the full harness: example cells, invariants, flows, exploration, races, and the mechanical layer (ADR-0035) |
| `toprope-harness --composition C [--regen-check]` | a system of domains: wiring, each member, and the regeneration check (ADR-0028) |
| `toprope-worldmap --domain D --out wm.json [--mermaid DIR] [--guide FILE]` | the world map, diagrams and the domain guide |

## 5. Experiment instruments (researcher)

| Step | Who | Command |
|---|---|---|
| Validate | researcher (an agent with `--sealed`) | `python experiments/tools/instruments.py validate experiments/m1/instruments [--sealed]` |
| Freeze | **researcher**, or an agent on their explicit instruction | `… freeze experiments/m1/instruments` |
| Amend a frozen file | **researcher**, or an agent on their explicit instruction | `… amend experiments/m1/instruments FILE --reason "..."` |
| Check before a run | the harness | `… verify experiments/m1/instruments [--run]` |

Prefix each with `uv run --with pyyaml`. Content rules are in AGENTS.md.

## 6. Repository work (everyone)

| Step | Who | How |
|---|---|---|
| A change | anyone | a branch from `develop`, a PR to `develop` (AGENTS.md) |
| Merge | **maintainer**, or an agent when asked | squash; an umbrella with a merge commit |
| Release | **maintainer** | PR `develop` → `main` titled `Release vX.Y.Z`, merge commit, then tag `main` |
