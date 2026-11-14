#!/usr/bin/env python3
"""Inventory which cloud and GPU platforms a codebase depends on.

Step 1 of the runpod-cloud-migrate skill: before planning a move to Runpod, count what
the repository actually uses. The scanner walks a directory, matches each text file
against a table of platform signals (SDK imports, CLI invocations, API hostnames,
config files, Terraform resource types, credential and runtime env var names), and
reports the hits grouped by platform and by kind.

It reads files only. It never calls a network, never reads credentials and never edits
anything. Standard library only, Python 3.9+.

    python3 scan_cloud_usage.py [path]              # Markdown summary
    python3 scan_cloud_usage.py [path] --json       # full hit list as JSON
    python3 scan_cloud_usage.py [path] --platform modal --platform aws
    python3 scan_cloud_usage.py --list              # the platforms and their references

A hit is evidence, not a verdict: read the file before deciding what it means. The
`reference` field of each platform names the playbook to open next.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from typing import Dict, Iterable, Iterator, List, NamedTuple, Optional, Pattern, Sequence, Tuple

# Kinds, in the order the summary prints them.
KINDS = ("sdk", "cli", "api", "config", "iac", "runtime", "credential")

KIND_HELP = {
    "sdk": "code that imports or calls the platform's SDK",
    "cli": "shell, CI or Makefile lines that run the platform's CLI",
    "api": "hostnames or URLs of the platform's API or of workloads it serves",
    "config": "the platform's own project or deploy config",
    "iac": "Terraform or Kubernetes definitions of resources on the platform",
    "runtime": "container-side contract: env vars or paths the platform injects",
    "credential": "names of the platform's credentials (the name only, never a value)",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "site-packages",
    "dist",
    "build",
    "target",
    "vendor",
    ".terraform",
    ".next",
    ".nuxt",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".claude",
    ".cursor",
    ".agents",
    ".codex",
}

SKIP_SUFFIXES = (
    ".lock",
    ".min.js",
    ".min.css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".whl",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".pt",
    ".pth",
    ".ckpt",
    ".safetensors",
    ".onnx",
    ".gguf",
    ".parquet",
    ".arrow",
    ".npy",
    ".npz",
    ".pkl",
    ".mp3",
    ".mp4",
    ".wav",
    ".mov",
    ".tfstate",
    ".backup",
)

SKIP_FILES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
}

MAX_BYTES = 1_000_000
MAX_LINE = 2_000

CODE = ("*.py", "*.pyi", "*.ipynb", "*.js", "*.jsx", "*.mjs", "*.cjs", "*.ts", "*.tsx", "*.go", "*.rs", "*.rb", "*.java", "*.kt")
PY = ("*.py", "*.pyi", "*.ipynb")
JS = ("*.js", "*.jsx", "*.mjs", "*.cjs", "*.ts", "*.tsx")
SHELL = (
    "*.sh",
    "*.bash",
    "*.zsh",
    "*.fish",
    "*.ps1",
    "Makefile",
    "makefile",
    "*.mk",
    "justfile",
    "Justfile",
    "Dockerfile",
    "Dockerfile.*",
    "*.dockerfile",
    "*.yml",
    "*.yaml",
    "*.md",
    "*.mdx",
    "*.txt",
    "*.toml",
    "Procfile",
    "*.py",
    "*.ipynb",
)
TF = ("*.tf", "*.tf.json", "*.hcl", "*.tfvars")
K8S = ("*.yml", "*.yaml", "*.json", "*.tpl")
DEPS = ("requirements*.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "package.json", "environment.yml", "environment.yaml")
ANY = ("*",)


class Signal(NamedTuple):
    kind: str
    pattern: Pattern[str]
    globs: Tuple[str, ...]
    meaning: str


class Platform(NamedTuple):
    slug: str
    name: str
    reference: Optional[str]
    signals: Tuple[Signal, ...]


def sig(kind: str, pattern: str, globs: Sequence[str], meaning: str, flags: int = 0) -> Signal:
    assert kind in KINDS, kind
    return Signal(kind, re.compile(pattern, flags), tuple(globs), meaning)


def filename(pattern: str, meaning: str, kind: str = "config") -> Signal:
    """A signal that fires on the file's name alone (first line carries the hit)."""
    return Signal(kind, re.compile(r"(?s)\A"), (pattern,), meaning)


