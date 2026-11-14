---
concepts: [pod, serverless-endpoint, template, container-image, registry-credential, network-volume, endpoint-autoscaling, runpod-secret]
---
# Migrate from AWS to Runpod

Scope: move GPU and AI workloads from Amazon EC2 (G and P families), SageMaker AI (real-time, async, batch, training, notebooks), Amazon Bedrock, AWS Batch/ECS/EKS on GPU, and ParallelCluster/HyperPod to Runpod Pods, Serverless endpoints, Public Endpoints, and Instant Clusters. The default outcome is hybrid: GPU compute on Runpod, with S3, IAM, databases, and non-GPU services staying on AWS. Treat a full AWS exit as a separate, explicit user decision.

Sources: AWS docs, checked 2026-11-14: [EC2 accelerated computing specs](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html), [SageMaker inference container contract](https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-inference-code.html), [async inference](https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference.html), [Serverless Inference](https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html), [endpoint auto scaling](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling-add-policy.html), [training container layout](https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-training-algo-running-container.html), [Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html), [Bedrock Chat Completions](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions.html), [ECR registry auth](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html), [EC2 instance lifecycle](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html).

Runpod command syntax: [runpodctl skill](../../runpodctl/SKILL.md). Storage and networking behavior: [storage](../../runpod-usage/reference/storage.md), [networking](../../runpod-usage/reference/networking.md), [secrets](../../runpod-usage/reference/secrets.md), [gotchas](../../runpod-usage/reference/gotchas.md).

## Detect

| Signal (grep) | What it means | Lands on |
| --- | --- | --- |
| `boto3.client("sagemaker-runtime"` or `invoke_endpoint(` | Caller of a SageMaker real-time endpoint | Client rewrite to `/runsync` or a load balancing URL |
| `invoke_endpoint_async(` or `AsyncInferenceConfig` | SageMaker asynchronous inference | Serverless queue endpoint, `/run` with `webhook` |
| `invoke_endpoint_with_response_stream(` | Streaming inference | Queue endpoint `/stream`, or load balancing endpoint |
| `def model_fn(` with `def predict_fn(` | SageMaker framework inference script | Queue endpoint with a handler wrapper |
| `/invocations` with `/ping` in server code, or port `8080` | SageMaker bring-your-own inference container | Serverless load balancing endpoint |
| `/opt/ml/model`, `/opt/ml/input/data`, `SM_MODEL_DIR` | SageMaker container paths | Image path, network volume, or env var |
| `from sagemaker` with `Estimator(` or `.fit(` | SageMaker training job | Pod, or `@app.task` |
| `create_transform_job` or `Transformer(` | Batch transform | Queue endpoint, one `/run` job per shard |
| `boto3.client("bedrock-runtime"` with `.converse(` or `.invoke_model(` | Bedrock inference | Public Endpoint or Serverless vLLM endpoint |
| `bedrock-runtime.` with `/openai/v1` | Bedrock OpenAI-compatible calls | Base URL, key, and model swap |
| `aws ec2 run-instances` or `--user-data` | EC2 launch script | Pod with a custom image |
| `instance_type` matching `(g4dn\|g5\|g5g\|g6\|g6e\|g7\|g7e\|p3dn\|p4d\|p4de\|p5\|p5e\|p5en\|p6)` | GPU instance in IaC | `runpod_pod` or Serverless endpoint |
| `ml\.(g\|p)[0-9]` | SageMaker GPU instance type | `gpu_pools` on a Serverless endpoint |
| `resource "aws_sagemaker_endpoint"` or `aws_sagemaker_model` | SageMaker in Terraform | `runpod_template` and `runpod_serverless_endpoint` |
| `resource "aws_appautoscaling_` with `sagemaker` | Endpoint autoscaling | `workers_min`, `workers_max`, `scaling_type` |
| `resource "aws_instance"` or `aws_launch_template` | EC2 in Terraform | `runpod_pod` |
| `dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com` | ECR image reference | Keep ECR with a delegation, or push elsewhere |
| `169\.254\.169\.254` | EC2 instance metadata calls | `RUNPOD_*` env vars |
| `linux/arm64` or `aarch64` in Dockerfiles or CI | Graviton images | Rebuild for `linux/amd64` |
| `pcluster` or `HeadNode:` in YAML, `sagemaker create-cluster` | ParallelCluster or HyperPod | Instant Cluster with Slurm |
| `aws_batch_job_definition`, `resourceRequirements` with `GPU` | AWS Batch GPU jobs | Queue endpoint or Pods |
| `nvidia.com/gpu` in Kubernetes manifests with EKS | EKS GPU workloads | Serverless endpoint, or SkyPilot/dstack onto Pods |

