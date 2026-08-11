// Nightly capacity + price report. Uses the Runpod GraphQL API.
const RUNPOD_GRAPHQL = "https://api.runpod.io/graphql";

async function gql(query, variables = {}) {
  const res = await fetch(`${RUNPOD_GRAPHQL}?api_key=${process.env.RUNPOD_API_KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  const json = await res.json();
  if (json.errors) throw new Error(JSON.stringify(json.errors));
  return json.data;
}

export async function accountSummary() {
  return gql(`query { myself { id email currentSpendPerHr clientBalance } }`);
}

export async function gpuPrices() {
  const data = await gql(`
    query {
      gpuTypes {
        id
        displayName
        memoryInGb
        secureCloud
        communityCloud
        lowestPrice(input: { gpuCount: 1, secureCloud: true }) {
          stockStatus
          uninterruptablePrice
          availableGpuCounts
        }
      }
    }
  `);
  return data.gpuTypes;
}

export async function runningPods() {
  const data = await gql(`
    query {
      myself {
        pods {
          id
          name
          desiredStatus
          costPerHr
          machineId
          runtime { uptimeInSeconds gpus { gpuUtilPercent memoryUtilPercent } }
        }
      }
    }
  `);
  return data.myself.pods;
}

export async function scaleEndpoint(id, workersMax) {
  return gql(`
    mutation {
      saveEndpoint(input: {
        id: "${id}",
        gpuIds: "AMPERE_16",
        locations: "US",
        workersMax: ${workersMax},
        scalerType: "QUEUE_DELAY",
        scalerValue: 4,
        idleTimeout: 5,
        flashBootType: FLASHBOOT,
        templateId: "${process.env.TEMPLATE_ID}"
      }) { id name workersMax }
    }
  `);
}

export async function retireEndpoint(id) {
  return gql(`mutation { deleteEndpoint(id: "${id}") }`);
}
