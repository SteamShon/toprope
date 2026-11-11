# Tutorial: your first enforced rule in about 20 minutes

Link: none (ADR-0049, E2; ADR-0053, F2). You will start a domain from a template, see the gate
refuse an agent with the rule's own reason, change a rule and add one of your own without writing
YAML, and connect the domain to your agent. `tests/test_tutorial.py` runs every command on this page, in order, so it stays
true.

You need [`uv`](https://docs.astral.sh/uv/) and a clone of this repository
(`git clone https://github.com/SteamShon/toprope.git && cd toprope`). Work in one shell from start
to end: the first block installs, the second remembers where the clone is, and every later
command runs through `uv run --project "$TOPROPE"`, from any directory.

```bash
uv sync
```
```bash
export TOPROPE="$(pwd)"            # the repository; run this from its root
```

## 1. Start a domain (1 minute)

```bash
uv run --project "$TOPROPE" toprope-init --list
uv run --project "$TOPROPE" toprope-init my-access --template approval --dir /tmp/toprope-tutorial
```

`my-access/` now holds `domain.yaml` (the rules), `tokens.yaml` (the people and the agent of
the template's story), `story.yaml`, and `toprope.yaml`, so the commands below need no options.

## 2. See the rules work (2 minutes)

```bash
cd /tmp/toprope-tutorial/my-access
uv run --project "$TOPROPE" toprope-try
```

An agent files access requests for the team. It cannot approve one (only a person can), a
manager cannot approve prod access (security does), and nobody approves their own request. Each
refusal comes with the rule's reason, the same one the agent gets.

## 3. Act as the agent (3 minutes)

The domain's own store keeps what happens. Act as the agent (`t-bot`), then as a person:

```bash
uv run --project "$TOPROPE" toprope-run submit_request R-wiki --token t-bot
uv run --project "$TOPROPE" toprope-run approve_request R-wiki --token t-bot || echo "refused, as it should be"
uv run --project "$TOPROPE" toprope-run approve_request R-wiki --token t-max
uv run --project "$TOPROPE" toprope-run history R-wiki --token t-max
```

The second command is refused with `"code": "actor"` and the reason *Only a person can
approve_request.* (`toprope-run` exits 1 on a refusal, hence the `||`). The third is approved
by `max`, a manager. `history` shows what happened to the request: created, submitted, approved,
and the decision. A refusal changes nothing, so it is not among them; the store keeps it as an
attempt (query tools over attempts are planned, M0b).

## 4. Change a rule without YAML (3 minutes)

```bash
uv run --project "$TOPROPE" toprope-set --list
uv run --project "$TOPROPE" toprope-set prod_approver=manager
uv run --project "$TOPROPE" toprope-set prod_approver=security
```

Before anything ships, you see what the change touches (the change check) and which steps of
the story now end differently: a manager may now approve prod access. The last command sets it
back. When a change is what you meant, `toprope-try --accept` makes the story expect it (it shows
each step it changes).

## 5. Add a rule of your own (5 minutes)

Say a request now carries an amount, and one over 1,000 needs finance. The template has no such
rule, so add it by command:

```bash
uv run --project "$TOPROPE" toprope-add field amount --set-by submit_request --default 0
uv run --project "$TOPROPE" toprope-rule threshold --action approve_request --when "amount > 1000" --needs finance
uv run --project "$TOPROPE" toprope-try
```

The first command gives requests an `amount`, which `submit_request` now takes (`--amount`). The
second adds the rule: it adds the role `finance`, lets it approve, adds a person `kim` with that role
to try it, and a step to the story in which a manager is refused. `toprope-try` shows it. Other kinds
of rule: `no-self-approval`, `person-only` and `window` (`toprope-rule --help`); `toprope-rule list`
shows every rule, and `toprope-rule remove ID` takes one out. `toprope-rename` and `toprope-add role`,
`person` and `agent` fit the names and the people to your team's.

The domain's own store still holds what you did in step 3, so the commands left it as it was and
said how to start it again from the new examples. Do that, then act:

```bash
uv run --project "$TOPROPE" toprope-try --reset
uv run --project "$TOPROPE" toprope-run submit_request R-wiki --amount 1500 --token t-mia
uv run --project "$TOPROPE" toprope-run approve_request R-wiki --token t-max || echo "refused by your rule"
uv run --project "$TOPROPE" toprope-run approve_request R-wiki --token t-kim
```

`max` is refused with `"code": "amount-over-1000-needs-finance"` and your rule's reason; `kim`, from
finance, approves. (`--reset` keeps the old store as `.toprope/events-<time>.db`.)

Run in a script, as here, the rule is written `proposed`: a rule becomes a person's only when they
confirm it at a terminal, when they type the command or later with `toprope-rule confirm`. Proposed
or not, it is enforced. `toprope-remove field|role|person` takes out a template's leftovers once
nothing uses them.

## 6. Connect your agent (5 minutes)

Serve the domain over MCP to Claude Code, Codex, Cursor or your own agent:

```bash
uv run --project "$TOPROPE" toprope-server --help
```

The server does not read `toprope.yaml`: give it the same three things as options, with
absolute paths, since an MCP client starts it from elsewhere. For this domain:

```
toprope-server --domain /tmp/toprope-tutorial/my-access/domain.yaml \
  --store sqlite:/tmp/toprope-tutorial/my-access/.toprope/events.db \
  --identity static:/tmp/toprope-tutorial/my-access/tokens.yaml
```

with `TOPROPE_TOKEN=t-bot` for the agent ([`server.md`](server.md) has an MCP client entry). The
agent then gets one tool per action and is held to the same rules: what it may not do is refused
with the reason.

## Next

- Your own workflow: let your agent interview you about it ([`workflow.md`](workflow.md)).
- Every part and how they fit: [`concepts.md`](concepts.md).
- What each refusal and error means: [`errors.md`](errors.md).