Inventory commands (read-only, per Region): `aws ec2 describe-instances`, `aws ec2 describe-instance-attribute --attribute userData`, `aws sagemaker list-endpoints`, `aws sagemaker describe-endpoint`, `aws sagemaker describe-endpoint-config`, `aws sagemaker describe-model`, `aws application-autoscaling describe-scalable-targets --service-namespace sagemaker`, `aws sagemaker list-notebook-instances`, `aws bedrock list-provisioned-model-throughputs`, `aws ecr describe-repositories`, `aws ec2 describe-volumes`, `aws efs describe-file-systems`, `aws fsx describe-file-systems`.

## Product map

| AWS | Runpod | Notes |
| --- | --- | --- |
| EC2 GPU instance | Pod | Container, not a VM. No Docker Compose, UDP, or Windows. |
| AMI, DLAMI, user data | Image plus start command | Move install steps into the Dockerfile. |
| Launch template + Auto Scaling group | Serverless endpoint | Pods do not autoscale. |
| SageMaker real-time endpoint (BYO container) | Load balancing endpoint | Same `/ping` idea; port differs. |
| SageMaker real-time endpoint (`inference.py`) | Queue endpoint | Handler wraps `model_fn` and `predict_fn`. |
| SageMaker async inference, batch transform | Queue endpoint | `/run`, `webhook`, scale to zero. |
| SageMaker Serverless Inference (CPU only on AWS) | Serverless endpoint, GPU or CPU | |
| SageMaker training and processing jobs | Pod or `@app.task` | One ephemeral Pod per call with `@app.task`. |
| SageMaker Studio, notebook instances | Pod with JupyterLab (port 8888) | |
| Bedrock on-demand, JumpStart LLMs | Public Endpoint if the model is listed, else vLLM endpoint | OpenAI-compatible route. |
| Bedrock Provisioned Throughput, Custom Model Import | Serverless vLLM endpoint | Set min workers for warm capacity. |
| AWS Batch, ECS GPU, EKS GPU node groups | Queue endpoint, Pods, SkyPilot, dstack | |
| ParallelCluster, HyperPod (Slurm) | Instant Cluster with Slurm | Capacity depends on stock at create time. |
| Lambda | Stays on AWS | CPU Serverless endpoint only for GPU-adjacent glue. |
| ECR | ECR delegation, or any registry | |
| EBS root / EBS data / EFS, FSx | Container disk / volume disk or network volume / network volume | Network volume is pinned to one data center. |
| S3 | Stays on AWS, or network volume | Runpod S3-compatible API is a file interface to a volume. |
| Secrets Manager, SSM parameters | Runpod secrets, `{{ RUNPOD_SECRET_name }}` in env | |
| IAM role, instance profile | Scoped IAM keys stored as secrets | No AWS identity on a Pod or worker. |
| Security group | `ports` | HTTP proxy URL is public and unauthenticated. |
| CloudWatch Logs | `runpodctl pod logs`, `runpodctl serverless logs` | |

GPU map (EC2 family: GPU, then Runpod GPU type ID, then Serverless pool):

| EC2 | GPU | Runpod GPU type ID | Pool |
| --- | --- | --- | --- |
| `g4dn` | T4 16 GB | `NVIDIA RTX A4000`, `NVIDIA RTX 2000 Ada Generation`, `NVIDIA L4` | `AMPERE_16`, `AMPERE_24` |
| `g5` | A10G 24 GB | `NVIDIA RTX A5000`, `NVIDIA L4`, `NVIDIA GeForce RTX 4090` | `AMPERE_24`, `ADA_24` |
| `g6`, `gr6` | L4 24 GB | `NVIDIA L4` | `AMPERE_24` |
| `g6e` | L40S 48 GB | `NVIDIA L40S` | `ADA_48_PRO` |
| `g7` | RTX PRO 4500 32 GB | `NVIDIA RTX PRO 4500 Blackwell` | read from `runpodctl gpu list` |
| `g7e` | RTX PRO 6000 96 GB | `NVIDIA RTX PRO 6000 Blackwell Server Edition` | read from `runpodctl gpu list` |
| `p3dn` | V100 32 GB | `Tesla V100-SXM2-32GB` | none listed |
| `p4d`, `p4de` | A100 40 GB / 80 GB | `NVIDIA A100 80GB PCIe`, `NVIDIA A100-SXM4-80GB` | `AMPERE_80` |
| `p5` | H100 80 GB | `NVIDIA H100 80GB HBM3`, `NVIDIA H100 PCIe` | `ADA_80_PRO` |
| `p5e`, `p5en` | H200 141 GB | `NVIDIA H200` | `HOPPER_141` |
| `p6-b200`, `p6e-gb200` | B200 | `NVIDIA B200` | read from `runpodctl gpu list` |
| `p6-b300` | B300 | `NVIDIA B300 SXM6 AC` | read from `runpodctl gpu list` |

