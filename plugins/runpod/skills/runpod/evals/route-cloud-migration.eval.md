# Route a move from another platform to runpod-cloud-migrate

## Prompt

We have a FastAPI inference service on Google Cloud Run with an L4 GPU and a SageMaker
endpoint we inherited. What would it take to run both on Runpod?

## Expected behavior

Per `runpod/SKILL.md` routing step 7:

1. Routes to **runpod-cloud-migrate**, not to runpod-migrate (which moves Runpod code
   between Runpod API versions) and not straight to an infra lane.
2. That skill inventories the repo, opens the Google Cloud and AWS playbooks, and stops at
   a plan because the user asked what it would take.

## Assertions

- Loads `runpod-cloud-migrate/SKILL.md` before proposing any Runpod resource.
- Does NOT load `runpod-migrate` for this request.
- Creates nothing on Runpod and changes nothing on Google Cloud or AWS.
- The answer is a plan with targets, gaps and a cost bound, not a generic comparison.
