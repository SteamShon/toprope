# Who does what, when: workflows and commands

Link: none (an operating guide). A short introduction. The commands themselves are generated:

- **What a domain's people and agents do** is in that domain's generated guide, section *How
  to work in this domain* (ADR-0036): every stage, who acts, what only a person may do, and
  the `toprope-run` command for each action. For the self domains:
  [`domains/authoring/guide.md`](../domains/authoring/guide.md) (build and change a domain) and
  [`domains/delivery/guide.md`](../domains/delivery/guide.md) (deliver a commit).
- **The kernel's own commands**, the same for every domain (`toprope-run`, `toprope-server`,
  `toprope-harness`, `toprope-worldmap`, `toprope-commits`), are in
  [`kernel-commands.md`](kernel-commands.md), generated from their argument parsers.

Since the switch-over (ADR-0037), nothing but the kernel is hand-built: authoring and
delivering a domain are actions of the Authoring and Delivery domains, which are declarations
too ([`charter.md`](charter.md)).

**Who.** *Owner*: the person who owns a domain (in M1, the researcher). *Agent*: an AI agent
working for the owner (for example Claude Code, through the generated MCP server or
`toprope-run`). *Maintainer*: whoever releases. Some actions are **a person only**
(`requires: human`): an agent never takes them, even when told the owner agrees in chat
(probe P01: "the agent does not decide on its own").

**You, on your machine.** `toprope-run` knows who you are from your git email
(`git config user.email`), looked up in [`toprope.identity.yaml`](../toprope.identity.yaml):
each person's roles, and each agent's own git email with the person it works for and a grant
of what it may draft. No token is needed; `toprope-run ... whoami` shows the result. A git
email is self-asserted, and an agent on your machine has your git email, so this trusts the
processes on your machine; an `agents` entry applies to an agent with its own git email (for
example in its own container). As a guard against mistakes, an action only a person may take
also asks you to confirm on your terminal, which an agent's ordinary shell cannot do.

**From a cloud session (ADR-0039).** What only you may do (freeze an instrument, confirm,
approve, deploy) can be done without your terminal: the agent commits a *human request*,
`.toprope/requests/<id>.yaml`, listing the steps; the `human-request` workflow shows them on
its run page and waits; you press **Approve and deploy** (web or the GitHub mobile app); the
steps then run as you, the person `toprope.identity.yaml` lists with your `github:` login,
and the result is pushed to the branch with the approver and the run in the commit. A request
that approves a commit runs `check_commit` on it first: the workflow installs TLC, so that check
model-checks the commit, and the kernel approves only a commit TLC passed (ADR-0044). The run
is also appended to `.toprope/approval-runs.jsonl`, so a commit can cite it as evidence
(`cite_evidence --kind approval-run`) after any merge. The
format is in `tools/human_request.py`. One-time setup (maintainer): Repository settings →
Environments → `researcher` → Required reviewers: you ("Prevent self-review" off); Actions →
Workflow permissions: read and write.

Install `uv` first (`brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh | sh`),
then `uv sync`. Every command runs from the repository root as `uv run <command>`.

## The self domains, end to end

```
R="uv run toprope-run --composition domains/toprope-self.composition.yaml --kernel-root . \
   --workspace toprope.authoring.workspace.yaml --env .toprope/env"
$R --member authoring open_draft authoring --domain-id authoring \
   --declaration domains/authoring/authoring.domain.yaml --branch work   # once per domain
$R --member authoring next_questions authoring          # the current stage's questions
$R --member authoring propose_element E-1 --path ... --origin S-1 --cites REF --value JSON
$R --member authoring confirm_all_proposed authoring    # you, on your terminal
$R --member authoring commit_draft authoring            # `then` names the new commit <id>
$R --member authoring check_commit <id>
$R --member authoring approve_commit <id>               # you, on your terminal
$R --member authoring deliver <id> --environment local  # hands off to Delivery
$R --member delivery preview authoring:<id>:local
$R --member delivery deploy authoring:<id>:local        # you, on your terminal
$R --member delivery verify authoring:<id>:local --verified true
```

- **Commit what changed.** Each domain's events go to its own append-only log,
  `domains/<domain>/events/`, and its commits, approvals and check records to
  `.toprope/commits/<domain>/`; commit both with your change, so decisions are shared and
  audited. The declaration's example objects never go into a log: `--seed` needs
  `--store memory` (which keeps nothing) or `--store-dir`.
- **Your agent's tools** are the generated MCP server:
  `claude mcp add toprope-authoring -- uv run --directory <repo> toprope-server --composition
  domains/toprope-self.composition.yaml --member authoring --kernel-root . --workspace
  toprope.authoring.workspace.yaml --identity static:<tokens file>`, with `TOPROPE_TOKEN` set
  in its environment. The tokens file maps a token to the agent and the person it works for,
  as `toprope.identity.yaml` does by email: `t-claude: {id: claude, kind: agent, roles: [owner],
  on_behalf_of: {id: "you <you@example.com>", roles: [owner]}, grant: {id: drafting, actions:
  [...]}}`. Keep it out of git.
- **Read the history** with `toprope-commits`: `branches`, `log` (an element's history),
  `diff`, `checks`, and `deployed` (what an environment runs).
- **A new domain** gets a workspace file (`toprope.<domain>.workspace.yaml`: the declaration
  path, the interview log and the sources; see the self domains' files), then `open_draft`.

## Experiment instruments (researcher)

| Step | Who | Command |
|---|---|---|
| Validate | researcher (an agent with `--sealed`) | `python experiments/tools/instruments.py validate experiments/m1/instruments [--sealed]` |
| Freeze | **researcher**, or an agent on their explicit instruction | `… freeze experiments/m1/instruments` |
| Amend a frozen file | **researcher**, or an agent on their explicit instruction | `… amend experiments/m1/instruments FILE --reason "..."` |
| Check before a run | the harness | `… verify experiments/m1/instruments [--run]` |

Prefix each with `uv run --with pyyaml`. Content rules are in AGENTS.md.

## Repository work (everyone)

| Step | Who | How |
|---|---|---|
| A change | anyone | a branch from `develop`, a PR to `develop` (AGENTS.md) |
| Merge | **maintainer**, or an agent when asked | squash; an umbrella with a merge commit |
| Release | **maintainer** | PR `develop` → `main` titled `Release vX.Y.Z`, merge commit, then tag `main` |