PLATFORMS: Tuple[Platform, ...] = (
    Platform(
        "vast-ai",
        "Vast.ai",
        "reference/vast-ai.md",
        (
            sig("sdk", r"^\s*(?:from\s+vastai(?:_sdk)?\b|import\s+vastai(?:_sdk)?\b)", PY, "vastai Python SDK"),
            sig("sdk", r"\bVastAI\s*\(", PY, "vastai SDK client"),
            sig("cli", r"(?<![\w./-])vastai\s+(?:search|create|show|destroy|stop|start|reboot|label|logs|copy|cloud|execute|ssh-url|scp-url|set|update|change|attach|detach|prepay|recycle)\b", SHELL, "vastai CLI"),
            sig("api", r"\b(?:console|cloud)\.vast\.ai\b", ANY, "Vast.ai API host"),
            sig("api", r"\brun\.vast\.ai\b", ANY, "Vast.ai Serverless route"),
            sig("api", r"\bopenai\.vast\.ai\b", ANY, "Vast.ai OpenAI-compatible route"),
            sig("config", r"\bvastai/(?:base-image|pytorch|kvm)\b", ANY, "Vast.ai base image"),
            sig("runtime", r"\b(?:VAST_CONTAINERLABEL|VAST_TCP_PORT_\d+|VAST_UDP_PORT_\d+|CONTAINER_API_KEY)\b", ANY, "env var Vast.ai sets in an instance"),
            sig("credential", r"\bVAST_API_KEY\b", ANY, "Vast.ai API key name"),
            sig("config", r"\b(?:vastai|vastai-sdk|vast-pyworker)\b", DEPS, "Vast.ai package dependency"),
        ),
    ),
    Platform(
        "lambda",
        "Lambda",
        "reference/lambda.md",
        (
            sig("api", r"\bcloud\.lambda(?:labs)?\.(?:com|ai)/api/v1\b", ANY, "Lambda Cloud API"),
            sig("api", r"\bapi\.lambda(?:labs)?\.(?:com|ai)\b", ANY, "Lambda inference API host"),
            sig("api", r"\bfiles\.[a-z0-9-]+\.lambda\.com\b", ANY, "Lambda Filesystem S3 Adapter endpoint"),
            sig("runtime", r"/lambda/nfs/", ANY, "Lambda filesystem mount path"),
            sig("config", r"\b(?:lambda-stack(?:-legacy)?|gpu-base)-2[24]-04\b", ANY, "Lambda image family"),
            sig("config", r"\bgpu_\d+x_[a-z0-9]+(?:_[a-z0-9]+)*\b", ANY, "Lambda instance type name"),
            sig("credential", r"\bLAMBDA(?:_CLOUD|_LABS)?_API_KEY\b", ANY, "Lambda API key name"),
            sig("iac", r"\blambdalabs_[a-z_]+\b", TF, "Lambda Terraform resource"),
        ),
    ),
    Platform(
        "coreweave",
        "CoreWeave",
        "reference/coreweave.md",
        (
            sig("api", r"\b[\w.-]*\.coreweave\.(?:com|cloud)\b", ANY, "CoreWeave host"),
            sig("api", r"\bcwobject\.com\b|\bcwlota\.com\b", ANY, "CoreWeave AI Object Storage endpoint"),
            sig("api", r"\bcwinference\.com\b", ANY, "CoreWeave inference endpoint"),
            sig("cli", r"(?<![\w./-])cwic\s+\w+", SHELL, "cwic CLI"),
            sig("iac", r"\bstorageClassName:\s*shared-vast\b", K8S, "CoreWeave Distributed File Storage class"),
            sig("iac", r"\bcoreweave_[a-z_]+\b", TF, "CoreWeave Terraform resource"),
            sig("iac", r"\b(?:node\.coreweave\.cloud|gpu\.nvidia\.com)/[\w.-]+", K8S, "CoreWeave node selector or label"),
            sig("iac", r"\b(?:compute|sunk|storage)\.coreweave\.com/", K8S, "CoreWeave Kubernetes API group"),
            sig("credential", r"\bCOREWEAVE_(?:API_)?TOKEN\b|\bCW_TOKEN\b", ANY, "CoreWeave token name"),
        ),
    ),
    Platform(
        "paperspace",
        "Paperspace and DigitalOcean GPU",
        "reference/paperspace.md",
        (
            sig("sdk", r"^\s*(?:from\s+gradient\b|import\s+gradient\b|from\s+paperspace\b|import\s+paperspace\b)", PY, "Gradient or Paperspace Python SDK"),
            sig("cli", r"(?<![\w./-])gradient\s+(?:deployments|notebooks|workflows|datasets|models|machines|projects|secrets|storageProviders|apiKey)\b", SHELL, "gradient CLI"),
            sig("cli", r"(?<![\w./-])pspace\s+\w+", SHELL, "pspace CLI"),
            sig("cli", r"(?<![\w./-])doctl\s+(?:compute|kubernetes|gradient|genai|serverless)\b", SHELL, "doctl CLI"),
            sig("api", r"\bapi\.paperspace\.(?:com|io)\b|\b[\w-]+\.paperspacegradient\.com\b", ANY, "Paperspace API or deployment host"),
            sig("api", r"\binference\.do-ai\.run\b|\b[\w-]+\.agents\.do-ai\.run\b", ANY, "DigitalOcean inference host"),
            sig("api", r"\b[\w.-]+\.digitaloceanspaces\.com\b", ANY, "DigitalOcean Spaces bucket"),
            sig("config", r"\bpaperspace/gradient-base\b", ANY, "Paperspace Gradient base image"),
            sig("iac", r"\bdigitalocean_(?:droplet|volume|spaces_bucket|kubernetes_cluster|kubernetes_node_pool|genai_\w+|gradientai_\w+)\b", TF, "DigitalOcean Terraform resource"),
            sig("config", r"\bgpu-(?:h100|h200|l40s|4000adax|6000adax|mi300x|mi325x)[\w-]*\b", ANY, "DigitalOcean GPU Droplet size"),
            sig("credential", r"\bPAPERSPACE_API_KEY\b|\bDIGITALOCEAN_(?:ACCESS_)?TOKEN\b|\bGRADIENT_MODEL_ACCESS_KEY\b", ANY, "Paperspace or DigitalOcean credential name"),
        ),
    ),
    Platform(
        "modal",
        "Modal",
        "reference/modal.md",
        (
            sig("sdk", r"^\s*(?:import\s+modal\b|from\s+modal(?:\.\w+)*\s+import\b)", PY, "Modal SDK import"),
            sig("sdk", r"\bmodal\.(?:App|Stub|Image|Volume|NetworkFileSystem|Secret|Cls|Function|Dict|Queue|Sandbox|Cron|Period|CloudBucketMount)\b", PY, "Modal primitive"),
            sig("sdk", r"@(?:\w+\.)?(?:function|cls)\s*\([^)]*\bgpu\s*=", PY, "Modal GPU function or class"),
            sig("sdk", r"@modal\.(?:enter|exit|method|fastapi_endpoint|web_endpoint|asgi_app|wsgi_app|web_server|concurrent|batched)\b", PY, "Modal lifecycle or web decorator"),
            sig("cli", r"(?<![\w./-])modal\s+(?:run|deploy|serve|shell|app|volume|secret|token|setup|launch|container|environment)\b", SHELL, "modal CLI"),
            sig("api", r"\b[\w-]+\.modal\.run\b", ANY, "Modal web endpoint URL"),
            sig("credential", r"\bMODAL_TOKEN_(?:ID|SECRET)\b", ANY, "Modal token name"),
            sig("config", r"^\s*\"?modal\"?\s*(?:[=<>~!\[]|$|\")", DEPS, "Modal package dependency"),
        ),
    ),
    Platform(
        "replicate",
        "Replicate",
        "reference/replicate.md",
        (
            sig("sdk", r"^\s*(?:import\s+replicate\b|from\s+replicate\b)", PY, "replicate Python client"),
            sig("sdk", r"""(?:from|require\()\s*['"]replicate['"]""", JS, "replicate JavaScript client"),
            sig("sdk", r"\breplicate\.(?:run|stream|predictions|deployments|models|trainings)\b", CODE, "Replicate client call"),
            sig("sdk", r"^\s*from\s+cog\s+import\b", PY, "Cog predictor"),
            filename("cog.yaml", "Cog model definition"),
            sig("cli", r"(?<![\w./-])cog\s+(?:build|push|predict|run|train|login|init)\b", SHELL, "cog CLI"),
            sig("api", r"\bapi\.replicate\.com\b", ANY, "Replicate API host"),
            sig("api", r"\br8\.im/", ANY, "Replicate image registry"),
            sig("api", r"\breplicate\.delivery\b", ANY, "Replicate output file host"),
            sig("credential", r"\bREPLICATE_API_(?:TOKEN|KEY)\b", ANY, "Replicate token name"),
        ),
    ),
    Platform(
        "baseten",
        "Baseten",
        "reference/baseten.md",
        (
            sig("sdk", r"^\s*(?:import\s+truss(?:_chains)?\b|from\s+truss(?:_chains)?\b|import\s+baseten\b|from\s+baseten\b)", PY, "Truss or Baseten SDK"),
            sig("cli", r"(?<![\w./-])truss\s+(?:push|init|predict|watch|login|chains|train|image|run-python|cleanup)\b", SHELL, "truss CLI"),
            sig("cli", r"(?<![\w./-])baseten\s+(?:model|truss|train|loops|chains|login)\b", SHELL, "baseten CLI"),
            sig("iac", r"\bbaseten_[a-z_]+\b|\bbasetenlabs/baseten\b", TF, "Baseten Terraform resource"),
            sig("runtime", r"\bBT_(?:MODEL_ID|MODEL_DEPLOYMENT_ID)\b", ANY, "env var Baseten sets in a deployment"),
            sig("api", r"\b(?:model|chain)-[\w-]+\.api\.baseten\.co\b|\b(?:api|app|inference)\.baseten\.co\b", ANY, "Baseten API or model host"),
            sig("config", r"^\s*(?:model_name|model_class_name|model_class_filename|model_framework|predict_concurrency)\s*:", ("config.yaml", "config.yml"), "Truss config.yaml"),
            sig("config", r"^\s*(?:accelerator|use_gpu)\s*:", ("config.yaml", "config.yml"), "Truss resources block"),
            sig("credential", r"\bBASETEN_API_KEY\b", ANY, "Baseten API key name"),
        ),
    ),
    Platform(
        "together-ai",
        "Together AI",
        "reference/together-ai.md",
        (
            sig("sdk", r"^\s*(?:import\s+together\b|from\s+together\b)", PY, "together Python SDK"),
            sig("sdk", r"""(?:from|require\()\s*['"]together-ai['"]""", JS, "together-ai JavaScript SDK"),
            sig("sdk", r"\b(?:Together|AsyncTogether)\s*\(", CODE, "Together client"),
            sig("sdk", r"""['"]@ai-sdk/togetherai['"]|\blangchain_together\b|\bllama_index\.llms\.together\b""", ANY, "Together integration package"),
            sig("api", r"\bapi\.together\.(?:xyz|ai)\b", ANY, "Together API host"),
            sig("api", r"\b(?:api-inference|us-api)\.together\.ai\b", ANY, "Together dedicated or regional API host"),
            sig("cli", r"(?<![\w./-])tg\s+(?:endpoints|batches|fine-tuning|ft|clusters|beta|models|files)\b", SHELL, "tg CLI"),
            sig("sdk", r"^\s*import\s+sprocket\b|\bsprocket\.Sprocket\b", PY, "Together Sprocket worker"),
            sig("credential", r"\bTOGETHER(?:_AI)?_API_KEY\b", ANY, "Together API key name"),
        ),
    ),
    Platform(
        "fireworks-ai",
        "Fireworks AI",
        "reference/fireworks-ai.md",
        (
            sig("sdk", r"^\s*(?:import\s+fireworks\b|from\s+fireworks\b)", PY, "fireworks-ai Python SDK"),
            sig("sdk", r"\b(?:Async)?Fireworks\s*\(", CODE, "Fireworks client"),
            sig("sdk", r"""['"]@ai-sdk/fireworks['"]|\blangchain_fireworks\b|\bllama_index\.llms\.fireworks\b|['"]@fireworks-ai/[\w-]+['"]""", ANY, "Fireworks integration package"),
            sig("cli", r"(?<![\w./-])firectl\s+\w+", SHELL, "firectl CLI"),
            sig("api", r"\bapi\.fireworks\.ai\b", ANY, "Fireworks API host"),
            sig("config", r"\baccounts/[\w-]+/(?:models|deployments|deployedModels)/[\w.-]+", ANY, "Fireworks model or deployment ID"),
            sig("credential", r"\bFIREWORKS(?:_AI)?_API_KEY\b", ANY, "Fireworks API key name"),
        ),
    ),
    Platform(
        "fal",
        "fal",
        "reference/fal.md",
        (
            sig("sdk", r"^\s*(?:import\s+fal(?:_client)?\b|from\s+fal(?:_client)?(?:\.\w+)*\s+import\b)", PY, "fal Python SDK or client"),
            sig("sdk", r"""['"]@fal-ai/(?:client|serverless-client|server-proxy)[\w/-]*['"]|['"]@ai-sdk/fal['"]""", ANY, "fal JavaScript client"),
            sig("sdk", r"\bfal(?:_client)?\.(?:subscribe|submit|run|stream|queue|storage|upload_file|realtime)\b", CODE, "fal client call"),
            sig("sdk", r"\bclass\s+\w+\(\s*fal\.App\b|@fal\.(?:endpoint|function|realtime)\b", PY, "fal Serverless app"),
            sig("cli", r"(?<![\w./-])fal\s+(?:deploy|run|auth|apps|secrets|keys|runners|profile|create)\b", SHELL, "fal CLI"),
            sig("api", r"\b(?:queue\.|ws\.|rest\.alpha\.)?fal\.run\b|\bapi\.fal\.ai\b", ANY, "fal API host"),
            sig("api", r"\b(?:v\d\.)?fal\.media\b", ANY, "fal output file host"),
            sig("config", r"\[tool\.fal\.apps\.", ("pyproject.toml",), "fal app definition"),
            sig("credential", r"\bFAL_(?:API_)?KEY(?:_ID|_SECRET)?\b", ANY, "fal key name"),
        ),
    ),
    Platform(
        "hugging-face",
        "Hugging Face Inference Endpoints",
        "reference/hugging-face.md",
        (
            sig("api", r"\b[\w.-]+\.endpoints\.huggingface\.cloud\b", ANY, "Inference Endpoint URL"),
            sig("api", r"\bapi\.endpoints\.huggingface\.cloud\b", ANY, "Inference Endpoints management API"),
            sig("api", r"\brouter\.huggingface\.co\b|\bapi-inference\.huggingface\.co\b", ANY, "Hugging Face Inference Providers route"),
            sig("sdk", r"\b(?:create_inference_endpoint|create_inference_endpoint_from_catalog|get_inference_endpoint|list_inference_endpoints|update_inference_endpoint|delete_inference_endpoint|pause_inference_endpoint|resume_inference_endpoint|scale_to_zero_inference_endpoint)\b", CODE, "huggingface_hub endpoint management"),
            sig("sdk", r"\b(?:Async)?InferenceClient\s*\(", CODE, "huggingface_hub InferenceClient"),
            sig("runtime", r"^\s*class\s+EndpointHandler\b", PY, "Inference Endpoints custom handler"),
            sig("cli", r"(?<![\w./-])hf\s+(?:endpoints|jobs)\b|(?<![\w./-])huggingface-cli\s+endpoints?\b", SHELL, "hf endpoints or jobs CLI"),
            sig("sdk", r"^\s*import\s+spaces\b|@spaces\.GPU\b", PY, "Spaces ZeroGPU decorator"),
            sig("config", r"\bghcr\.io/huggingface/text-(?:generation|embeddings)-inference\b", ANY, "TGI or TEI container image"),
            sig("api", r"\b[\w-]+\.hf\.space\b", ANY, "Hugging Face Space URL"),
        ),
    ),
    Platform(
        "aws",
        "AWS",
        "reference/aws.md",
        (
            sig("sdk", r"^\s*(?:import\s+sagemaker\b|from\s+sagemaker\b)", PY, "SageMaker Python SDK"),
            sig("sdk", r"""\.client\(\s*['"](?:sagemaker|sagemaker-runtime|bedrock|bedrock-runtime|bedrock-agent-runtime|batch)['"]""", PY, "boto3 client for SageMaker, Bedrock or Batch"),
            sig("sdk", r"""['"]@aws-sdk/client-(?:sagemaker|sagemaker-runtime|bedrock|bedrock-runtime|batch)['"]""", ANY, "AWS SDK for JavaScript client"),
            sig("sdk", r"\b(?:invoke_endpoint|invoke_endpoint_async|invoke_endpoint_with_response_stream|invoke_model|invoke_model_with_response_stream|converse_stream|create_training_job|create_transform_job|create_processing_job)\s*\(", PY, "SageMaker or Bedrock call"),
            sig("sdk", r"\bChatBedrock(?:Converse)?\b|\blangchain_aws\b|['\"]@ai-sdk/amazon-bedrock['\"]", ANY, "Bedrock integration package"),
            sig("cli", r"(?<![\w./-])aws\s+(?:sagemaker|sagemaker-runtime|bedrock|bedrock-runtime|batch)\s+[\w-]+", SHELL, "AWS CLI for SageMaker, Bedrock or Batch"),
            sig("cli", r"(?<![\w./-])aws\s+ec2\s+(?:run-instances|request-spot-instances|create-launch-template|create-fleet|purchase-capacity-block)\b", SHELL, "AWS CLI launching EC2 capacity"),
            sig("config", r"\b(?:ml\.)?(?:p[2-6][a-z]{0,3}|g[3-6][a-z]{0,3}|gr6)\.(?:\d{0,2}x?large|metal(?:-\d+xl)?)\b", ANY, "EC2 or SageMaker GPU instance type"),
            sig("api", r"\bruntime\.sagemaker\.[\w-]+\.amazonaws\.com\b|\bbedrock(?:-runtime)?\.[\w-]+\.amazonaws\.com\b", ANY, "SageMaker or Bedrock runtime host"),
            sig("api", r"\b\d{12}\.dkr\.ecr\.[\w-]+\.amazonaws\.com\b", ANY, "Amazon ECR image"),
            sig("iac", r"\baws_(?:sagemaker_[a-z_]+|bedrock[a-z_]*|batch_[a-z_]+|appautoscaling_[a-z_]+|eks_node_group)\b", TF, "AWS Terraform resource for ML or batch"),
            sig("iac", r"\bAWS::(?:SageMaker|Bedrock|Batch)::\w+", ANY, "CloudFormation resource for ML or batch"),
            sig("runtime", r"/opt/ml/(?:model|input|output|code|checkpoints|processing)\b|\bSM_(?:MODEL_DIR|CHANNEL_\w+|OUTPUT_DATA_DIR|NUM_GPUS|HPS)\b|\bSAGEMAKER_(?:PROGRAM|SUBMIT_DIRECTORY|REGION)\b", ANY, "SageMaker container contract"),
            sig("runtime", r"\b(?:model_fn|input_fn|predict_fn|output_fn|transform_fn)\s*\(", PY, "SageMaker inference handler functions"),
        ),
    ),
    Platform(
        "google-cloud",
        "Google Cloud",
        "reference/google-cloud.md",
        (
            sig("sdk", r"^\s*(?:from\s+google\.cloud\s+import\s+[\w, ]*\baiplatform\w*|import\s+google\.cloud\.aiplatform\w*|from\s+google\.cloud\.aiplatform\w*|import\s+vertexai\b|from\s+vertexai\b)", PY, "Vertex AI SDK"),
            sig("sdk", r"""['"]@google-cloud/(?:aiplatform|vertexai|run|batch)['"]|['"]@ai-sdk/google-vertex['"]|\blangchain_google_vertexai\b""", ANY, "Google Cloud AI client package"),
            sig("sdk", r"\baiplatform\.(?:init|Endpoint|Model|CustomJob|CustomContainerTrainingJob|CustomTrainingJob|BatchPredictionJob|PipelineJob)\b", PY, "Vertex AI resource call"),
            sig("cli", r"(?<![\w./-])gcloud\s+(?:beta\s+|alpha\s+)?(?:ai|ai-platform|batch)\s+[\w-]+", SHELL, "gcloud for Vertex AI or Batch"),
            sig("cli", r"(?<![\w./-])gcloud\s+(?:beta\s+|alpha\s+)?run\s+(?:deploy|services|jobs)\b.*--gpu\b", SHELL, "gcloud run with a GPU"),
            sig("cli", r"(?<![\w./-])gcloud\s+(?:beta\s+|alpha\s+)?compute\s+instances\s+create\b.*(?:--accelerator\b|--machine-type[= ]+(?:a[234]|g[24])-)", SHELL, "gcloud creating a GPU VM"),
            sig("config", r"\bnvidia-(?:tesla-(?:t4|p4|p100|v100|a100)|l4|a100-80gb|h100-80gb|h100-mega-80gb|h200-141gb|b200|gb200|rtx-pro-6000)\b", ANY, "Compute Engine GPU accelerator type"),
            sig("config", r"\b(?:a2-(?:highgpu|megagpu|ultragpu)|a3-(?:highgpu|megagpu|edgegpu|ultragpu)|a4x?-highgpu|g2-standard|g4-standard)-\d+g?\b", ANY, "Compute Engine GPU machine type"),
            sig("api", r"\b[\w-]*aiplatform\.googleapis\.com\b|\b[\w.-]+\.prediction\.vertexai\.goog\b", ANY, "Vertex AI API host"),
            sig("api", r"\b[\w-]+-docker\.pkg\.dev\b|\b(?:[a-z]+\.)?gcr\.io/", ANY, "Artifact Registry or Container Registry image"),
            sig("iac", r"\bgoogle_(?:vertex_ai_[a-z_]+|cloud_run_v2_(?:service|job)|cloud_run_service|container_node_pool|workbench_instance|notebooks_instance|batch_[a-z_]+)\b", TF, "Google Cloud Terraform resource for ML or serving"),
            sig("iac", r"\bguest_accelerator\b|\bgpu_type\s*=|\bnvidia\.com/gpu\b.*run\.googleapis\.com", TF + K8S, "GPU attachment in Terraform or a Cloud Run manifest"),
            sig("runtime", r"\bAIP_(?:HEALTH_ROUTE|PREDICT_ROUTE|HTTP_PORT|STORAGE_URI|MODEL_DIR|CHECKPOINT_DIR|TENSORBOARD_LOG_DIR|ENDPOINT_ID|DEPLOYED_MODEL_ID)\b", ANY, "Vertex AI container contract"),
            sig("runtime", r"\bmetadata\.google\.internal\b|\bCLOUD_RUN_TASK_(?:INDEX|COUNT)\b", ANY, "Google Cloud metadata server or Cloud Run job contract"),
        ),
    ),
    Platform(
        "azure",
        "Azure",
        "reference/azure.md",
        (
            sig("sdk", r"^\s*(?:from\s+azure\.ai\.(?:ml|inference|projects)\b|import\s+azure\.ai\.(?:ml|inference|projects)\b|from\s+azureml\b|import\s+azureml\b)", PY, "Azure Machine Learning or AI SDK"),
            sig("sdk", r"\b(?:Async)?AzureOpenAI\s*\(|\bAzureChatOpenAI\b|\bAzureOpenAIEmbeddings\b|['\"]@ai-sdk/azure['\"]|['\"]@azure/openai['\"]", ANY, "Azure OpenAI client"),
            sig("sdk", r"\b(?:ManagedOnlineEndpoint|ManagedOnlineDeployment|KubernetesOnlineEndpoint|BatchEndpoint|AmlCompute|ComputeInstance|MLClient)\s*\(", PY, "Azure ML resource"),
            sig("cli", r"(?<![\w./-])az\s+ml\s+[\w-]+", SHELL, "az ml CLI"),
            sig("cli", r"(?<![\w./-])az\s+(?:vm|vmss)\s+create\b.*Standard_N[CDVG]", SHELL, "az creating a GPU VM"),
            sig("cli", r"(?<![\w./-])az\s+containerapp\s+[\w-]+", SHELL, "az containerapp CLI"),
            sig("cli", r"(?<![\w./-])az\s+cognitiveservices\s+[\w-]+", SHELL, "az cognitiveservices CLI"),
            sig("config", r"\bStandard_N[CDVG]\w*\b", ANY, "Azure GPU VM size"),
            sig("config", r"\$schema:\s*https://azuremlschemas\.azureedge\.net/", ("*.yml", "*.yaml"), "Azure ML YAML definition"),
            sig("api", r"\b[\w.-]+\.inference\.ml\.azure\.com\b|\b[\w-]+\.openai\.azure\.com\b|\b[\w-]+\.(?:services|cognitiveservices)\.ai\.azure\.com\b|\b[\w-]+\.cognitiveservices\.azure\.com\b", ANY, "Azure ML or Azure OpenAI endpoint host"),
            sig("api", r"\b[\w-]+\.azurecr\.io\b", ANY, "Azure Container Registry image"),
            sig("api", r"\b[\w.-]+\.azurecontainerapps\.io\b", ANY, "Azure Container Apps host"),
            sig("iac", r"\bazurerm_(?:machine_learning_[a-z_]+|cognitive_[a-z_]+|ai_[a-z_]+|container_app(?:_environment|_job)?|kubernetes_cluster_node_pool)\b", TF, "Azure Terraform resource for ML or serving"),
            sig("iac", r"\bMicrosoft\.(?:MachineLearningServices|CognitiveServices)/[\w/]+", ANY, "ARM, Bicep or azapi resource type"),
            sig("runtime", r"\bAZUREML_(?:MODEL_DIR|ENTRY_SCRIPT|ARM_\w+|RUN_ID)\b", ANY, "Azure ML container contract"),
            sig("credential", r"\bAZURE_OPENAI_(?:API_KEY|ENDPOINT|API_VERSION|DEPLOYMENT\w*)\b", ANY, "Azure OpenAI setting name"),
        ),
    ),
    # Cross-platform signals. They carry no playbook of their own: they say what shape
    # the workload has, which decides the Runpod target.
    Platform(
        "kubernetes",
        "Kubernetes GPU workloads (any cloud)",
        "reference/coreweave.md",
        (
            sig("iac", r"\bnvidia\.com/gpu\s*:", K8S, "GPU resource request in a Kubernetes manifest"),
            sig("iac", r"\bkind:\s*(?:InferenceService|RayCluster|RayJob|RayService|PyTorchJob|TFJob|MPIJob|LeaderWorkerSet)\b", K8S, "ML workload custom resource"),
            sig("iac", r"\bkubernetes_(?:deployment|job|cron_job|stateful_set)(?:_v1)?\b", TF, "Kubernetes workload in Terraform"),
        ),
    ),
    Platform(
        "openai-compatible",
        "OpenAI-compatible clients (base URL swap)",
        None,
        (
            sig("sdk", r"\b(?:Async)?OpenAI\s*\([^)]*\bbase_url\s*=", PY, "OpenAI Python client with a custom base URL"),
            sig("sdk", r"\bnew\s+OpenAI\s*\(\s*\{[^}]*\bbaseURL\s*:", JS, "OpenAI JavaScript client with a custom base URL"),
            sig("credential", r"\bOPENAI_(?:BASE_URL|API_BASE)\b", ANY, "OpenAI base URL override"),
        ),
    ),
    Platform(
        "runpod",
        "Runpod (already in the repo)",
        None,
        (
            sig("sdk", r"^\s*(?:import\s+runpod\b|from\s+runpod\b)", PY, "Runpod Python SDK"),
            sig("sdk", r"\brunpod\.serverless\.start\s*\(", PY, "Runpod Serverless handler"),
            sig("cli", r"(?<![\w./-])(?:runpodctl|rp\s+flash)\s+\w+", SHELL, "runpodctl or rp flash"),
            sig("api", r"\bapi\.runpod\.(?:io|ai)\b|\bproxy\.runpod\.net\b", ANY, "Runpod API or proxy host"),
            sig("iac", r"\brunpod_(?:pod|serverless_endpoint|template|network_volume|global_volume|registry|cluster)\b", TF, "Runpod Terraform resource"),
            sig("credential", r"\bRUNPOD_API_KEY\b", ANY, "Runpod API key name"),
        ),
    ),
)

