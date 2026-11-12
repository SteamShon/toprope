# M2: the spec, on the researcher's paper trading

Link: ③ works as built, judged; ① iterate safely, a provisional result; ② the model is right,
observed only (ADR-0054). **Status: decided, not frozen.** The assistant drafted this at the
researcher's request ("M2 스펙 PR 초안 작성해줘", 2026-11-12), and the researcher decided every
draft as recommended ("추천대로", 2026-11-12), except the grader's open items (§10). The values
below are frozen in the preregistration (§3, step 2) before any check runs. Until then the
researcher may still change them. Progress is in [`STATUS.md`](../STATUS.md).

Builds on:
- [`M2-design.md`](M2-design.md): the arms, the measures and the draft verdict rules;
- [`M2-grader.md`](M2-grader.md): the grader, as decided and validated;
- ADR-0054: the domain, the roles and the isolation.

**What this spec does not hold.** M2's instruments are human-only (AGENTS.md), and this spec
holds none of their content. They are written by the researcher:
- the change requests, the seeds and the key;
- the probes;
- the experiment's binding;
- the held-out items for ②.

The verdict rules, thresholds and the draw's shares were drafted by the assistant and decided by
the researcher. The researcher freezes them before the checks run.

## 1. The domain and its system

| Item | Value | |
|---|---|---|
| Domain | The researcher's own investing in US stocks | decided (ADR-0054) |
| Account | Alpaca paper trading. No live account is connected | decided (ADR-0054) |
| How the tool reaches it | Alpaca's official MCP server (`alpaca-mcp-server`), behind `toprope-proxy` (ADR-0052) | decided (ADR-0054) |
| Who places an approved order | **The agent, through the gated call.** The proxy sends the order only after the gate allows it, and records the reply. The researcher does not place orders by hand during ③'s window | decided (2026-11-12, "추천대로") |
| Where the declaration starts | The researcher's interview (`toprope-interview`). It may import the server's tools first (`toprope-import mcp`), which drafts the actions and the proxy's binding as `proposed`. The researcher confirms every element, and confirms the binding with `toprope-proxy --confirm-binding` | decided (ADR-0054 §5) |

What the domain contains (its states, actions, rules and outcome rules) is not set here. It comes
from the interview.

### Paper only, enforced (ADR-0054, open question 5)
A rule in a document is skipped by the first agent that does not read it (AGENTS.md). **Decided:** a
check refuses to start M2's proxy unless all of these hold:
- the upstream's environment sets `ALPACA_PAPER_TRADE` to true, and does not set it to false;
- the binding names the paper server only;
- the key in use is a paper key.

