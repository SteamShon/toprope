# ADR-0046: Where a domain says so, the author does not approve

- Link: ① iterate safely, ③ works as built · Status: accepted · 2026-11-07 · decided by:
  SteamShon (the recommendation; drafted by the assistant)
- Builds on: the charter §5 (no self-approval), ADR-0032 (one approver in M1), ADR-0033
  (approving merges into `main`), ADR-0045 (the self domains run their deployed commit)

## Context
The charter says no self-approval. `approve_commit` checked only that a person approves a commit
whose checks passed, so a commit's author could approve it. In M1 each self domain has one
owner, the researcher, who both commits (through human requests) and approves: enforcing the
rule now would stop the self domains' loop. A domain with several owners (M2) needs it.

## Decision
1. **A domain opts in.** A declaration may set `approval: {distinct_from_author: true}`. It is
   off by default.
2. **The commit store enforces it,** on every path an approval takes (the kernel's
   `approve_commit`, the workspace, any tool): the commit's author may not approve it. A commit
   that names no author is refused, since its approver cannot be told apart from it.
3. **The rule in force is `main`'s.** It is read from the domain's approved `main`, so a commit
   cannot switch it off to approve itself; before the first approval, from the commit itself.
4. **The self domains keep it off in M1,** and turn it on with a second owner.

## Consequences
- Turning the rule on is itself a change someone else must approve after it lands, since it
  applies from the next approval on.
- Authors are the commit's recorded `author` (the caller's id); an approver is the person's id.
  Both are actor ids, so the comparison is exact.