`g5g` and `p6e-gb200` are Arm hosts: rebuild images for `linux/amd64`. Always read live stock with `runpodctl gpu list` and choose by VRAM fit for the model.

## Field map

| AWS field | REST v2 field | runpodctl flag | Terraform argument |
| --- | --- | --- | --- |
| `InstanceType` (EC2) | `gpu.id`, `gpu.count` | `--gpu-id`, `--gpu-count` | `gpu_type_id`, `gpu_count` |
| `InstanceType` (`ml.*`) | `gpu.pools`, `gpu.count` | `--gpu-id POOL_ID` | `gpu_pools`, `gpu_count` |
| `ImageId`, `PrimaryContainer.Image` | `image` | `--image` | `image` |
| `UserData` | `cmd`, `entrypoint`, `args` | `--docker-args` | `args` |
| `Environment` | `env` | `--env` | `env` |
| Security group ingress | `ports` (`8000/http`, `22/tcp`) | `--ports` | `ports` |
| Root volume size | `disk` | `--container-disk-in-gb` | `disk` |
| EBS data volume | `mounts.persistent`, `mounts.network` | `--volume-in-gb`, `--network-volume-id` | `persistent_volume`, `network_volumes` |
| Region, AZ | `dataCenterIds` | `--data-center-ids` | `data_center_ids` |
| `InitialInstanceCount`, `MinCapacity` | `workers.min` | `--workers-min` | `workers_min` |
| `MaxCapacity` | `workers.max` | `--workers-max` | `workers_max` |
| Target tracking `TargetValue` | `scaling.type` + `requestCount` or `queueDelay` | `--scale-by`, `--scale-threshold` | `scaling_type`, `scaling_value` |
| Scale-in cooldown | `workers.idleTimeout` | `--idle-timeout` | `idle_timeout` |
| Endpoint kind (real-time vs async) | `type`: `LOAD_BALANCER` or `QUEUE` | set through REST v2, Terraform, or console | `endpoint_type` |
| `ModelDataUrl` | image content, `mounts.network`, cached model | `--network-volume-id`, `--model-reference` | `network_volumes` |
| `ExecutionRoleArn`, instance profile | secrets in `env` | `--env` | `env` |
| ECR image | ECR delegation; leave `registry` unset | leave `--registry-auth-id` unset | `runpod_registry_delegation` |
| NVIDIA driver / CUDA from AMI | `gpu.minCudaVersion` | `--min-cuda-version` | `min_cuda_version` |

`runpodctl serverless create` creates queue endpoints. Create load balancing endpoints with `POST /v2/serverless` (`"type": "LOAD_BALANCER"`, scaler `REQUEST_COUNT`), the MCP `create-endpoint` tool, or Terraform. A queue endpoint that scales on `REQUEST_COUNT` takes no `workers.idleTimeout`. Check `runpodctl serverless create --help` and `runpodctl pod create --help` for exact flags.

## Code translation

SageMaker `inference.py` to a queue handler. Keep `inference.py`; add:

```python
# handler.py
import json, os
import runpod
from inference import input_fn, model_fn, output_fn, predict_fn

model = model_fn(os.environ.get("MODEL_DIR", "/opt/ml/model"))

def handler(job):
    data = input_fn(json.dumps(job["input"]), "application/json")
    return json.loads(output_fn(predict_fn(data, model), "application/json"))

runpod.serverless.start({"handler": handler})
```

```dockerfile
FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04
WORKDIR /app
RUN pip install --no-cache-dir runpod
COPY model/ /opt/ml/model/
COPY inference.py handler.py /app/
CMD ["python", "-u", "/app/handler.py"]
```

`model/` is the extracted `model.tar.gz` from `ModelDataUrl`. SageMaker unpacks it at start; Runpod expects it in the image or on a volume.

SageMaker BYO container to a load balancing endpoint (no code change when the server already serves `/ping` and `/invocations` on 8080):