**Built** (M2's setup PR): `experiments/tools/m2_paper.py`. M2's proxy is started only through
`m2_paper.py serve -- <toprope-proxy arguments>`. It reads the arguments with the proxy's own
parser, so it checks the binding the proxy will load, and runs the proxy only after the check
passes. The check requires all of these:
- the upstream command is exactly `[uvx, alpaca-mcp-server==X.Y.Z]`: the official server, pinned;
- the binding's `env` is exactly `ALPACA_PAPER_TRADE: "true"`;
- `pass_env` is exactly the two keys. `pass_env` is a proxy feature added for this: the binding
  names a variable, and its value comes from the proxy's environment, so no key is written in the
  binding;
- the key ID is a paper one (it starts with `PK`), as a second guard.

Each refusal names its fix. The tests show the check refusing a binding that turns paper trading
off, wrapper commands, unpinned or git-sourced servers, and a second `--binding`.

## 2. Roles

| Role | Who | Does |
|---|---|---|
| Expert, owner | the researcher | answers the interview, confirms the declaration, writes the probes and the held-out items for ② |
| Seeder | the researcher, with the draw choosing | writes each drawn problem into its change request; keeps the key outside the repository |
| User (③) | the researcher | trades or checks every US trading day with the generated tool, and keeps the diary and the defect log |
| Builder | the researcher and the assistant | the tool, the harness, the grader, the draw tool, the paper-only check; no instrument content |
| Grader's sample | the researcher | labels a random sample of the pilot's flags blind, with the grader's checklist (M2-grader) |

## 3. Phases and order

1. **Setup** (builder). Build the paper-only check and the draw tool (§5); done in the setup PR.
   Record the Toprope revision that M2's checks run on.
2. **Preregistration** (the researcher freezes):
   - the checks' revision;
   - the verdict rules (§7);
   - the draw: the types, the shares, the number of requests, and the salt's hash (§5);
   - the run protocol, carried from M1's protocol;
   - ③'s thresholds;
   - the grader: its checklist, the majority, the noise limit, the expert sample's size and
     minimum agreement, and its model (M2-grader).
3. **Held-out items for ②** (the researcher, before the interview). The researcher writes them
   alone, from `experiments/m2/heldout.template.yaml`, into a file outside the repository
   (`~/m2-private/heldout.yaml`). The project's `.claude/settings.json` denies agents' Read and
   Edit of `~/m2-private/**`. `experiments/tools/m2_heldout.py validate` checks the format and
   prints counts only. `seal` writes `experiments/m2/heldout.sealed.json`: the file's sha256 and
   the item ids. The researcher commits that record before the interview starts. After Phase A,
   `unseal` copies the file in for scoring, but only if its hash is the sealed one.
4. **Phase A** (the researcher). The interview, with the agent drafting and the researcher
   confirming. The declaration is approved and deployed, and the proxy's binding is confirmed.
   The probes are written and frozen before ③'s window starts.
5. **③'s window** (the researcher). Daily use, with the diary and the defect log (§4). Live
   changes to the declaration go through the change loop (`toprope-change`, `toprope-apply` or a
   human request).
6. **Phase B** (the researcher, then the harness):
   - The change requests are taken from the diary, in order.
   - Each request's text is frozen (hashed) before the draw.
   - The draw decides each seed, and the researcher writes the seed in.
   - The key is sealed.
   - The dry run is two changes. Then the three arms run the sequence, starting from the
     declaration as deployed when the window closed.
7. **Scoring and report.** Only the scorer opens the key, after every arm has run every change.
   The salt is revealed, so anyone can check the draw. The report gives ③'s verdict, ①'s
   provisional result with its limits, and ②'s observation.

## 4. ③'s window and the diary

- **Length** (ADR-0054, open question 3), **decided:**
  - at least 10 US trading days (two weeks);
  - it ends once the diary holds the number of change requests the draw needs (§5), or after 30
    trading days, whichever comes first.
- **Daily use.** On every US trading day, the researcher does at least one of these:
  - approves or refuses a proposed order;
  - reads back a fill;
  - checks the positions against the rules.

  A missed day is recorded, not made up later. **Decided:** ③ needs at least 80% of the window's
  trading days used.
- **The time difference.** An order proposed and approved in the Korean daytime waits for the US
  open. Its fill, part fill or cancellation is read back the next morning. That reading-back is
  the brownfield effect ③ tests.
- **The diary** (`experiments/m2/diary/`, written by the researcher):
  - One entry per rule change the researcher actually wants, in their own words, dated.
  - An entry is written when the wish arises. It is not rewritten later.
  - The diary is the only source of Phase B's change requests.
  - A wish that was applied live during the window still counts. Phase B starts from the
    window's final declaration, so such a request is turned into a change against that version.
    How is decided in the run protocol.
- **The defect log** (`experiments/m2/defects.jsonl`): one line per defect, with its class from
  the roadmap:
  - state-permission;
  - UX;
  - performance;
  - external API;
  - hand edit to generated code.

  Defects in Alpaca's server or API are logged as external API, apart from Toprope's own.

## 5. The draw (ADR-0054 §3)

**Format.** The draw tool is `experiments/tools/m2_draw.py`, built in the setup PR. It is a
format change and holds no content. Two secrets do two jobs:
- **A public beacon stops the researcher from choosing.** The draw mixes in a drand round
  (`quicknet`) published an hour after the bases reach `develop`. Nobody knows that round when the
  bases are frozen. So no wording of a request can be tried until it draws a type the researcher
  wants. An adversarial review found that a salt alone allowed that.
- **The salt keeps the key sealed.** The beacon and the bases are public, so without a secret
  anyone could compute the types.

The steps:
1. `make-salt` makes the salt on the researcher's machine. It refuses a path inside the
   repository.
2. `salt-hash` prints the salt's hash. It goes into `experiments/m2/draw.yaml`, copied from
   `draw.template.yaml`, with `status: frozen`. That file is merged into `develop`.
3. `freeze-bases` records each request's `intent` hash in `experiments/m2/draw-bases.json`. It
   runs once, before any seed is written, and its output is merged into `develop`. From then on
   `intent` never changes, and the seeded wording goes in `seeded_intent`.
4. `draw` reads both files as `origin/develop` holds them. It refuses unless:
   - each file was added there once and never changed since;
   - the working copy matches;
   - `draw.yaml` is frozen and landed no later than the bases;
   - the salt matches its hash;
   - at least 12 requests are frozen;
   - the beacon round is out.

   It prints the commits, the round and each request's type, to the researcher only. The types
   are part of the key and are sealed with it.
5. For request `seq`, with base hash `h` and beacon randomness `r` (the sha256 of the round's
   signature): `u = int(sha256(salt ‖ 0x00 ‖ r ‖ 0x00 ‖ seq ‖ 0x00 ‖ h)) / 2^256`. The value `u`
   picks the type by the cumulative shares below, in their order.
6. After scoring, the salt is published, and `verify` recomputes every draw. It also checks:
   - the fallback, against the key. Each entry holds `seq`, `drawn`, `type` and
     `not_applicable`, and each `not_applicable` entry has a `why`;
   - that every `intent` still matches its base.

   It lists every not-applicable reason, for the report.

**Types and shares** (ADR-0054, open question 2), **decided:**

| Type | Share | What the researcher writes into the request |
|---|---|---|
| none (clean control) | 0.30 | nothing; the request is applied as written |
| conflicts with a rule | 0.20 | a change that breaks a declared rule in some case |
| breaks a reference | 0.15 | a change that removes or renames something another element uses |
| widens who can act | 0.15 | a change that lets someone take an action or reach a state they could not before |
| breaks an outcome rule | 0.20 | a change after which some path reaches a guarded outcome without its check |

- The clean controls give precision a base. M1 had none by design.
- **The number of requests**, decided: 20, the same as M1. Phase B runs with what the diary holds
  at the window's end, with at least 12. Below 12, Phase B is not run, and ① is reported as "not
  enough changes".
- **A drawn type that cannot be written into a request.** For example, there may be no outcome
  rule yet to break. Then the researcher records "not applicable", and the next type in the order
  of the table is used. The rule is fixed now, so the researcher still does not choose.
  Each such case is reported.

## 6. Does M2 wait for M0b? (ADR-0054, open question 4)

**Decided: no.**
- M2 runs on the surfaces that exist today:
  - `toprope-run`;
  - the generated MCP server;
  - `toprope-proxy`;
  - the interview and change-loop commands.
- The brownfield effect no longer needs M0b's GitHub adapter.
- A live change that needs a migration plan (ADR-0018) is applied through today's in-flight check.
  If that is not enough, it is logged as a defect of class "needs migration", not fixed by hand.
- ③'s finding then reads "works as built on today's surfaces, without a generated UI".

## 7. Verdict rules (decided, frozen in the preregistration)

```yaml
# ③ (verdict). Over ③'s window, with at least 80% of trading days used.
factory:
  supports:
    state_permission_defects_max: 0      # an action allowed or denied differently from the declaration
    hand_edits_to_generated_code_max: 0
  weakens:
    state_permission_defects_min: 1
    hand_edits_to_generated_code_min: 1
  not_judged_if:
    trading_days_used_below: 0.80        # reported as "not enough use"

# ① (provisional; the claim-status table stays untested). From M2-design, unchanged.
iterate:
  supports:
    toprope_recall_min: 0.80
    toprope_precision_grouped_min: 0.70
    nl_recall_gap_min: 0.20
    structured_recall_gap_min: 0.10
    structured_precision_grouped_gap_min: 0.0
    median_iteration_minutes_max: 1
  weakens:
    structured_within: 0.0
    toprope_precision_grouped_below: 0.50
  noise:
    gap_within_noise_is: inconclusive
  not_run_if:
    change_requests_below: 12

# ② (observation only). Held-out accuracy, accuracy over iterations, unsupported rules, human
# time, reported with the label "expert = builder". No thresholds.
```

The external API defects (Alpaca's server or API) do not count against ③. They are reported beside
it.

## 8. Limits stated with the results

- **①:**
  - one person was the expert, the requester and the seeder;
  - the draw chose the seeds, but how each seed was worded is the researcher's (ADR-0054 §3);
  - the requests come from one person's diary.
- **②:** the expert is the builder. These numbers are an observation (ADR-0030).
- **③:**
  - it ran on a paper account and on today's surfaces;
  - fills come from the paper engine, not a live market.

## 9. Estimate

| Phase | Researcher | Builder |
|---|---|---|
| Setup and preregistration | 2–3 hours | the paper-only check and the draw tool: one PR |
| Held-out items, interview, probes | 4–6 hours | — |
| ③'s window | 10–15 minutes a trading day, for 2–6 weeks | fixes to defects, through the change loop |
| Phase B | about 2 hours (seeding), then the run | the run, as in M1 |
| Report | 1–2 hours | the scorer's output |

## 10. Decisions left for the researcher

Decided on 2026-11-12 ("추천대로"): the draw's shares and the number of requests (§5), ③'s window
and its 80% use threshold (§4), not waiting for M0b (§6), and the verdict rules (§7). ①'s rules
stay as M2-design drafted them.

Still open, with no recommendation yet (M2-grader leaves them to the preregistration):
1. **The expert sample.** Its size, and the grader's minimum agreement with the researcher's blind
   labels on it.
2. **The grader's model.** It is decided once M2's pilot shows what a second model would cost.

**Freezing.** The researcher freezes the preregistration in their own commit, or through a human
request (ADR-0039). The files are `experiments/m2/preregistration.yaml`, `verdict-rules.yaml` and
`draw.yaml`, frozen in one `freeze-prereg` step (`experiments/tools/instruments.py`). The grader's
expert sample is in `preregistration.yaml`, as recommended: 60 of the pilot's flags, 20 per arm,
with at least 0.80 raw agreement and a kappa of 0.60 on each checklist item. The preregistration holds:
- the checks' revision;
- the verdict rules;
- the draw (the shares, the number of requests, and the salt's hash);
- the run protocol;
- the grader's items.

The salt is made on the researcher's machine, and only its hash is committed.
