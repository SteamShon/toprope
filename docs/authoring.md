# Authoring: sources, drafting and the interview

Link: ① ②. M0a's authoring tools (ADR-0014, ADR-0017). Your own agent (for example Claude
Code) drafts a declaration from sources and interviews you through the authoring MCP. M1
Phase A runs on them.

```bash
uv run toprope-author init .                     # writes toprope.workspace.yaml
claude mcp add toprope-authoring -- uv run --directory /path/to/toprope toprope-author serve --workspace "$PWD"
uv run toprope-author progress                   # where each stage stands
uv run toprope-author questions                  # the current stage's bundle
uv run toprope-author fetch                      # fetch link sources into snapshots
uv run toprope-author confirm actions.approve    # only you confirm
uv run toprope-author check                      # validate + model-level harness on the draft
```

## Workspace (`toprope.workspace.yaml`)
- `domain`: the draft declaration it writes.
- `sources`: each has an `id`, a `kind` (`repository`, `records`, `transcripts`,
  `interview-log`), a `path`, and optionally `globs`, `exclude` and `local_only`.
- `interview_log` and `usage_log`: JSONL files.
- Optional: `budget_minutes` (the stop rule), `event_store` (recorded attempts raise
  question priority), `redact` (extra patterns) and `exclude`.

## Sources
- **Chunks and refs.** Readers split each source into chunks with a stable ref,
  `<source>:<path>#L<a>-L<b>`:
  - code in 120-line blocks
  - markdown by heading
  - transcripts one message per chunk (Claude Code JSONL)
  - the interview log one entry per chunk
- **Redaction.** Every chunk is redacted before anyone reads it. Secrets are keys, tokens,
  private keys, JWTs, bearer tokens and password assignments. Personal data is emails,
  phone numbers and resident registration numbers. Matches become `[REDACTED:<kind>]`.
- **Local-only** sources are listed with their chunk count, but their content is never
  served, so it never reaches a hosted model.
- **Never read:** `experiments/**` (the held-out gold, its key, and the guides that show
  what the gold probes), plus `.git`,
  `.venv`, `node_modules`, symlinks, files outside the workspace, and binary or large files.
- **Usage log.** Every chunk served is recorded there, so the drafter records which sources
  it used.

## Rules the tools enforce
- **Every drafted element cites a real chunk.** `propose` refuses a ref that
  `read_source` or `search_sources` would not return. The element records `source.kind`
  (`system`, `record` or `interview`), the ref and an optional quote.
- **Agents write only `proposed`.** A `confirmed` status anywhere in a proposed value is
  demoted.
- **The draft is written only if it still parses.** Validation issues (unknown role,
  missing cell, and so on) are returned, not hidden.
- **An answer is recorded in the owner's words** (`answer`) in the interview log. Its
  decisions become proposed elements that cite that log line, and the line is itself
  citable afterwards.
- **Only a person confirms**, through one of two channels. Each confirmation is logged with
  its channel (`via`):
  - `toprope-author confirm` on the owner's terminal. It prompts, or takes `--yes` when you
    run it yourself; without a terminal and without `--yes` it is refused.
  - the MCP `confirm` tool, which shows the owner an elicitation prompt in their client and
    confirms only on acceptance. A client that cannot show one is refused.

## Stages (ADR-0025, proposed)
The interview runs in nine stages, in the order the declaration's parts depend on:

`sources → purpose → cast (roles, objects, links) → actions → transitions → invariants →
world (fixtures, scenarios) → handoffs → review (confirmations, glossary)`

- **One stage at a time.** `questions` returns the **current stage's bundle**: conflicts
  first, then what is missing. The current stage is the first one not done, so a later
  break sends the interview back.
- **Each round.** For the current stage, the agent:
  1. drafts what the sources support (citing them)
  2. asks the whole bundle at once
  3. shows `progress`: every stage as done, current, todo or skipped, with counts
  4. records the owner's answer with `answer(bundle_id, ...)`
- **Skipping.** `skip_stage` records, in the owner's words, that an optional stage
  (invariants, handoffs) has nothing.
- **Link sources.** A source may be a link, `{id: wiki, kind: records, url: ...}`.
  `toprope-author fetch` (or the MCP tool `fetch_source`) fetches it once into
  `.toprope/snapshots/<id>/`. From there it is read and redacted like a file. A page behind
  a login cannot be fetched: download it and give its path.

## Questions within a stage (ADR-0014)
Inside a bundle, conflicts come first. In the transitions stage, ADR-0014's question kinds
apply, highest priority first:
1. **Defaults**: one question per action with two or more undecided cells, such as "In
   which states can someone approve a drafted experiment at all?". The answer settles the
   whole column.
2. **Grouped rows**: one question per state with undecided cells.

Purpose comes from its own stage, and confirmations from the review stage.

Priority comes from attempts recorded in the event store (×100), then risk (an action with
effects or a decision record, ×10), then how many cells the answer decides. The **stop
rule**: stop when no undecided cell has been attempted or leads to an effect, or when the
time budget is spent. Remaining undecided cells deny by default and stay listed.

## Limits in M0a
- Attempts are attributed to the action, not the cell, because attempt events do not
  record the state they were made in.
- Candidate invariants are not generated as questions yet.
- Writing the draft drops YAML comments.
- A bare `n/a` or `undecided` cell carries no provenance in schema v1. The interview log
  records where it came from.