| Contract | SageMaker | Runpod load balancing |
| --- | --- | --- |
| Health | `GET /ping`, `200` | `GET /ping` (`HEALTH_CHECK_PATH`), `200` healthy, `204` initializing, other unhealthy |
| Port | `8080` | `PORT`, `PORT_HEALTH`, default `80` each; set both to `8080` and expose `8080/http` |
| Start | `docker run IMAGE serve` | set `cmd: ["serve"]` when the entrypoint dispatches on it |
| Request limit | 60 s response | 5.5 min processing, 30 MB payload |
| URL | SigV4 `InvokeEndpoint` | `https://ENDPOINT_ID.api.runpod.ai/invocations`, Bearer key |

```bash
curl -s -X POST https://api.runpod.io/v2/serverless \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"sm-realtime","type":"LOAD_BALANCER","image":"IMAGE","cmd":["serve"],
       "ports":["8080/http"],"env":{"PORT":"8080","PORT_HEALTH":"8080"},"disk":20,
       "gpu":{"pools":["AMPERE_24"],"count":1},"workers":{"min":0,"max":3,"idleTimeout":30},
       "scaling":{"type":"REQUEST_COUNT","requestCount":4},"timeout":600000}'
```

Read the invoke URL from `requestUrls.base` in the response. Walkthrough: [golden path 14](../../runpod/golden-paths/14-load-balancing-endpoint.md).

EC2 user data to a Pod: move package installs into the Dockerfile; keep run-time steps in a start script that ends with `exec` of the server; write persistent data under `/workspace`.

```bash
runpodctl pod create --name NAME --image IMAGE --gpu-id "NVIDIA L40S" \
  --container-disk-in-gb 50 --volume-in-gb 200 --ports "8000/http" --min-cuda-version 12.8 \
  --env '{"AWS_ACCESS_KEY_ID":"{{ RUNPOD_SECRET_aws_access_key_id }}","AWS_SECRET_ACCESS_KEY":"{{ RUNPOD_SECRET_aws_secret_access_key }}"}'
```

SageMaker training job to `@app.task`: hyperparameters become function arguments, channels under `/opt/ml/input/data` become a `NetworkVolume` mount or an S3 sync, and the model output is written to the volume or uploaded to S3 by the function. API details: [runpod-flash reference](../../runpod-flash/reference/api.md).

Terraform: add provider `runpod/runpod` `~> 2.0` next to `hashicorp/aws` in the same configuration. `aws_instance` becomes `runpod_pod`. `aws_sagemaker_model` + `aws_sagemaker_endpoint_configuration` + `aws_sagemaker_endpoint` + `aws_appautoscaling_*` become `runpod_template` (`serverless = true`) + `runpod_serverless_endpoint` (`endpoint_type`, `gpu_pools`, `scaling_type`, `scaling_value`, `workers_min`, `workers_max`). `aws_ecr_repository` stays, with `aws_ecr_repository_policy` and `runpod_registry_delegation { resource = aws_ecr_repository.NAME.arn }` (use `depends_on` on the policy). `aws_efs_file_system` and `aws_ebs_volume` become `runpod_network_volume`. Read argument names from the Terraform Registry docs for `runpod/runpod`, not from memory.

## Data

| Source | Target | Method |
| --- | --- | --- |
| S3 (stays) | read at run time | scoped IAM keys as secrets, or presigned URLs in the request |
| S3 to network volume | `/workspace` on a Pod | `aws s3 sync s3://BUCKET/PREFIX /workspace/PREFIX` inside a Pod with the volume attached |
| S3 to network volume (console) | Pod | Cloud Sync on the Pod page (access key, secret, Region, bucket path) |
| Local files to network volume | volume | `runpodctl network-volume upload VOLUME_ID LOCAL_PATH` (runpodctl v3.1.0+; check `runpodctl network-volume --help`; needs S3 API keys and a data center with the S3 API), or `aws s3 sync` with `--endpoint-url https://s3api-DC.runpod.io/` |
| EBS, EFS, FSx | network volume | copy to S3 first, or `rsync` over SSH from an instance that mounts it |
| Hugging Face weights mirrored in S3 | cached model | `--model-reference https://huggingface.co/ORG/MODEL:main` |
| `model.tar.gz` | image or volume | extract and `COPY`, or place on a volume |

