# Golden paths 10 and 19: one serverless endpoint across several regions' volumes

## Prompt

My endpoint reads model files from a network volume in EU-RO-1 and can't scale when that
data center runs out of capacity. Make it serve from more regions.

## Expected behavior

Follows [golden path 10](../golden-paths/10-multi-region-ha-serverless.md) (19 for three
regions): one network volume per data center, attached to the same endpoint (v2
`mounts.network`, at most one per data center, or `runpodctl serverless create
--network-volume-ids` on v2.4.0+). States the catch up front: the volumes do **not** sync,
so the agent copies identical data to each (S3 API by default, which needs the user's
Console-only S3 keys; a CPU pod otherwise) and verifies parity before relying on it. Sets
`timeout` on the create and reports which data centers served test requests.

## Assertions

- Creates one volume per data center and attaches all of them to one endpoint
- Says the volumes do not sync and verifies identical contents
- Asks the user for S3 API keys rather than trying to create them, or uses a pod instead
- Sets `timeout` explicitly on the endpoint create
