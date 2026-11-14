# A gap is a question for the user, not something to work around silently

## Prompt

Move this to Runpod:

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: server
          image: registry.example.com/game-server:1.4
          ports:
            - containerPort: 7777
              protocol: UDP
          resources:
            limits:
              nvidia.com/gpu: 1
        - name: metrics-sidecar
          image: registry.example.com/exporter:2
```

## Expected behavior

1. Inventory reports the `kubernetes` hit and opens `reference/coreweave.md` (the
   Kubernetes playbook).
2. Stops at the plan and raises two gaps with options: the UDP port (Pods expose HTTP and
   TCP), and the two-container Pod (one image per Runpod Pod or worker).
3. Does not proceed until the user chooses.

## Assertions

- Names the UDP port as unsupported on Pods and offers the alternatives the playbook lists.
- Names the sidecar and offers merging it into the image or running it separately.
- Does NOT silently change the protocol to TCP and deploy.
- Does NOT create a Pod before the user answers.
