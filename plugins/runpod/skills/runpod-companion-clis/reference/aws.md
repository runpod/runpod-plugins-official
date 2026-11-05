---
concepts: [network-volume, data-center, file-transfer]
---

# AWS CLI

The AWS CLI is used to access Runpod storage over the S3 protocol. Any Runpod product that can mount a Network Volume — pods, clusters, and serverless endpoints — can have its storage accessed this way. The bucket name is the network volume ID.

> **Not installed?** One-time install lives in [`aws-setup.md`](aws-setup.md) — skip if `aws --version` already works.

## Credentials

Runpod uses its own S3-compatible API, not AWS. You need a Runpod user ID and S3 API key — not an AWS account.

- **Access key** (`AWS_ACCESS_KEY_ID`): your Runpod user ID — found in the console under Settings > S3 API Keys, in the key description (format: `user_...`)
- **Secret key** (`AWS_SECRET_ACCESS_KEY`): an S3 API key — generate one at Settings > S3 API Keys > Create. Shown only once; save it immediately (format: `rps_...`)

> **S3 API keys are Console-only.** There is **no** `runpodctl` command and **no**
> REST/GraphQL endpoint to create an S3 API key or read the user ID; both come from the
> Console (Settings > S3 API Keys), so an agent cannot self-provision them. (This differs
> from the regular `RUNPOD_API_KEY`, which the CLI can save.) Note the AWS access key must
> be the Runpod **user id** (`user_...`), not the `RUNPOD_API_KEY`.
>
> **Rule:** if an operation needs S3-API access and no S3 credentials are present in
> `~/.aws/credentials` or env vars, stop and ask the user to generate them in the Console —
> do not attempt to self-provision them.

```bash
# Option 1: interactive configure (writes ~/.aws/credentials and ~/.aws/config)
# When prompted: enter user ID as access key, S3 API key as secret.
# Press Enter to skip region and output format — region is always passed per-command, not stored in config.
aws configure

aws configure list    # verify stored credentials

# Option 2: environment variables (override config files)
export AWS_ACCESS_KEY_ID=user_...
export AWS_SECRET_ACCESS_KEY=rps_...

# To stop using env vars and fall back to config file:
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
```

## Region and Endpoint

The `--region` flag on every command is the Runpod datacenter ID where the network volume lives — not an AWS region. The `--endpoint-url` is derived from the same datacenter ID.

Every command requires both flags. **`--region` takes the DC id as-is, but the
`--endpoint-url` host must be LOWERCASED** — `s3api-eu-ro-1…`, not `s3api-EU-RO-1…`
(an upper-cased host fails to resolve):
```
--region <DC> --endpoint-url https://s3api-<dc-lowercased>.runpod.io/
# DC EU-RO-1  →  --region EU-RO-1  --endpoint-url https://s3api-eu-ro-1.runpod.io/
```

**Tip:** Each network volume on the storage page at https://console.runpod.io/user/storage/ shows a pre-filled example `aws s3 ls` command with the correct `--region` and `--endpoint-url` already substituted. Use this to confirm the exact values for a given volume.

Datacenter IDs are **region-prefixed**; they go verbatim into `--region <DC>` but must be
**lowercased** in the host `https://s3api-<dc-lowercased>.runpod.io/`. `runpodctl datacenter
list` is authoritative — the set grows over time; run it for the current list. Common ones:

| Region | Datacenter IDs |
|--------|---------------|
| EU | EU-CZ-1, EU-RO-1, EU-NL-1, EU-FR-1, EUR-IS-1, EUR-NO-1 |
| US | US-CA-2, US-GA-1, US-GA-2, US-IL-1, US-KS-2, US-MD-1, US-MO-1, US-NC-1, US-TX-1, US-WA-1 |
| Other | CA-MTL-1, AP-JP-1, AP-IN-1, SEA-SG-1, OC-AU-1 |

## Key Commands

Replace `DATACENTER` (in `--region`) with your network volume's datacenter ID **as-is**
(e.g. `US-CA-2`), `<dc-lowercased>` (in the host) with that **same id lowercased**
(`us-ca-2`), and `NETWORK_VOLUME_ID` with the volume ID (the S3 bucket name).

```bash
# List files in a volume
aws s3 ls \
  --region DATACENTER \
  --endpoint-url https://s3api-<dc-lowercased>.runpod.io/ \
  s3://NETWORK_VOLUME_ID/

# List a subdirectory
aws s3 ls \
  --region DATACENTER \
  --endpoint-url https://s3api-<dc-lowercased>.runpod.io/ \
  s3://NETWORK_VOLUME_ID/my-folder/

# Upload a file
aws s3 cp local-file.txt \
  --region DATACENTER \
  --endpoint-url https://s3api-<dc-lowercased>.runpod.io/ \
  s3://NETWORK_VOLUME_ID/

# Download a file
aws s3 cp \
  --region DATACENTER \
  --endpoint-url https://s3api-<dc-lowercased>.runpod.io/ \
  s3://NETWORK_VOLUME_ID/remote-file.txt ./

# Delete a file
aws s3 rm \
  --region DATACENTER \
  --endpoint-url https://s3api-<dc-lowercased>.runpod.io/ \
  s3://NETWORK_VOLUME_ID/remote-file.txt

# Sync a local directory to a volume
aws s3 sync local-dir/ \
  --region DATACENTER \
  --endpoint-url https://s3api-<dc-lowercased>.runpod.io/ \
  s3://NETWORK_VOLUME_ID/remote-dir/
```

Path mapping: `/workspace/my-folder/file.txt` on a pod = `s3://NETWORK_VOLUME_ID/my-folder/file.txt` via S3.

## Troubleshooting

```bash
# Retry on timeout (large transfers)
export AWS_RETRY_MODE=standard
export AWS_MAX_ATTEMPTS=10

# Extend read timeout for large files (seconds)
aws s3 cp large-file.zip \
  --region DATACENTER \
  --endpoint-url https://s3api-<dc-lowercased>.runpod.io/ \
  --cli-read-timeout 7200 \
  s3://NETWORK_VOLUME_ID/
```

## Optional: resumable volume transfers (community tool)

`aws s3 sync` is fine for modest trees but has weak resume and struggles past ~10,000
files — painful for large model weights or when replicating the same data to several
volumes (see golden path [10 — multi-region HA serverless](../../runpod/golden-paths/10-multi-region-ha-serverless.md)).
For that, the community **Runpod Network Volume Storage Tool** wraps the same S3 API
with **resumable multipart uploads** (auto chunk sizing, MD5-verified resume),
directory sync with excludes, an interactive file browser, a Python SDK, and a REST
server. It's referenced in the official docs under
[community solutions](https://docs.runpod.io/community-solutions/runpod-network-volume-storage-tool).

```bash
git clone https://github.com/justinwlin/Runpod-Network-Volume-Storage-Tool.git
cd Runpod-Network-Volume-Storage-Tool && uv sync

# Same S3 credentials as the AWS CLI above (access key = user id, secret = rps_... key)
export RUNPOD_API_KEY=...
export RUNPOD_S3_ACCESS_KEY=user_...
export RUNPOD_S3_SECRET_KEY=rps_...

uv run runpod-storage upload ./model-artifacts <volume-id>   # resumable — re-run to resume
uv run runpod-storage list-volumes
```

Plain `aws s3` (above) stays the zero-dependency baseline; reach for this tool when
resume/large-tree reliability matters.