BY_SLUG: Dict[str, Platform] = {p.slug: p for p in PLATFORMS}


class Hit(NamedTuple):
    platform: str
    kind: str
    path: str
    line: int
    meaning: str
    text: str


def matches_glob(name: str, globs: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, g) for g in globs)


def iter_files(root: str) -> Iterator[str]:
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name in SKIP_FILES or name.lower().endswith(SKIP_SUFFIXES):
                continue
            yield os.path.join(dirpath, name)


def read_text(path: str) -> Optional[str]:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace")


def scan_file(path: str, rel: str, platforms: Iterable[Platform]) -> List[Hit]:
    name = os.path.basename(path)
    wanted: List[Tuple[Platform, Signal]] = [
        (p, s) for p in platforms for s in p.signals if matches_glob(name, s.globs)
    ]
    if not wanted:
        return []
    text = read_text(path)
    if text is None:
        return []
    hits: List[Hit] = []
    seen = set()
    lines = text.splitlines() or [""]
    for platform, signal in wanted:
        if signal.pattern.pattern == r"(?s)\A":
            hits.append(Hit(platform.slug, signal.kind, rel, 1, signal.meaning, name))
            continue
        for number, line in enumerate(lines, start=1):
            if len(line) > MAX_LINE:
                line = line[:MAX_LINE]
            if not signal.pattern.search(line):
                continue
            key = (platform.slug, signal.kind, number)
            if key in seen:
                continue
            seen.add(key)
            hits.append(Hit(platform.slug, signal.kind, rel, number, signal.meaning, line.strip()[:200]))
    return hits


