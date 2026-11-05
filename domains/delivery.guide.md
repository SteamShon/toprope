# Domain guide: `delivery` (version 1)

_Generated from the declaration at build time. Do not edit: change the declaration._

## Purpose

An approved domain version must become working software in an environment, and nothing unverified may reach it.

**Success metric:** share of approved versions that reach verified-in-use without a manual fix or rollback (up is better)

> Approved domain versions now reach the environment as working software in one step. Nothing that fails its checks or lacks a person's approval gets there.

## People and things

**Roles:** `approver` (ana). Agents act only on a person's behalf, with a grant.

- **DeliveryRequest**: A request to deliver an approved commit of a domain, handed off by Authoring. Stages: `requested`, `previewing`, `previewed`, `deploying`, `done`, `verified` (starts `requested`).
  - facts: `domain_id` (string), `commit` (string), `interface` (string), `environment` (string), `approver` (string), `build` (string, optional), `harness_ok` (boolean, optional), `deployed` (boolean, optional), `refusal` (string, optional), `verified` (boolean, optional)
- **Environment**: Where a domain runs; it points at one deployed commit.
  - facts: `name` (string), `current_commit` (string, optional)

## Actions

🔒 only a person may take it · 📝 recorded as a decision

| action | who | on | needs first | changes | starts | event |
| --- | --- | --- | --- | --- | --- | --- |
| `request_delivery` | system | creates **DeliveryRequest**; params `domain_id` (string), `commit` (string), `interface` (string), `environment` (string), `approver` (string) | — | — | — | `DeliveryRequestCreated` |
| `preview` | approver | **DeliveryRequest** | — | the stage (per the matrix) | kernel `preview` → `record_build` | `DeliveryRequestPreview` |
| `record_build` | the kernel | **DeliveryRequest**; params `build` (string), `harness_ok` (boolean) | — | the stage (per the matrix); `target.build` ← `params.build`, `target.harness_ok` ← `params.harness_ok` | — | `DeliveryRequestRecordBuild` |
| `deploy` 🔒 📝 | approver | **DeliveryRequest** | `harness-passed`: Deploy only a build whose harness passed. | the stage (per the matrix) | kernel `deploy` → `record_deployment` | `DeliveryRequestDeploy` |
| `record_deployment` | the kernel | **DeliveryRequest**; params `deployed` (boolean), `error` (string) | — | the stage (per the matrix); `target.deployed` ← `params.deployed`, `target.refusal` ← `params.error` | — | `DeliveryRequestRecordDeployment` |
| `verify` 🔒 | approver | **DeliveryRequest**; params `verified` (boolean) | `deployed`: Only a deployment that happened can be verified. | the stage (per the matrix); `target.verified` ← `params.verified` | — | `DeliveryRequestVerify` |

## Transitions

For each stage: may the action happen, and where does it lead? A missing cell is undecided; nothing is ever silently allowed.

### DeliveryRequest (`stage`)

| stage | `preview` | `record_build` | `deploy` | `record_deployment` | `verify` |
| --- | --- | --- | --- | --- | --- |
| `requested` | → `previewing` | n/a | denied: Preview it first. | n/a | n/a |
| `previewing` | denied: A preview is running. | → `previewed` | denied: The preview has not finished. | n/a | n/a |
| `previewed` | → `previewing` | n/a | → `deploying` | n/a | n/a |
| `deploying` | denied: A deploy is running. | n/a | denied: A deploy is running. | → `done` | n/a |
| `done` | → `previewing` | n/a | → `deploying` | n/a | → `verified` |
| `verified` | n/a | n/a | n/a | n/a | denied: Already verified. |

## Always true (invariants)

- **deployed-builds-passed-their-harness** on DeliveryRequest: Nothing reaches the environment unless its harness passed.
- **verified-requests-were-deployed** on DeliveryRequest: Only a deployment that happened is verified.
- **finished-deploys-record-the-outcome** on DeliveryRequest: A finished deploy records whether it happened.

## Examples and scenarios

- 5 example object(s): Environment `ENV-local`, DeliveryRequest `R1`, DeliveryRequest `R2`, DeliveryRequest `R3`, DeliveryRequest `R4`
- scenario `deliver-preview-deploy-verify`: 6 step(s)
- scenario `a-failed-harness-is-never-deployed`: 1 step(s)
- scenario `a-refused-deploy-is-not-verified-and-can-be-retried`: 2 step(s)

## What is generated

- **MCP server** `toprope:delivery`: one tool per action (6), plus `get_object`, `history`, `attempts`, `allowed_actions`, `describe_domain`, `world_map` and `how_to_reach`. Kernel replies (`record_build`, `record_deployment`) are tools too, but only the kernel may take them.
- **Events**: one per action (`DeliveryRequestCreated`, `DeliveryRequestDeploy`, `DeliveryRequestPreview`, `DeliveryRequestRecordBuild`, `DeliveryRequestRecordDeployment`, `DeliveryRequestVerify`); the current state is the events replayed in order.
- **World map** (`world-map.json`): every object, link, stage and (stage, action) edge.
- **Harness**: passes; decided cells covered per level: model 60/60, execution 60/60, mcp 60/60; 0 finding(s).
