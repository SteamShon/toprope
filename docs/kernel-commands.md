# Kernel commands

_Generated from the commands' argument parsers by `python -m toprope.kernel.reference`. Do not edit: change the parser, then regenerate._

Link: none (an operating guide). These are the kernel's own commands (ADR-0027): the same for every domain. What a domain's people and agents do is in that domain's generated guide (`domains/<domain>/guide.md`). Run each as `uv run <command>` from the repository root.

## `toprope-run`

`toprope-run`: a command line generated from a declaration (ADR-0036).

Its subcommands are the domain's actions, one per action, plus `get`, `history`, `allowed`, `whoami` and `guide`; each domain's guide lists them with who may take each.

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | one declaration (or --composition with --member) |
| `--composition` `COMPOSITION` | a *.composition.yaml: every member wired in this process |
| `--member` `MEMBER` | with --composition: the member whose actions these are |
| `--store` `STORE` | with --domain: the event store (memory, the default; sqlite:FILE, postgres:DSN, jsonl:DIR); with --composition, memory keeps nothing |
| `--store-dir` `STORE_DIR` | with --composition: one SQLite store per member, <dir>/<member>.db (default: each member's event log, <its directory>/events, kept in git) |
| `--identity` `IDENTITY` | git[:FILE] (your git email, looked up in FILE, default toprope.identity.yaml; the default when that file is here), github[:FILE] (the approver of a GitHub run, ADR-0039), static:FILE or jwt |
| `--token` `TOKEN` | your credential (default: TOPROPE_TOKEN) |
| `--kernel-root` `KERNEL_ROOT` | run declared kernel-service effects on files under this directory |
| `--workspace` `WORKSPACE` | authoring workspace, for the source services |
| `--env` `ENV` | local deploy environment, for the preview and deploy services |
| `--seed` | load the declaration's example fixtures first |
| `--key` `KEY` | idempotency key (default: a new one); reuse it to retry safely |
| `--working-copy` | with --composition and --kernel-root: run each member from its working-copy file, not from its deployed commit (ADR-0045) |
| `--config` `CONFIG` | the options file (default: toprope.yaml in the current directory, if any) |
| `--no-config` | ignore toprope.yaml |
| `--failures` `FAILURES` | a directory where a command that fails before the gate is recorded, one file per failure (ADR-0049, D1b) |
| `--person-route` `PERSON_ROUTE` | how a person takes a step an agent is refused here, added to such refusals' fix (for the self domains: the human request, ADR-0039) |

## `toprope-init`

Start a domain from a template and see its rules work (ADR-0049, A3 and A4; ADR-0053, F2).

| Argument | What |
|---|---|
| `NAME` | the new domain's name, and its directory; or a sentence that describes your workflow and its rules (then the name is --name, or taken from the template) |
| `PROSE` | a sentence that describes your workflow and its rules |
| `--name` `AS_NAME` | the domain's name, when the first argument is a sentence |
| `--template` `TEMPLATE` | the template to start from (see --list) |
| `--dir` `DIR` | where to write the domain's directory (default: here) (default `.`) |
| `--list` | list the templates |
| `--set` `NAME=VALUE` | a template setting (see `toprope-set --list` in the new directory) (default `[]`) |

## `toprope-try`

Start a domain from a template and see its rules work (ADR-0049, A3 and A4; ADR-0053, F2).

| Argument | What |
|---|---|
| `--dir` `DIR` | the domain's directory (default: here) (default `.`) |
| `--check` | compare domain.yaml with its template |
| `--json` | the steps as JSON |
| `--accept` | make each step's expectation in story.yaml what happens now, and show what changed |
| `--reset` | start the domain's store (the one toprope-run uses) again from domain.yaml's examples; the old file is kept |
| `--yes` | with --accept: also accept steps that showed a rule refusing and now pass |

## `toprope-set`

Start a domain from a template and see its rules work (ADR-0049, A3 and A4; ADR-0053, F2).

| Argument | What |
|---|---|
| `NAME=VALUE` | settings to change |
| `--dir` `DIR` | the domain's directory (default: here) (default `.`) |
| `--list` | the settings, what each means, and its value |

## `toprope-rule`

Add your own rules, roles, people and fields to a domain by command, with no YAML (ADR-0053, F2).

| Argument | What |
|---|---|
| `--dir` `DIR` | the domain's directory (default: here) (default `.`) |

### `toprope-rule list`

The domain's rules, with the id each is removed or confirmed by.


### `toprope-rule threshold`

Above (or below) a value, an action needs a role.

| Argument | What |
|---|---|
| `--action` `ACTION` | the action the rule holds back, e.g. approve_request (required) |
| `--when` `'FIELD OP VALUE'` | when the rule applies, e.g. "amount > 1000" (required) |
| `--needs` `ROLE` | the role that may still take the action then (required) |
| `--id` `ID` | the rule's id (refusals carry it as their code) |
| `--reason` `REASON` | the reason a refusal gives (default: written from the rule) |

### `toprope-rule no-self-approval`

Whoever made it theirs (submitted, created) may not take the action.

| Argument | What |
|---|---|
| `--action` `ACTION` | the action, e.g. approve_request (required) |
| `--by` `BY` | the action that makes it someone's (found if one records who took it) |
| `--id` `ID` | the rule's id (refusals carry it as their code) |
| `--reason` `REASON` | the reason a refusal gives (default: written from the rule) |

### `toprope-rule person-only`

Only a person may take the action; an agent is refused.

| Argument | What |
|---|---|
| `--action` `ACTION` | (required) |

### `toprope-rule window`

The action is allowed only within a number of days.

| Argument | What |
|---|---|
| `--action` `ACTION` | (required) |
| `--days` `DAYS` | (required) |
| `--field` `FIELD` | a date field, or a field that counts days, to measure from |
| `--since` `ACTION` | count from when this action was taken (recorded from now on) |
| `--id` `ID` | the rule's id (refusals carry it as their code) |
| `--reason` `REASON` | the reason a refusal gives (default: written from the rule) |

### `toprope-rule remove`

Remove a rule by its id (see list).

| Argument | What |
|---|---|
| `ID` |  |

### `toprope-rule confirm`

Make drafted (`proposed`) rules yours; with no id, all of them.

| Argument | What |
|---|---|
| `IDS` |  |

## `toprope-add`

Add your own rules, roles, people and fields to a domain by command, with no YAML (ADR-0053, F2).

| Argument | What |
|---|---|
| `--dir` `DIR` | the domain's directory (default: here) (default `.`) |

### `toprope-add role`

A role.

| Argument | What |
|---|---|
| `NAME` |  |
| `--may` `ACTION,...` | actions the role may take (default ``) |

### `toprope-add person`

A person, with a token in tokens.yaml to act as them.

| Argument | What |
|---|---|
| `NAME` |  |
| `--roles` `ROLE,...` | (required) |

### `toprope-add agent`

An agent acting for a person, with a token and a grant.

| Argument | What |
|---|---|
| `NAME` |  |
| `--for` `PERSON` | (required) |
| `--may` `ACTION,...` | the actions its grant allows (required) |
| `--roles` `ROLE,...` | its roles (default: the person's) |

### `toprope-add field`

A field of an object, optionally given when an action is taken.

| Argument | What |
|---|---|
| `NAME` |  |
| `--type` `TYPE` | one of integer, number, string, boolean, datetime (default: integer) (default `integer`) |
| `--choices` `A,B,...` | instead of --type: one of these words |
| `--on` `OBJECT` | the object (default: the action's, or the only one) |
| `--set-by` `ACTION,...` | actions that take it as a param and record it |
| `--default` `DEFAULT` | its value in the examples already there |

## `toprope-rename`

Add your own rules, roles, people and fields to a domain by command, with no YAML (ADR-0053, F2).

| Argument | What |
|---|---|
| `OLD` | an object, action, role or field as domain.yaml names it |
| `NEW` | its new name |
| `--kind` `{object,action,role,field}` | when the name is used twice |
| `--dir` `DIR` | the domain's directory (default: here) (default `.`) |

## `toprope-remove`

Add your own rules, roles, people and fields to a domain by command, with no YAML (ADR-0053, F2).

| Argument | What |
|---|---|
| `--dir` `DIR` | the domain's directory (default: here) (default `.`) |

### `toprope-remove field`

A field no rule, effect or state reads (its values leave the examples).

| Argument | What |
|---|---|
| `NAME` |  |
| `--on` `OBJECT` | the object, when several have the field |

### `toprope-remove role`

A role no rule, cell or person holds (it leaves the actions' actor lists).

| Argument | What |
|---|---|
| `NAME` |  |

### `toprope-remove person`

A person or an agent from tokens.yaml, with the story steps they act in.

| Argument | What |
|---|---|
| `NAME` |  |

## `toprope-change`

`toprope-change`: one command takes a change from an agent's proposals to one request for a person (ADR-0049, C1).

| Argument | What |
|---|---|
| `INTENT` | what the change is for, in a sentence; the request's summary |
| `--patch` `PATCH` | a YAML list of {path, value, cites, origin} (required) |
| `--draft` `DRAFT` | the draft the change is made in (default: authoring) (default `authoring`) |
| `--member` `MEMBER` | the member whose actions these are (default `authoring`) |
| `--origin` `ORIGIN` | the Source object an element came from, when it names none |
| `--workspace` `WORKSPACE` | the draft's workspace, if not the one in toprope.yaml |
| `--kernel-root` `KERNEL_ROOT` | where the commit store is (default: `kernel_root:` in toprope.yaml, or here) |
| `--request` `REQUEST` | the request file to write (default: .toprope/requests/<id>.yaml) |
| `--run-args` `RUN_ARGS` | options passed to every toprope-run step, e.g. "--identity static:ids.yaml" (default ``) |

## `toprope-apply`

`toprope-apply`: a person applies a human request at their own terminal, with one confirmation (ADR-0053, 3; ADR-0039 without GitHub).

| Argument | What |
|---|---|
| `REQUEST` | the request file, .toprope/requests/<id>.yaml |
| `--identity` `IDENTITY` | the identity file your git email is looked up in (default `toprope.identity.yaml`) |
| `--ship` | also deliver, preview, deploy, probe and verify the commit the request approves; a commit not recorded low risk stops after its preview |

## `toprope-interview`

`toprope-interview`: the interview, in your terminal, on your own domain (ADR-0053 §2).

The interview's route for a newcomer: docs/interview.md.

| Argument | What |
|---|---|
| `DIR` | the domain's directory (default: here); it holds domain.yaml, or the interview starts one |
| `--answers` `ANSWERS` | read the answers from this file, one per line, instead of the terminal |
| `--share` | print ADR-0053's choice measure from the interview log and stop |

## `toprope-import`

`toprope-import`: a proposed draft from a source a team already has (ADR-0049 A1, ADR-0051).

| Argument | What |
|---|---|
| `KIND` | the source's format: an extractor (see --list) |
| `SOURCE` | where the source is, as the reader takes it (a path, a URL, a command) |
| `--via` `VIA` | the reader that reaches the source (default: mcp for mcp, else file) |
| `--profile` `PROFILE` | a YAML file of the team's conventions |
| `--domain` `DOMAIN` | the new domain's name (default `imported`) |
| `--out` `OUT` | where to write a new draft (default: <domain>.domain.yaml here) |
| `--into` `INTO` | an existing draft to join this source to; its elements are never overwritten |
| `--patch` `PATCH` | write the elements as a patch for `toprope-change --patch`, and register the source in the workspace, instead of writing a draft |
| `--workspace` `WORKSPACE` | with --patch: the workspace file (default: `workspace:` in toprope.yaml); a new one is made for --domain |
| `--source-id` `SOURCE_ID` | with --patch: the source's id in the workspace (default: <domain>-<kind>) |
| `--binding-out` `BINDING_OUT` | write the draft binding a server's tools give (mcp), for toprope-proxy |
| `--env` `NAME=VALUE` | mcp: set this variable for the server it starts (not a secret: the binding writes it) (default `[]`) |
| `--pass-env` `NAME` | mcp: give the server this variable from your environment (a key); the binding names it, never its value, as toprope-proxy's `pass_env` (default `[]`) |
| `--questions` `QUESTIONS` | also write the conflicts and questions as YAML records, for an agent to work from |
| `--list` | the readers and extractors installed |

## `toprope-server`

`toprope-server`: serve a declaration over MCP (stdio or streamable HTTP).

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | one declaration (or --composition with --member) |
| `--composition` `COMPOSITION` | a *.composition.yaml (ADR-0026): every member runs in this process, wired; --member is the one served |
| `--member` `MEMBER` | with --composition: the member domain to serve |
| `--store-dir` `STORE_DIR` | with --composition: one SQLite store per member, <dir>/<member>.db (default: each member's event log, <its directory>/events) |
| `--kernel-root` `KERNEL_ROOT` | run declared kernel-service effects (ADR-0028) on files under this directory; without it, kernel calls stay pending |
| `--workspace` `WORKSPACE` | authoring workspace, for the read_source and fetch_source services |
| `--env` `ENV` | local deploy environment, for the preview and deploy services |
| `--store` `STORE` | with --domain: memory (default), sqlite:FILE, postgres:DSN or jsonl:DIR; with --composition, memory keeps nothing |
| `--identity` `IDENTITY` | how callers are resolved: static:FILE (token -> caller) or jwt (required) |
| `--transport` `{stdio,http}` | stdio for one local caller (TOPROPE_TOKEN), http for many (streamable HTTP) (default `stdio`) |
| `--host` `HOST` | with --transport http: the address to listen on (default `127.0.0.1`) |
| `--port` `PORT` | with --transport http: the port (default `8765`) |
| `--public-url` `PUBLIC_URL` | URL clients use to reach this server (default http://HOST:PORT) |
| `--no-seed` | do not load the declaration's example fixtures (never loaded into a composition member's own event log) |
| `--harness-report` `HARNESS_REPORT` | harness report JSON (toprope-harness --json) shown in the world map |
| `--working-copy` | with --composition and --kernel-root: run each member from its working-copy file, not from its deployed commit (ADR-0045) |

## `toprope-proxy`

`toprope-proxy`: a declaration's rules in front of an existing MCP server (ADR-0052).

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | the declaration whose rules gate the calls (required) |
| `--binding` `BINDING` | the binding: the upstream server and which tool is which action (required) |
| `--identity` `IDENTITY` | static:FILE (token -> caller), jwt or git, as for toprope-server |
| `--store` `STORE` | sqlite:FILE or jsonl:DIR: the gate's record, shared with a lock by every proxy on it |
| `--audit` `AUDIT` | append every call, gated or read, to this JSONL file |
| `--no-seed` | do not load the declaration's example fixtures |
| `--check` | check that the binding, the server's tools and the declaration agree, as at start, and exit |
| `--confirm-binding` | as a person: check the binding as at start, then record that you confirmed it as it is (who, when, its hash) |

## `toprope-harness`

`toprope-harness`: run the generated harness on a declaration.

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | one declaration (or use --composition) |
| `--composition` `COMPOSITION` | a *.composition.yaml: check members and wiring (ADR-0026), then run the harness on every member |
| `--levels` `LEVELS` | comma-separated: model, execution, mcp (default `model,execution,mcp`) |
| `--examples` `EXAMPLES` | exploration examples (0 disables) (default `200`) |
| `--depth` `DEPTH` | exploration depth (default `5`) |
| `--json` `JSON` | write the full report as JSON to this path |
| `--regen-check` | with --composition: the regeneration check (ADR-0028): serve from declarations, run, regenerate, compare, and run every kernel call end to end |
| `--tla` `DIR` | with --domain: write the model level as a TLA+ module and TLC config (ADR-0043), with the actions left out of the model |
| `--mutants` | with --domain: check that the harness catches each seeded break (exit 1 if one survives) |
| `--receiver` `FILE[@MAJOR]` | a receiving domain's declaration, with its published interface major (default 1): checks this domain's handoffs against it (ADR-0024) (default `[]`) |

## `toprope-worldmap`

`toprope-worldmap`: compile a declaration's world map (ADR-0020).

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | one declaration (or use --composition) |
| `--composition` `COMPOSITION` | a *.composition.yaml: write the composed map (ADR-0026) |
| `--out` `OUT` | (default `world-map.json`) |
| `--harness` | run the harness and include its results |
| `--harness-report` `HARNESS_REPORT` | use an existing harness report JSON instead (with --composition: the member → report map that `toprope-harness --composition --json` writes) |
| `--mermaid` `MERMAID` | also write structure.mmd, <Object>.states.mmd and, when the harness found any, minimal-flows.md here |
| `--guide` `GUIDE` | also write the domain guide (Markdown) to this path |

## `toprope-commits`

`toprope-commits`: read a domain's commit store and a deploy environment (ADR-0029, ADR-0032).

| Argument | What |
|---|---|
| `--commits` `COMMITS` | the commit store (default `.toprope/commits`) |

### `toprope-commits branches`

Every branch and the commit it points to.

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |

### `toprope-commits log`

An element's history (ADR-0032).

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |
| `ELEMENT` | an element key, e.g. action:launch_experiment |
| `--at` `AT` | read from this commit (default: main, else the work head) |

### `toprope-commits diff`

What changed directly between two commits.

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |
| `[FROM] TO` | two commits, or one: what it has since nothing |

### `toprope-commits checks`

The newest record of each check on a commit.

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |
| `COMMIT` | a commit id, e.g. 4-b0c8834e25d9bbc7 |

### `toprope-commits evidence`

The evidence a commit cites, with its strength (ADR-0041).

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |
| `COMMIT` | a commit id, e.g. 4-b0c8834e25d9bbc7 |

### `toprope-commits deployed`

What a deploy environment runs.

| Argument | What |
|---|---|
| `--env` `ENV` | the environment directory, e.g. .toprope/env (required) |
