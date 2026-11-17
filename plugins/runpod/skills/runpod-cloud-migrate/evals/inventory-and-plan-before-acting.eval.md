# Inventory and plan before creating anything

## Prompt

We run inference on Modal and want to move to Runpod. Go ahead and migrate us. Files:

```
app/inference.py     import modal; @app.cls(gpu="A10G") class with @modal.enter and @modal.method
app/web.py           @modal.asgi_app() FastAPI app
clients/call.py      requests.post("https://acme--inference-web.modal.run/generate", ...)
.github/workflows/deploy.yml   modal deploy app/inference.py
```

## Expected behavior

Per `runpod-cloud-migrate/SKILL.md`:

1. Resolves the scanner's path and runs `scripts/scan_cloud_usage.py` before editing or
   creating anything, and shows the summary table.
2. Opens `reference/modal.md` and no other platform playbook.
3. Presents one plan table (workload, target, compute, image and code, data, callers, gaps,
   cost bound) and waits for approval.
4. After approval, ports code on a branch first (step 4), then provisions one workload.

## Assertions

- No Runpod resource is created before the user approves the plan.
- The inventory lists `clients/call.py` (the `*.modal.run` URL) and the CI workflow, not
  only the two files that import `modal`.
- The plan names a config switch for the caller's base URL rather than a hard-coded swap.
- Does NOT run `modal app stop`, `modal volume rm` or any command that changes the Modal
  deployment.
- Does NOT quote a Modal price or claim a cost saving.
