# Golden path 28: share model files across data centers with a global volume

## Prompt

I run the same model from Pods and a Serverless endpoint, and I keep copying the weights to a
network volume in each data center so the GPUs can find them. Set it up so the weights live
in one place and any data center can use them.

## Expected behavior

Follows [golden path 28](../golden-paths/28-global-volume/README.md): states that a global volume
bills for stored data plus per-request fees before creating it, creates it with only a `name`
(`create-global-volume` or `POST /v2/global-volumes`) and keeps the returned id. Writes the
files from a short-lived Pod that mounts the volume under `mounts.global` with an explicit
`path`, reads that path back, checks the file list, and deletes the Pod, also when the copy
fails. Only then attaches the volume to a GPU endpoint under `mounts.global`, with no network
volumes on the same endpoint and `dataCenterIds` unset, and points the handler at
`/runpod-volume`. Verifies with a real request, and on cleanup deletes every Pod and the
endpoint before `delete-global-volume`.

## Assertions

- Quotes the billing shape (stored data plus per-request fees) before the create
- Sends only `name` on the create; no size or data center
- Writes the files before any worker or GPU Pod, other than a GPU fill Pod, starts on the
  volume
- After a failed copy, deletes the fill Pod before reporting the failure
- Attaches the volume to a GPU endpoint without network volumes and without pinning
  `dataCenterIds`, and reads the files at `/runpod-volume`
- Reads `mounts.global[0].path` back from the Pod instead of assuming a default
- Does not recommend the global volume for checkpoints or other write-heavy work while a data
  center with network storage and stock is available
- Deletes Pods and the endpoint before the volume, and reports a `409` instead of detaching
  anything the user did not ask to remove
