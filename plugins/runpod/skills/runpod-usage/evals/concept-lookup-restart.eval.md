# Answer an exact-fact question from the concept files

## Prompt

I stopped my pod last night. The console shows my GPU type available in that data
center, but starting the pod again fails with no GPUs available. Why, and what should
I do?

## Expected behavior

Per `runpod-usage/SKILL.md` ("Exact facts: the concept files"):

1. The agent should find the matching concept files (`pod-deployment.yaml`, `machine.yaml`)
   rather than answer from memory.
2. It should explain that a pod is bound to the machine it was placed on. Stopping releases
   that machine's GPUs, so others can rent them, and data-center stock does not mean the pod's
   own machine has a free GPU.
3. It should give the fix the rules support: wait and retry, start with zero GPUs to
   reach the volume disk, or keep data on a network volume and deploy a new pod anywhere in that
   data center.

## Assertions

- Explains that a stopped pod restarts only on its own machine, not anywhere in the data center.
- Distinguishes data-center stock from the pod's machine having a free GPU.
- Recommends a network volume, which any pod in the data center can attach, for data that must survive this.
- Does NOT tell the user to simply retry in another data center without moving their data.
