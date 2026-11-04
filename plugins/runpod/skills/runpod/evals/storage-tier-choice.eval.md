# Golden path 21: pick a network-volume storage tier

## Prompt

Create a high-performance network volume for my training data, 200 GB, wherever it is
cheapest to run an A100 next to it.

## Expected behavior

Follows [golden path 21](../golden-paths/21-storage-tiers.md): reads the data-center
catalog (`list-data-centers` / `GET /v2/catalog/datacenters`) and only considers DCs whose
`networkVolumeTypes` include `HIGH_PERFORMANCE`, then intersects with A100 stock. Creates
with MCP `create-network-volume` and its `volumeType`, or REST v2 `type:
"HIGH_PERFORMANCE"`, not `runpodctl` unless `runpodctl network-volume create --help`
lists a tier flag (none through v2.14.0). Says the tier is immutable and quotes
the storage cost before creating (a volume bills for as long as it exists).

## Assertions

- Chooses the data center from the live `networkVolumeTypes` read, not from an example
- Requests the tier through MCP `volumeType` or REST v2 `type`, unless
  `runpodctl network-volume create --help` lists a tier flag
- States that the tier cannot be changed later
- Quotes the cost before the create
