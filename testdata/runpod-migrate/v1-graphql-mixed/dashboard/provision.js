// One-off pod provisioning from the ops dashboard (GraphQL).
import { gql } from "./capacity.js";

export async function deployWorker(name, imageName) {
  return gql(`
    mutation {
      podFindAndDeployOnDemand(input: {
        cloudType: SECURE,
        gpuCount: 1,
        gpuTypeId: "NVIDIA RTX A6000",
        name: "${name}",
        imageName: "${imageName}",
        containerDiskInGb: 40,
        volumeInGb: 40,
        volumeMountPath: "/workspace",
        minVcpuCount: 8,
        minMemoryInGb: 32,
        ports: "8888/http,22/tcp",
        dockerArgs: "",
        env: [{ key: "JUPYTER_PASSWORD", value: "hunter2" }]
      }) { id imageName machineId machine { podHostId } }
    }
  `);
}

export async function stopWorker(podId) {
  return gql(`mutation { podStop(input: { podId: "${podId}" }) { id desiredStatus } }`);
}

export async function resumeWorker(podId) {
  return gql(`mutation { podResume(input: { podId: "${podId}", gpuCount: 1 }) { id desiredStatus } }`);
}

export async function killWorker(podId) {
  return gql(`mutation { podTerminate(input: { podId: "${podId}" }) }`);
}