def scan(root: str, slugs: Optional[Sequence[str]] = None) -> List[Hit]:
    platforms = [BY_SLUG[s] for s in slugs] if slugs else list(PLATFORMS)
    base = root if os.path.isdir(root) else os.path.dirname(root) or "."
    hits: List[Hit] = []
    for path in iter_files(root):
        rel = os.path.relpath(path, base)
        hits.extend(scan_file(path, rel, platforms))
    hits.sort(key=lambda h: (h.platform, KINDS.index(h.kind), h.path, h.line))
    return hits


def summarize(hits: Sequence[Hit]) -> List[dict]:
    out = []
    for platform in PLATFORMS:
        mine = [h for h in hits if h.platform == platform.slug]
        if not mine:
            continue
        kinds = {}
        for kind in KINDS:
            of_kind = [h for h in mine if h.kind == kind]
            if of_kind:
                kinds[kind] = {"hits": len(of_kind), "files": sorted({h.path for h in of_kind})}
        out.append(
            {
                "platform": platform.slug,
                "name": platform.name,
                "reference": platform.reference,
                "hits": len(mine),
                "files": sorted({h.path for h in mine}),
                "kinds": kinds,
            }
        )
    return out


def render_markdown(hits: Sequence[Hit], root: str, max_examples: int) -> str:
    summary = summarize(hits)
    lines = [f"# Cloud usage inventory: `{root}`", ""]
    if not summary:
        lines.append("No platform signals found. The repo may deploy by hand (console) or keep its")
        lines.append("infrastructure code elsewhere: ask the user what runs where before planning.")
        return "\n".join(lines) + "\n"
    lines += ["| Platform | Hits | Files | Kinds | Playbook |", "| --- | ---: | ---: | --- | --- |"]
    for row in summary:
        kinds = ", ".join(f"{k} ({v['hits']})" for k, v in row["kinds"].items())
        lines.append(
            f"| {row['name']} | {row['hits']} | {len(row['files'])} | {kinds} | {row['reference'] or 'n/a'} |"
        )
    for row in summary:
        lines += ["", f"## {row['name']}", ""]
        for kind, info in row["kinds"].items():
            lines.append(f"**{kind}**: {KIND_HELP[kind]}")
            shown = 0
            for hit in hits:
                if hit.platform != row["platform"] or hit.kind != kind:
                    continue
                if shown == max_examples:
                    lines.append(f"- ... {info['hits'] - shown} more (use `--json` for all)")
                    break
                lines.append(f"- `{hit.path}:{hit.line}` {hit.meaning}: `{hit.text.replace('`', chr(39))}`")
                shown += 1
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", nargs="?", default=".", help="directory or file to scan (default: .)")
    parser.add_argument("--json", action="store_true", help="print every hit as JSON")
    parser.add_argument("--platform", action="append", choices=sorted(BY_SLUG), help="limit to a platform (repeatable)")
    parser.add_argument("--max-examples", type=int, default=8, help="hits shown per kind in the summary (default: 8)")
    parser.add_argument("--list", action="store_true", help="list the platforms and their playbooks, then exit")
    args = parser.parse_args(argv)

    if args.list:
        for platform in PLATFORMS:
            print(f"{platform.slug}\t{platform.name}\t{platform.reference or '-'}")
        return 0
    if not os.path.exists(args.path):
        print(f"path not found: {args.path}", file=sys.stderr)
        return 2

    hits = scan(args.path, args.platform)
    if args.json:
        json.dump(
            {"root": args.path, "summary": summarize(hits), "hits": [h._asdict() for h in hits]},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(hits, args.path, args.max_examples))
    return 0


if __name__ == "__main__":
    sys.exit(main())