- Create the network volume in the data center that has stock for the target GPU; everything that mounts it runs there.
- Mount paths: `/workspace` on Pods, `/runpod-volume` on Serverless workers.
- AWS bills data transfer out of S3 to the internet. Tell the user to budget the one-time copy and any ongoing run-time reads. Runpod has no ingress or egress fees.
- Runpod S3-compatible API: endpoint `https://s3api-DC.runpod.io/`, Region = data center ID, bucket = volume ID, separate S3 API keys. Presigned URLs, versioning, ACLs, bucket policies, and object tagging are outside its supported set.
- ECR delegation: (1) `aws ecr set-repository-policy` granting `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage` to `arn:aws:iam::550005742258:role/prod-us-east-1-deployment-role` and `arn:aws:iam::550005742258:role/prod-us-west-2-deployment-role` via an `aws:PrincipalArn` condition; (2) `POST /v2/registries/delegations` with `{"resource": "arn:aws:ecr:REGION:ACCOUNT:repository/NAME"}`; (3) deploy with the ECR image URI and no `registry` value. An ECR login token lasts 12 hours, so it is unsuitable as a stored registry credential.

## Client and API call map

| AWS call | Runpod call |
| --- | --- |
| `sagemaker-runtime.invoke_endpoint(EndpointName, ContentType, Body)` | `runpod.Endpoint(ID).run_sync(payload)` or `POST https://api.runpod.ai/v2/ID/runsync` with `{"input": payload}`; result under `output` |
| same, BYO container | `POST https://ID.api.runpod.ai/invocations`, same body, `Authorization: Bearer KEY` |
| `invoke_endpoint_async(InputLocation=s3://...)` | `POST https://api.runpod.ai/v2/ID/run` with `{"input": {...}, "webhook": URL}`; poll `/status/JOB_ID` |
| `invoke_endpoint_with_response_stream` | `GET https://api.runpod.ai/v2/ID/stream/JOB_ID`, or streaming response from a load balancing worker |
| `bedrock-runtime.converse(modelId, messages, system, inferenceConfig)` | OpenAI SDK, `base_url=https://api.runpod.ai/v2/ID/openai/v1`, `chat.completions.create(model, messages, max_tokens, temperature, top_p, stop)` |
| `response["output"]["message"]["content"][0]["text"]` | `response.choices[0].message.content` |
| `usage.inputTokens`, `usage.outputTokens`, `stopReason` | `usage.prompt_tokens`, `usage.completion_tokens`, `finish_reason` |
| `aws ec2 run-instances` / `aws ec2 describe-instances` / `aws ec2 stop-instances` / `aws ec2 terminate-instances` | `runpodctl pod create` / `pod list`, `pod get` / `pod stop` / `pod delete` |
| `aws sagemaker create-endpoint` / `aws sagemaker describe-endpoint` / `aws sagemaker delete-endpoint` | `runpodctl serverless create` / `serverless get`, `serverless health` / `serverless delete` |
| `aws logs tail --follow` | `runpodctl pod logs POD_ID --follow`, `runpodctl serverless logs ENDPOINT_ID --follow` |
| EC2 `RunInstances`, SageMaker `CreateEndpoint` | `POST /v2/pods`, `POST /v2/serverless` |
| Secrets Manager `CreateSecret` | `POST /v2/account/secrets` |

Converse translation: `system: [{"text": T}]` becomes a `system` message; `content: [{"text": T}]` becomes a string; `inferenceConfig.maxTokens/topP/stopSequences` become `max_tokens/top_p/stop`. Payload limits: `/runsync` 20 MB, `/run` 10 MB, load balancing 30 MB. Async results are retained 30 minutes after completion.

Status map: EC2 `pending` = Pod `PROVISIONING`/`STARTING`; `running` = `RUNNING`; `stopped` = `EXITED`; `terminated` = `TERMINATED`. SageMaker `InService` = workers `IDLE`/`RUNNING`; `Creating`/`Updating` = workers `INITIALIZING`. Jobs: `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`.

## Gaps: stop and ask the user

