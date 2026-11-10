# Tutorial: your first enforced rule in 15 minutes

Link: none (ADR-0049, E2). You will start a domain from a template, see the gate refuse an
agent with the rule's own reason, change the rule without writing YAML, and connect the domain
to your agent. `tests/test_tutorial.py` runs every command on this page, in order, so it stays
true.

You need [`uv`](https://docs.astral.sh/uv/) and this repository. From its root:

```bash
uv sync
```

## 1. Start a domain (1 minute)

```bash
uv run toprope-init --list
uv run toprope-init my-access --template approval --dir /tmp/toprope-tutorial
```

`my-access/` now holds `domain.yaml` (the rules), `tokens.yaml` (the people and the agent of
the template's story), `story.yaml`, and `toprope.yaml`, so the commands below need no options.

## 2. See the rules work (2 minutes)

```bash
cd /tmp/toprope-tutorial/my-access
uv run --project "$OLDPWD" toprope-try
```

An agent files access requests for the team. It cannot approve one (only a person can), a
manager cannot approve prod access (security does), and nobody approves their own request. Each
refusal comes with the rule's reason, the same one the agent gets.

## 3. Act as the agent (3 minutes)

The domain's own store keeps what happens. Act as the agent (`t-bot`), then as a person:

```bash
uv run --project "$OLDPWD" toprope-run submit_request R-wiki --token t-bot
uv run --project "$OLDPWD" toprope-run approve_request R-wiki --token t-bot || true
uv run --project "$OLDPWD" toprope-run approve_request R-wiki --token t-max
```

The second command is refused: *Only a person can approve_request.* The third is approved by
`max`, a manager. `toprope-run history R-wiki --token t-max` shows every step, and the refusal
is recorded too.

## 4. Change a rule without YAML (3 minutes)

```bash
uv run --project "$OLDPWD" toprope-set --list
uv run --project "$OLDPWD" toprope-set prod_approver=manager
```

Before anything ships, you see what the change touches (the change check) and which steps of
the story now end differently: a manager may now approve prod access. Set it back with
`toprope-set prod_approver=security`. To change a rule that has no setting, edit `domain.yaml`
and run `toprope-try --check`.

## 5. Connect your agent (5 minutes)

Serve the domain over MCP to Claude Code, Codex, Cursor or your own agent:

```bash
uv run --project "$OLDPWD" toprope-server --help
```

Point the server at `domain.yaml`, the store and the identities in `toprope.yaml`
([`server.md`](server.md) has the options and an MCP client entry). The agent then gets one tool
per action and is held to the same rules: what it may not do is refused with the reason.

## Next

- Your own workflow: let your agent interview you about it ([`workflow.md`](workflow.md)).
- Every part and how they fit: [`concepts.md`](concepts.md).
- What each refusal and error means: [`errors.md`](errors.md).
