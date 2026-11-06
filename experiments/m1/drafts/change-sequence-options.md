# M1 change sequence: options to select from (draft)

Link: ① iterate safely, ⑥ (partial); pilot only (ADR-0034). Drafted by the assistant at the
researcher's request (ADR-0034 §3: the self domains' M1 instruments may be drafted by an
agent, with multiple-choice options the researcher selects from). **Not an instrument**: the
researcher picks one option per slot (or writes their own), then the assistant writes
`instruments/change-requests.yaml` and `instruments/change-key.yaml` from the picks with
`status: draft`, and the researcher reviews, sets `frozen` and freezes them in their own commit.

Each slot fixes the *kind* of problem, so any pick keeps the mix the design asks for:
6 conflicts, 4 breakages, 10 clean, in this order. The intents are what an arm sees; the
key columns (kind, type, against, designed for the checks) go only into `change-key.yaml`.
Slot 9 is handoff-breaking, so the ⑥ pilot is tested (verdict rules, `handoff`). Some keys
are types the checks were not designed for (`designed: no`), as the design's risk list asks.

Domain words as Phase A named them: draft, interview stage, question, answer, element
(proposed, unknown, confirmed), decision request, commit, change check, approve, deliver,
delivery request (requested, previewing, previewed, deploying, done, verified), preview,
deploy, verify, owner, expert, approver.

| # | Kind | Option A (intent) | Option B (intent) | Key: type · against · designed |
|---|---|---|---|---|
| 1 | clean | Let the expert ask interview questions too, not only the owner. | Record who asked each question. | — |
| 2 | clean | Give every commit a short title that the history shows. | Let a person reopen a decided decision request when new facts come in, keeping the earlier choice on record. | — |
| 3 | conflict | Let an agent confirm elements that only fix wording. | Let an agent approve a commit when every check passes and the owner is away. | conflicts-with-rule · only a person confirms (A) / approves (B) · yes |
| 4 | clean | Allow delivering to a `staging` environment as well as `local`. | Let the approver cancel a delivery request before it is deployed. | — |
| 5 | breakage | Call the `unknown` element state `open question` instead. | Call the `previewed` delivery stage `built` instead. | breaks-past-behavior · past events and in-flight objects in the old state · yes |
| 6 | clean | Keep a note on each confirmation saying why the owner agreed. | Let a person mark a source as no longer used, so its chunks are not offered. | — |
| 7 | conflict | Approve a commit without a change check when only wording changed. | Let a commit that is already approved be approved again, to re-tag it. | conflicts-with-rule · approve needs a passing check, and approved commits passed it (A) / not twice (B) · yes |
| 8 | clean | Ask a second person to confirm elements about who may approve or deploy. | Record how long each interview stage took. | — |
| 9 | breakage (handoff) | Delivery should know which branch a commit came from, and refuse requests that do not say. | Delivery should call the environment the `target`, and refuse requests that do not name one. | breaks-reference · what Authoring sends when it delivers · yes |
| 10 | clean | Let the owner withdraw a proposed element, so it leaves the draft. | Let a person attach a link to an outside ticket to a commit. | — |
| 11 | conflict | Let a build whose harness failed be deployed when the approver accepts the risk. | Allow verifying a delivery before it is deployed, to record a dry run. | conflicts-with-rule · deploy only builds that passed their harness (A) / verify only what was deployed (B) · yes |
| 12 | clean | Let the approver run the preview again after a failed one. | Show on each delivery request which commit it replaced. | — |
| 13 | conflict | Let the owner skip a required interview stage if they write why. | Let elements the owner wrote themselves be confirmed without citing a source. | other:required-stages · only optional stages may be skipped, a kernel rule (A) / conflicts-with-rule · every element cites a source (B) · no (A) / yes (B) |
| 14 | clean | Let the owner name a deputy who may approve commits while they are away. | Add a `paused` stage for delivery requests waiting on someone. | — |
| 15 | breakage | Drop the `previewing` stage: a preview finishes at once. | Drop the `unknown` element state: an element is proposed or confirmed. | strands-objects · requests now previewing (A) / elements now unknown (B) · yes |
| 16 | clean | Let the owner give an approved commit a release name. | Allow fetching a link source again to refresh its snapshot. | — |
| 17 | conflict | Deliver a commit that is not approved yet, to preview it in the shared environment. | Let the system deploy on its own after a passing preview. | conflicts-with-rule · only approved commits are delivered (A) / only a person deploys (B) · yes |
| 18 | breakage | Count a commit as checked only if its check is less than a day old. | Make the expert's answers count only after the owner countersigns them. | breaks-past-behavior · commits approved on older checks (A) / answers given before (B) · no |
| 19 | clean | Let anyone read an element's history, not only the owner. | Record which agent drafted each proposed element. | — |
| 20 | conflict | Let an agent settle a decision request when the owner says so in chat. | Let the expert approve commits that only touch the stages they answered. | conflicts-with-rule · only a person decides (A, probe P01) / only the owner approves (B) · yes |

## How to answer
One line, for example `1A 2B 3A 4A 5B 6A 7A 8A 9A 10A 11B 12A 13A 14A 15A 16A 17B 18A 19B 20A`.
Any slot can instead be your own wording (`5: <intent>`), with its key. Wording to avoid in
an intent: "conflict", "break", "seeded" (the validator warns about them).

## Selected (2026-11-06)
The researcher picked the recommended line. In review, at the researcher's request, two picks
changed: slot 2's B already contradicts "a new decision needs a new request" (so it was not
clean) and was replaced by a new clean intent, "Let a decision request carry a deadline that
the owner sees when it is asked"; slot 12's A is already allowed, so 12B was taken. The result
is in `instruments/change-requests.yaml` and `instruments/change-key.yaml`.
