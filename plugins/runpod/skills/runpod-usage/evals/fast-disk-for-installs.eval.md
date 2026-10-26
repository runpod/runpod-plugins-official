# Fast disk for installs on a pod

## Prompt

`pip install` and unpacking a dataset into `/workspace` on my pod are slow. Someone told me
regions with network volumes put everything on network storage, so I should move to a data
center without network volumes to get a local disk. Is that right?

## Expected behavior

The agent should:

1. Say the container disk (`/`, including `/root`, `/opt`, `/tmp`) is local and the fastest
   storage a pod has, in every data center
2. Say `/workspace` (the volume disk) is network-backed wherever the data center runs a network
   storage cluster, and that offering network volumes is not the signal: some data centers
   without network volumes still run one. Only a data center with no storage cluster gives a
   local `/workspace`
3. Suggest `findmnt /workspace` to check (`fuse` = network, `xfs` on a device = local)
4. Recommend installing packages, building and unpacking scratch data on the container disk,
   sized with `--container-disk-in-gb`, and keeping only what must survive a restart in
   `/workspace`

## Assertions

- States the container disk is local and faster than `/workspace`
- Does NOT treat "no network volumes" as meaning a local `/workspace`
- Mentions checking with `findmnt /workspace`
- Recommends the container disk for installs and scratch, and mentions sizing it
- Notes the container disk is wiped on stop or restart