| Gap | Options |
| --- | --- |
| Workload reaches VPC-only resources (RDS, ElastiCache, private subnets, PrivateLink) | (a) expose through an authenticated public endpoint or API gateway; (b) keep that workload on AWS; (c) move the dependency |
| IAM role or instance profile grants broad access | (a) create a scoped IAM user and store keys as Runpod secrets; (b) presigned URLs per request; (c) keep on AWS |
| KMS customer-managed keys or data that must stay encrypted under AWS control | (a) keep data in S3 and read at run time; (b) client-side encryption; (c) keep on AWS |
| Multi-model endpoint, multiple production variants, shadow traffic | (a) one endpoint per model; (b) router inside one load balancing worker; (c) keep on AWS |
| Bedrock model with no open weights, or Guardrails, Knowledge Bases, Agents | (a) keep on Bedrock; (b) pick an open-weight replacement and re-evaluate quality |
| Spot or Capacity Block based cost model | (a) on-demand Pods (`runpodctl`, REST v2, and Terraform create on-demand Pods); (b) Serverless with scale to zero; (c) contact Runpod sales for committed capacity |
| Requests longer than the load balancing limit, or bursts that must never drop | use a queue endpoint |
| Arm images (`g5g`, `p6e-gb200`) | rebuild for `linux/amd64` and retest |
| EKS-specific features (operators, service mesh, node groups) | (a) Serverless endpoints per service; (b) SkyPilot or dstack onto Pods; (c) keep on EKS |
| Slurm cluster with FSx for Lustre and custom AMIs | Instant Cluster with a network volume; confirm stock for the node count before promising a date |
| Compliance scope (HIPAA, SOC 2, region lock) | Secure Cloud with `--compliance` and `--country-code`; confirm with the user's compliance owner |
| Savings Plans or reservations still in term | choose the cutover date with the user |

Before creating billable resources: show the plan, the GPU types, and a cost estimate, and wait for approval.

## Verify

1. Pod: `runpodctl pod get POD_ID` until `runtimeStatus` is `running`; request the proxy URL from outside; `runpodctl pod logs POD_ID`.
2. Queue endpoint: `runpodctl serverless run ENDPOINT_ID --input '{...}'`; compare `output` with the SageMaker response for the same input.
3. Load balancing endpoint: `GET https://ENDPOINT_ID.api.runpod.ai/ping` returns `200` (retry through the cold start), then `POST /invocations`.
4. LLM: one `chat.completions.create` call; compare text and token counts with the Bedrock response.
5. Measure warm latency and cold start from zero workers; decide on `workers.min`.
6. Confirm AWS callbacks work from Runpod: S3 read and write with the scoped keys.
7. Run both systems in parallel on real traffic before shifting.

Common failures: `502` for about 8 minutes then worker recycle (set `PORT` and `PORT_HEALTH` to the server port); container exits at start (missing `serve` argument); `NoCredentialsError` (no instance role, add secrets); `exec format error` (arm64 image); requests to `169.254.169.254` hang (metadata service is EC2 only); ECR pull failure (policy or delegation missing).

## Shut down AWS

Run only after explicit user approval, resource by resource. List first, then delete.

```bash
# SageMaker
aws application-autoscaling deregister-scalable-target --service-namespace sagemaker \
  --resource-id endpoint/ENDPOINT_NAME/variant/VARIANT_NAME \
  --scalable-dimension sagemaker:variant:DesiredInstanceCount
aws sagemaker delete-endpoint --endpoint-name ENDPOINT_NAME
aws sagemaker delete-endpoint-config --endpoint-config-name CONFIG_NAME
aws sagemaker delete-model --model-name MODEL_NAME
aws sagemaker stop-notebook-instance --notebook-instance-name NAME
aws sagemaker delete-notebook-instance --notebook-instance-name NAME
aws bedrock delete-provisioned-model-throughput --provisioned-model-id ARN

# EC2 and leftovers
aws ec2 terminate-instances --instance-ids INSTANCE_ID
aws ec2 describe-volumes --filters Name=status,Values=available
aws ec2 describe-snapshots --owner-ids self
aws ec2 describe-addresses
aws ec2 describe-nat-gateways
aws ec2 delete-volume --volume-id VOLUME_ID
aws ec2 delete-snapshot --snapshot-id SNAPSHOT_ID
aws ec2 release-address --allocation-id ALLOCATION_ID
aws ec2 delete-nat-gateway --nat-gateway-id NAT_ID

# Images and logs
aws ecr delete-repository --repository-name NAME --force
aws logs describe-log-groups --log-group-name-prefix /aws/sagemaker/
aws logs delete-log-group --log-group-name LOG_GROUP
```

Checklist: endpoint configs and models (not removed by `delete-endpoint`), notebook instances and Studio apps, Auto Scaling groups (scale to 0 before terminating instances), `available` EBS volumes, snapshots and AMIs, unassociated Elastic IPs, NAT gateways, ECR repositories (keep when Runpod still pulls from them), EFS and FSx file systems, CloudWatch log groups and alarms, Capacity Reservations. In Terraform, remove the AWS blocks in a separate apply after traffic has moved.
