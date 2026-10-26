# Fast disk for installs on a pod

## Prompt

`pip install` and unpacking a dataset into `/workspace` on my pod are slow. Someone told me
regions with network volumes put everything on network storage, so I should move to a data
center without network volumes to get a local disk. Is that right?

## Expected behavior

The agent should:

1. Say the container disk (`/`, including `/root`, `/opt`, `/tmp`) is local, so installs
   outside `/workspace` are fast wherever the pod runs
2. Say `/workspace` (the volume disk) is network-backed in data centers that offer network
   volumes, and that a data center without network volumes does not guarantee a local
   `/workspace`
3. Suggest `findmnt /workspace` to check (`fuse` = network-backed, `xfs` on a device = local)
4. Recommend installing packages, building and unpacking scratch data on the container disk,
   sized with `--container-disk-in-gb`, and keeping only what must survive a restart in
   `/workspace`
5. Note that the container disk is wiped when the pod stops or restarts, so anything that must
   survive goes in `/workspace` or a network volume

## Assertions

- States the container disk is local and faster than a network-backed `/workspace`
- Does NOT treat "no network volumes" as a guarantee of a local `/workspace`
- Does NOT recommend switching data centers just for disk speed
- Mentions checking with `findmnt /workspace`
- Recommends the container disk for installs and scratch, and mentions sizing it
- Notes the container disk is wiped on stop or restart
