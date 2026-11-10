# Domain guide: `delivery` (version 8)

_Generated from the declaration at build time. Do not edit: change the declaration._

## Purpose

An approved domain version must become working software in an environment, and nothing unverified may reach it.

**Success metric:** share of approved versions that reach verified-in-use without a manual fix or rollback (up is better)

> Approved domain versions now reach the environment as working software in one step. Nothing that fails its checks or lacks a person's approval gets there.

## People and things

**Roles:** `approver` (ana). Agents act only on a person's behalf, with a grant.

- **DeliveryRequest**: A request to deliver an approved commit of a domain, handed off by Authoring. Stages: `requested`, `previewing`, `built`, `deploying`, `done`, `verified` (starts `requested`).
  - facts: `domain_id` (string), `commit` (string), `branch` (string), `interface` (string), `environment` (string), `approver` (string), `build` (string, optional), `harness_ok` (boolean, optional), `deployed` (boolean, optional), `refusal` (string, optional), `verified` (boolean, optional), `probes_passed` (boolean, optional), `probe_summary` (string, optional)
- **Environment**: Where a domain runs; it points at one deployed commit.
  - facts: `name` (string), `current_commit` (string, optional)

## Actions

🔒 only a person may take it · 📝 recorded as a decision

| action | who | on | needs first | changes | starts | event |
| --- | --- | --- | --- | --- | --- | --- |
| `request_delivery` | system | creates **DeliveryRequest**; params `domain_id` (string), `commit` (string), `branch` (string), `interface` (string), `environment` (string), `approver` (string) | — | — | — | `DeliveryRequestCreated` |
| `preview` | approver | **DeliveryRequest** | `not-deployed`: Already deployed; deliver again with a new request. | the stage (per the matrix) | kernel `preview` → `record_build` | `DeliveryRequestPreview` |
| `record_build` | the kernel | **DeliveryRequest**; params `build` (string), `harness_ok` (boolean) | — | the stage (per the matrix); `target.build` ← `params.build`, `target.harness_ok` ← `params.harness_ok` | — | `DeliveryRequestRecordBuild` |
| `deploy` 🔒 📝 | approver | **DeliveryRequest**; params `rationale` (string, optional) | `harness-passed`: Deploy only a build whose harness passed. | the stage (per the matrix) | kernel `deploy` → `record_deployment` | `DeliveryRequestDeploy` |
| `record_deployment` | the kernel | **DeliveryRequest**; params `deployed` (boolean), `error` (string) | — | the stage (per the matrix); `target.deployed` ← `params.deployed`, `target.refusal` ← `params.error`, `target.probes_passed` ← `False` | — | `DeliveryRequestRecordDeployment` |
| `verify` 🔒 | approver | **DeliveryRequest** | `deployed`: Only a deployment that happened can be verified.; `probes-passed`: Run the probes on the deployment first; verify only one whose probes passed. | the stage (per the matrix); `target.verified` ← `True` | — | `DeliveryRequestVerify` |
| `record_probes` | the kernel | **DeliveryRequest**; params `passed` (boolean), `summary` (string) | — | the stage (per the matrix); `target.probes_passed` ← `params.passed`, `target.probe_summary` ← `params.summary` | — | `DeliveryRequestRecordProbes` |
| `run_probes` | approver | **DeliveryRequest** | `deployed`: Only a deployment that happened can be probed. | the stage (per the matrix) | kernel `probe` → `record_probes` | `DeliveryRequestRunProbes` |

## Transitions

For each stage: may the action happen, and where does it lead? A missing cell is undecided; nothing is ever silently allowed.

### DeliveryRequest (`stage`)

| stage | `preview` | `record_build` | `deploy` | `record_deployment` | `verify` | `record_probes` | `run_probes` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `requested` | → `previewing` | n/a | denied: Preview it first. | n/a | n/a | n/a | n/a |
| `previewing` | denied: A preview is running. | → `built` | denied: The preview has not finished. | n/a | n/a | n/a | n/a |
| `built` | → `previewing` | n/a | → `deploying` | n/a | n/a | n/a | n/a |
| `deploying` | denied: A deploy is running. | n/a | denied: A deploy is running. | → `done` | n/a | n/a | n/a |
| `done` | → `previewing` | n/a | → `deploying` | n/a | → `verified` | → `done` | → `done` |
| `verified` | n/a | n/a | n/a | n/a | denied: Already verified. | n/a | n/a |

## Always true (invariants)

- **deployed-builds-passed-their-harness** on DeliveryRequest: Nothing reaches the environment unless its harness passed.
- **verified-requests-were-deployed** on DeliveryRequest: Only a deployment that happened is verified.
- **finished-deploys-record-the-outcome** on DeliveryRequest: A finished deploy records whether it happened.
- **deploying-builds-passed-their-harness** on DeliveryRequest: A deploy starts only from a build whose harness passed.
- **verified-requests-passed-their-probes** on DeliveryRequest: A verified deployment passed its probes.

## Who may bring about an outcome (rules)

