# ADR-0032: Domain knowledge managed the way git and GitHub manage code

- Link: ① iterate safely, ④ shared language, ⑤ evolves · Status: accepted · 2026-11-05 · decided
  by: the assistant, on the researcher's delegation ("close what can be closed"); the
  researcher may reopen any item
- Builds on: ADR-0029 (commit log, approval tags, semantic diff), ADR-0025 (staged interview),
  ADR-0028 (kernel services)

## Context
The researcher's framing: Domain Authoring is to domain knowledge what git plus GitHub
pull requests are to code. ADR-0029 adopted git's core: commits, tags and diff. This ADR
checks the rest of the git and GitHub model against Toprope, and closes the choices that do
not need the researcher.

## The mapping

| git / GitHub | Toprope | Status |
|---|---|---|
| repository | a domain (a composition is a monorepo of domains, ADR-0026) | exists |
| working tree | the working copy, one per domain in M1 | exists |
| staging area (`git add -p`) | none: a commit snapshots the whole working copy | **closed: not needed** (the semantic diff already shows what changed) |
| commit, message, parents | immutable commit, message, parents as a list | exists |
| commit author | who compiled the commit | **closed: add** (recorded on the commit) |
| diff | the semantic diff by element (review hash) | exists |
| `git log -- path`, `git blame` | an element's history: the commits that changed it, with the source and answer it cites | **closed: add** an element log |
| `git checkout <commit>` / `git revert` | load a commit's content into the working copy, then commit (a revert is a new commit) | **closed: add** a `checkout` kernel service and CLI command |
| branch, merge | branches from the start (ADR-0033) | proposed |
| tag, release | approval tag; an environment ref to the deployed commit | exists |
| pull request | no separate object: the review is the range from the last approved commit to the head, with its change report | **closed** (see 1) |
| review comment on a line | a question attached to an element of a commit, answered in the interview | **closed** (see 2) |
| "review requested" | a decision request in the responsible person's outbox (probe P01) | **closed** (see 3) |
| required status checks (protected branch) | the change check and the harness, recorded on the commit | **closed: add** check records (see 4) |
| CODEOWNERS, required reviewers | the domain owner approves; per-element ownership later | **closed for M1** (see 5) |
| issues | questions, unknowns and proposals (proposals mined from history in M4, ⑤) | exists as vocabulary |
| Actions / CI | kernel services called by declared effects (ADR-0028) | exists |
| fork, upstream, cherry-pick | reuse of domains across organizations; later | out of scope |

## Decisions closed here
1. **No pull-request object.** With one working copy and no branches, a "pull request" is
   the range from the last approved commit to the head, its semantic diff (`to_review`),
   its change report and its check records. Approving the head tag-approves that range.
   This keeps ADR-0029's no-states rule: nothing is open, merged or closed.
2. **Review comments are questions.** A reviewer's comment attaches to an element key and a
   commit. It becomes an interview question; its answer and the resulting change make the
   next commit. This needs no new mechanism.
3. **Review requests are decision requests.** An agent that reaches a decision only a
   person may take proposes it, with grounds and a recommendation. It sends a decision
   request to that person's outbox and waits, and all of it is recorded (probe P01). The
   request object and its flow are part of the Authoring declaration (Phase A). They are
   not kernel.
4. **Checks are recorded on commits.** Each run of the change check and the harness on a
   commit appends a check record (commit, check, ok, summary) to the commit store,
   append-only, like approvals. The Authoring declaration decides whether approval requires
   green checks; the recommended default is yes, as a protected branch would. The deploy
   floor already requires a passing harness. Implemented with sub-PR 8 (the change check).
5. **One approver in M1.** The domain owner approves. Per-element ownership and required
   reviewers, the CODEOWNERS analogue, wait until a domain has more than one owner (M2 or
   later).
6. **Small additions to the commit store**, implemented next:
   - the commit's author
   - an element log
   - `checkout`

## Resolved (researcher, 2026-11-05)
- **Sources connect through MCP.** Connectors for operational databases and models,
  BigQuery, papers, Notion, Jira, Linear and others come in as MCP clients of existing MCP
  servers. Toprope's Source port still applies redaction, local-only and citation refs to
  everything read through them. The port's detail gets its own ADR when it is built (M0b).
- **Branches from the start** (ADR-0033) replace this ADR's "branch, merge: M2" row.
