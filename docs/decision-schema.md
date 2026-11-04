# Decision schema v0 (draft)

A decision carries its **meaning and lifecycle** (who, why, where, since when, evidence)
separately from its **check** (how to evaluate an action). The check is handed to a
`PolicyEvaluator` adapter so it can later be compiled to Cedar or OPA without changing the
decision record.

```yaml
id: no-skip-failing-tests           # stable identifier
version: 1                          # bumps on amendment
status: active                      # proposed | active | withdrawn | superseded
statement: >                        # human meaning, one or two sentences
  Do not skip, delete, or xfail failing tests to make CI pass.
reason: >                           # returned to the agent when it blocks
  Green CI must mean the behavior works. Fix the code or ask.
owner: SteamShon                    # who may amend or withdraw
scope:
  repos: ["*"]                      # where it applies
  paths: ["tests/**", "**/test_*.py"]
since: 2026-11-04
evidence:                           # why we believe this was decided
  - kind: statement                 # statement | correction | rejection | incident
    source: docs/experiments/M1-enforce.md
    quote: "D4 Do not skip, delete or xfail failing tests to get green."
check:                              # evaluated by the PolicyEvaluator port
  on: [Edit, Write, Bash]
  deny_if_any:
    - content_matches: '@pytest\.mark\.(skip|xfail)'
    - command_matches: 'pytest .*(--deselect|-k\s+"not )'
on_violation: deny                  # deny | ask
exceptions:                         # filled by lifecycle (M3)
  allowed: true
  require_reason: true
  amend_threshold: 5                # N exceptions in 30 days → amendment proposal
supersedes: null
```

## Open questions

- How much of `check` should be structured matching vs. an LLM classifier (and how to
  report the classifier's error rate honestly)?
- Do decisions without a `check` (pure guidance) belong in the store at all? Proposal: yes,
  with `on_violation: none`, so coverage and propagation can still be measured.
- Scope precedence when a repo-level and a global decision conflict.
