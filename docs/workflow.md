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
approve, deploy) can be done without your terminal (on your own machine, `toprope-apply` takes the
same request with one confirmation; see *A change in one command*): the agent commits a *human request*,
`.toprope/requests/<id>.yaml`, listing the steps; the `human-request` workflow shows them on
its run page and waits; you press **Approve and deploy** (web or the GitHub mobile app); the
steps then run as you, the person `toprope.identity.yaml` lists with your `github:` login,
and the result is pushed to the branch with the approver and the run in the commit. A request
that approves a commit runs `check_commit` on it first: the workflow installs TLC, so that check
model-checks the commit, and the kernel approves only a commit TLC passed (ADR-0044). One
change takes one request: `python tools/human_request.py change .toprope/requests/<id>.yaml
--draft <draft>` writes confirm, commit, check and approve, where the last two name `$commit`,
the commit the request's own commit step makes. So nobody predicts the commit's id. The run
is also appended to `.toprope/approval-runs.jsonl`, so a commit can cite it as evidence
(`cite_evidence --kind approval-run`) after any merge. A step that fails stops the run, and
the steps before it are kept: the workflow still pushes their work, notes the failed step in the
run's entry, leaves the steps from the failed one on in the request, and ends red. So a failed
preview leaves the commit approved (ADR-0050). What the failed step itself half wrote is undone
first; a step whose action was taken but whose follow-up failed counts as run and is not sent
again. Fix the cause and push a change to that request; its run takes only the steps that did
not run, numbered as in the first request. If a run ends red, do not re-run it (**Re-run jobs**); push a change to
the rest. A re-run would take the first request's steps again, so the workflow refuses it once the
branch has moved on. The
format is in `tools/human_request.py`. One-time setup (maintainer): Repository settings →
Environments → `researcher` → Required reviewers: you ("Prevent self-review" off); Actions →
Workflow permissions: read and write.

Install `uv` first (`brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh | sh`),
then `uv sync`. Every command runs from the repository root as `uv run <command>`.

## A change in one command (ADR-0049, C1)

An agent writes the elements a change proposes to a patch file and runs

```
uv run toprope-change "Drafts name their declaration" --patch change.yaml
```

It proposes each element, checks the working copy (on a scratch copy of the commit store), prints the diff a person will
confirm, and writes one human request (`.toprope/requests/<id>.yaml`). The person's one approval
confirms, commits, checks and approves, by either route: push the request and approve its run in
GitHub, or apply it at their own terminal (below). If a check fails, nothing is
requested, and the message says which check and how to fix it. A low-risk change (ADR-0050:
no widening, nothing removed, no invariant or rule changed, nothing about who takes a person-only
step) ships on the same approval: deliver, preview, deploy, the probes and verify, which runs only
if the probes pass. A high-risk change stops at approval; a second request ships it after the
preview. The steps one by one follow.

### Without GitHub: apply the request at your terminal (ADR-0053, 3)

```
uv run toprope-apply .toprope/requests/<id>.yaml           # one `yes`
uv run toprope-apply --ship .toprope/requests/<id>.yaml    # a high-risk change: up to its preview
```

`toprope-apply` shows the request exactly as the workflow's run page does (every step, the risk
and its reasons, the diff a confirm step confirms) and asks you to type `yes` once. It then runs
the steps as you (your git email in `toprope.identity.yaml`, as `toprope-run` finds you), with the
same runner as the workflow, records the run in `.toprope/approval-runs.jsonl` with `channel:
local`, and removes the request; commit the result with the logs it changed. F1 counts it as one
approval, as it counts an approved run in GitHub. Your one `yes` stands for each person-only
step's own prompt: `toprope-run` accepts a token from the apply that asked you, for you only, and
only while it runs. It refuses without a terminal (an agent's shell), and for a git email listed as
an agent or not listed. An approval needs TLC's check here too: set `TOPROPE_TLC_JAR` to a TLC jar.

A step that fails stops it, as in GitHub: the steps before it keep their work, the run is
recorded with the failed step, and the request keeps the steps that are left; fix the cause and
apply it again. A commit that is not recorded low risk is not put in use on the same `yes`
(ADR-0050, 3): the run stops after its preview, prints it, and leaves deploy, the probes and
verify in the request; apply it again once you have read the preview. With `--ship`, a request
that approves the commit it makes also carries that commit's delivery, so a high-risk change takes
two applies (approve and preview; then deploy and verify) and a low-risk one takes one.

## The self domains, end to end

```
R="uv run toprope-run"     # the options come from toprope.yaml (ADR-0049, C3)
$R open_draft authoring --domain-id authoring \
   --declaration domains/authoring/authoring.domain.yaml --branch work   # once per domain
$R next_questions authoring          # the current stage's questions
$R propose_element E-1 --path ... --origin S-1 --cites REF --value JSON
                                     # REF: a chunk ref, or words from the passage (B4)
$R review                            # what you are about to confirm, as one diff
$R confirm_all_proposed authoring    # you, on your terminal
$R commit_draft authoring            # `then` names the new commit <id>
$R check_commit <id>
$R approve_commit <id>               # you, on your terminal
$R deliver <id> --environment local  # hands off to Delivery
$R preview authoring:<id>:local
$R deploy authoring:<id>:local        # you, on your terminal
$R run_probes authoring:<id>:local    # the deployed commit, checked in use
$R verify authoring:<id>:local        # you, once its probes passed
```

- **Failed commands are recorded.** A command that fails before the gate (a usage error, a
  refused option, a crash) writes one file under `.toprope/failures/` (`failures:` in
  toprope.yaml); commit them too, so the friction of the loop can be measured (ADR-0049, F1).
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