Every action that reaches the outcome is held to the rule, an action added later too.

- **only-a-person-deliveryrequest-deployed** on `DeliveryRequest.deployed`: only a person. Only a person sets the deployed of a DeliveryRequest: every action that does so today requires a person (deploy). Covers: `deploy`, `record_deployment`.
- **only-a-person-deliveryrequest-deploying** on `DeliveryRequest.deploying`: only a person. Only a person brings a DeliveryRequest to deploying: every action that does so today requires a person (deploy). Covers: `deploy`.
- **only-a-person-deliveryrequest-done** on `DeliveryRequest.done`: only a person. Only a person brings a DeliveryRequest to done: every action that does so today requires a person (deploy). Covers: `deploy`, `record_deployment`.
- **only-a-person-deliveryrequest-refusal** on `DeliveryRequest.refusal`: only a person. Only a person sets the refusal of a DeliveryRequest: every action that does so today requires a person (deploy). Covers: `deploy`, `record_deployment`.
- **only-a-person-deliveryrequest-verified** on `DeliveryRequest.verified`: only a person. Only a person brings a DeliveryRequest to verified: every action that does so today requires a person (verify). Covers: `verify`.

## Examples and scenarios

- 7 example object(s): Environment `ENV-local`, DeliveryRequest `R1`, DeliveryRequest `R2`, DeliveryRequest `R3`, DeliveryRequest `R4`, DeliveryRequest `R5`, DeliveryRequest `R6`
- scenario `deliver-preview-deploy-verify`: 8 step(s)
- scenario `a-failed-harness-is-never-deployed`: 1 step(s)
- scenario `a-refused-deploy-is-not-verified-and-can-be-retried`: 3 step(s)
- scenario `verify-needs-probes-that-passed`: 6 step(s)

## How to work in this domain

Generated from the actions, their actors, the matrix and the kernel calls: for each thing, how it comes to exist, then what can happen in each stage and who does it. Steps marked **a person only** are never taken by an agent.

### DeliveryRequest

- **request_delivery** by the system (a handoff from another domain) → `requested`

**In `requested`:**

- **preview** by `approver` → `previewing`. Needs: Already deployed; deliver again with a new request. Then starts kernel `preview`, answered by `record_build`. Run: `toprope-run --domain delivery.domain.yaml preview ID`

**In `previewing`:**

- **record_build** by the kernel, automatically (a reply) → `built`

**In `built`:**

- **preview** by `approver` → `previewing`. Needs: Already deployed; deliver again with a new request. Then starts kernel `preview`, answered by `record_build`. Run: `toprope-run --domain delivery.domain.yaml preview ID`
- **deploy** by `approver` — **a person only** — recorded as a decision → `deploying`. Needs: Deploy only a build whose harness passed. Then starts kernel `deploy`, answered by `record_deployment`. Run: `toprope-run --domain delivery.domain.yaml deploy ID`

**In `deploying`:**

- **record_deployment** by the kernel, automatically (a reply) → `done`

**In `done`:**

- **preview** by `approver` → `previewing`. Needs: Already deployed; deliver again with a new request. Then starts kernel `preview`, answered by `record_build`. Run: `toprope-run --domain delivery.domain.yaml preview ID`
- **deploy** by `approver` — **a person only** — recorded as a decision → `deploying`. Needs: Deploy only a build whose harness passed. Then starts kernel `deploy`, answered by `record_deployment`. Run: `toprope-run --domain delivery.domain.yaml deploy ID`
- **verify** by `approver` — **a person only** → `verified`. Needs: Only a deployment that happened can be verified. Run the probes on the deployment first; verify only one whose probes passed. Run: `toprope-run --domain delivery.domain.yaml verify ID`
- **record_probes** by the kernel, automatically (a reply)
- **run_probes** by `approver`. Needs: Only a deployment that happened can be probed. Then starts kernel `probe`, answered by `record_probes`. Run: `toprope-run --domain delivery.domain.yaml run_probes ID`

**In `verified`:** nothing more happens (final).

## What is generated

- **Command line** `toprope-run --domain delivery.domain.yaml ...`: one subcommand per action, with the same rules as every other surface (ADR-0036), plus `get`, `history`, `allowed` and `guide`.
- **MCP server** `toprope:delivery`: one tool per action (8), plus `get_object`, `history`, `attempts`, `allowed_actions`, `describe_domain`, `world_map` and `how_to_reach`. Kernel replies (`record_build`, `record_deployment`, `record_probes`) are tools too, but only the kernel may take them.
- **Events**: one per action (`DeliveryRequestCreated`, `DeliveryRequestDeploy`, `DeliveryRequestPreview`, `DeliveryRequestRecordBuild`, `DeliveryRequestRecordDeployment`, `DeliveryRequestRecordProbes`, `DeliveryRequestRunProbes`, `DeliveryRequestVerify`); the current state is the events replayed in order.
- **World map** (`world-map.json`): every object, link, stage and (stage, action) edge.
- **Harness**: passes; decided cells covered per level: model 84/84, execution 84/84; 0 finding(s).
