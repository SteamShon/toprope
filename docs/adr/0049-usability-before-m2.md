# ADR-0049: Make Toprope easy to use before M2

- Link: none (an enabler for ② and ⑥: M2's expert and later users go through these surfaces) ·
  Status: accepted · 2026-11-09 · decided by: SteamShon ("fix every weakness before we extend
  to application domains"; "go as recommended"; drafted by the assistant)
- Builds on: ADR-0019 (milestone order), ADR-0039 (human requests), ADR-0041 (one way across),
  ADR-0048 (outcome rules), [M1-report.md](../experiments/M1-report.md)
- Changes: the roadmap order (ADR-0019): a usability program runs after M1 and before M2

## Context
Toprope's products are the compiler and its two self domains, Authoring (making a domain) and
Delivery (shipping it). M1 ran them end to end, and what it cost to use them showed:

- A change to the self domains takes many commands: propose, cite, commit, check, request,
  approve, deploy. Each one needs the full `toprope-run --composition … --kernel-root …
  --workspace … --env …` prefix.
- A citation must name an exact chunk reference. A wrong one is refused, and the error does not
  say how to find the right one.
- A person confirms elements one at a time, then approves the commit, then approves the deploy.
  The person approves more often than the risk of the change calls for.
- There is no way to start: no `init`, no template, no tutorial. The README's first steps assume
  the reader already has a declaration.
- Interview questions are open-ended, and impact reports and counterexamples speak in cells and
  element keys, not in the domain's terms.
- An existing team already has its rules somewhere: an `AGENTS.md`, skill files, an OpenAPI
  spec, enums in a database, a ticket workflow, MCP servers. Toprope cannot start from any of
  them.

Competing products make the same claim, that the declared process is what runs (UiPath's
Cartographer; [`problem.md`](../problem.md)). How easy the product is to use will decide between
them. M2 brings an expert who is not the builder; if that expert spends the time fighting the
tools, M2 measures the tools' friction and not the claims. So the friction is removed first.

## Decision
1. **A program, not a milestone with a verdict.** Usability work runs after M1 closes
   (`umbrella/m1-recheck`) and before M2's spec freezes. It gives no link verdict. M0b may run
   alongside it.
2. **Step 0: a baseline, measured from records that already exist.**
   - **F1. Friction in the change loop.** From the self domains' event, attempt and commit logs:
     kernel commands per approved change; commands per change taken by a person; refused attempts
     per command; commits whose checks failed or that were never approved. A command that fails
     before the gate (a bad argument, an unresolved citation) leaves no record today. The
     baseline says so. Recording those failures is part of theme 1.
   - **F2. Time to a first rule.** From an empty directory to a first rule the gate enforces: the
     minutes it takes, the person's touches (commands typed, approvals), and the lines of YAML
     written by hand. It is measured on a written script, and repeated at the end on the same
     script.
   - The tool that computes F1, and the recorded baseline, are one PR with tests.
3. **Four themes, each an umbrella** (`umbrella/<theme>`, a draft PR into `develop` opened
   early with its targets; small sub-PRs, each with an adversarial review):
   1. **The change loop** (`umbrella/usability-change-loop`):
      - B4: citations resolved from a query or a quote, not only an exact chunk reference;
      - C1: `toprope change "<intent>"`, which runs propose, commit and check, and leaves one
        request for a person;
      - C3: a `toprope.yaml` that holds the composition, kernel root, workspace and env, so a
        command needs none of them;
      - B5: a person confirms a change from one readable diff, not element by element;
      - D1: every error names its fix, from an error catalog. A test scans the errors and fails
        on one without a fix. A failed command is recorded as an attempt;
      - C2: the number of approvals depends on the risk. A low-risk change gets one approval that
        covers confirming, approving and deploying, and is verified by probes afterwards. C2
        touches ADR-0039 and the floor that only a person approves (ADR-0041, ADR-0048), so it
        needs its own ADR before it is built.
   2. **Getting started** (`umbrella/usability-start`):
      - A4: `toprope init` and `toprope try`;
      - A3: a template library: an approval workflow, a refund window, a budget change, a
        release, an experiment;
      - E1: docs that show the first step first and the rest on demand;
      - E2: a 15-minute tutorial that runs.
   3. **Interview and feedback** (`umbrella/usability-interview`):
      - B1: choice questions with a recommended answer;
      - B2: ask for examples first, then the rule;
      - B3: a live map or diagram of the domain while answering;
      - D2: impact reports stated as the decisions a person must make;
      - D3: counterexamples told as a story in the domain's terms.
   4. **Import and wrap** (`umbrella/usability-import`):
      - A1: an `AGENTS.md` or skill files become a draft declaration and a list of conflicts;
        then importers from OpenAPI, database enums and a ticket workflow;
      - A2: existing MCP servers wrapped as a proxy, with rules over their tool calls.
      A2 overlaps M0b's adapters and needs its own ADR. A demo of A1 may come early.
4. **Order.** Theme 1 first, then themes 2 and 3 in parallel, then theme 4. A sub-PR that does
   not run the self domains' loop may start at any time. A sub-PR that does run it follows
   AGENTS.md's one-loop rule: it waits until no other open PR changes the self domains' commit
   store or logs, and starts from the base's files.
5. **Done when** (targets; F1 and F2 are measured again at the end):
   - a first enforced rule within 30 minutes of starting, with no YAML written by hand (F2);
   - a low-risk change takes one command and one approval by a person (F1; depends on C2's ADR.
     If that ADR keeps more approvals, this target is restated there);
   - every error the kernel and the CLI raise names its fix, enforced by a test;
   - at least 80% of the interview's questions offer choices with a recommended answer;
   - the self domains' refused or failed commands per command are at most half the baseline
     (F1).
6. **What does not change.** Agents still write only `proposed`. Only a person confirms or
   approves, unless C2's ADR decides otherwise. Gold sets and sealed files stay human-only.
   Every theme states the link it serves.

## Consequences
- The roadmap lists the program between M1 and M2, and M2's spec waits for it. M2 then tests the
  improved Toprope, the same way the M1 recheck does.
- Each theme's draft PR records its targets, and each sub-PR updates `docs/STATUS.md`.
- Two more ADRs come before their work: C2 (approvals by risk) and A2 (an MCP proxy).
- Theme 1 changes the self domains' declarations and their loop, so its sub-PRs run one at a
  time. Themes 2 and 4 mostly add code and docs, and can run beside it.

## Rejected
- **One umbrella for everything.** It would hold a large unreviewed branch for weeks, and every
  theme would wait for the slowest.
- **One umbrella per item.** About twenty umbrellas, each with its own draft PR and merge
  commit, cost more than the items they hold.
- **Doing it after M2.** M2's expert would meet the friction, and M2 would partly measure it.
