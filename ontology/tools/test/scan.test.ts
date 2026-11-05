import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { compareRules, scanFiles } from "../src/scan.ts";

// Writes each file under a fresh root and returns the root.
function tree(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), "scan-"));
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(join(root, dirname(path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
  return root;
}

// Findings for a skill whose body is `text`, which lands on line 6.
function scanSkill(text: string): string[] {
  const root = tree({ "plugins/demo/SKILL.md": `---\nname: demo\n---\n# Demo\n\n${text}\n` });
  return scanFiles(root, ["plugins"]).findings.map((finding) => `${finding.file}:${finding.line} ${finding.why}`);
}

test("internal tool links, private repositories, email addresses and every key shape fail", () => {
  const cases: [string, string][] = [
    ["Tracked in https://linear.app/acme/issue/ENG-42.", "an internal tool's link"],
    ["Notes at https://acme.notion.site/page and https://acme.slack.com/archives/C1.", "an internal tool's link"],
    ["Clone https://github.com/runpod/acme-service first.", "a link to a Runpod repository that is not public"],
    ["Clone git@github.com:runpod/runpodctl-internal.git first.", "a link to a Runpod repository that is not public"],
    ["See runpod/proxy for the details.", "a private repository"],
    ["Ask jane.doe@acme.dev for access.", "an email address"],
    ["Questions go to team@runpod.io.evil.dev.", "an email address"],
    ["Write to jane@example.com.evil.dev for access.", "an email address"],
    ["Connect with `ssh x@ssh.runpod.io.evil.dev`.", "an email address"],
    ["Mail git@github.com.evil.dev for a key.", "an email address"],
    [`export RUNPOD_API_KEY=rpa_${"x".repeat(20)}`, "a Runpod API key"],
    [`AWS_SECRET_ACCESS_KEY=rps_${"x".repeat(20)}`, "a Runpod S3 API key"],
    ...["sk-", "sk_", "pk-", "pk_", "ghp_", "gho_", "phc_", "phx_", "xoxb-", "xoxp-"].map(
      (prefix): [string, string] => [`token: ${prefix}${"x".repeat(20)}`, "an API key"],
    ),
    [`GITHUB_TOKEN=github_pat_${"x".repeat(30)}`, "a GitHub token"],
    ...["ghu_", "ghs_", "ghr_"].map((prefix): [string, string] => [
      `token: ${prefix}${"x".repeat(36)}`,
      "a GitHub token",
    ]),
    [`HF_TOKEN=hf_${"x".repeat(34)}`, "a Hugging Face token"],
    [`AWS_ACCESS_KEY_ID=AKIA${"X".repeat(16)}`, "an AWS access key id"],
    [`AWS_ACCESS_KEY_ID=ASIA${"X".repeat(16)}`, "an AWS access key id"],
    [`Authorization: Bearer eyJ${"a".repeat(10)}.${"b".repeat(10)}.${"c".repeat(10)}`, "a JWT"],
  ];
  for (const [text, why] of cases) {
    assert.deepEqual(scanSkill(text), [`plugins/demo/SKILL.md:6 ${why}`], text);
  }
});

test("public links, placeholder and published addresses, SSH logins and ordinary words pass", () => {
  for (const text of [
    "See https://docs.runpod.io/pods/overview for the fields.",
    "See https://github.com/runpod/runpodctl/releases and https://github.com/runpod/runpod-python.",
    "The CLI is runpod/runpodctl and the SDK is runpod/runpod-python.",
    "Run `git config user.email your_email@example.com` first.",
    "Questions go to team@runpod.io, support@runpod.io or help@runpod.io.",
    "The helper refuses https://user:secret@huggingface.co/org/model because it carries credentials.",
    "Clone it with `git clone git@github.com:runpod/runpodctl.git`, or test the key with `ssh -T git@github.com`.",
    "Clone the model with `git clone git@hf.co:org/model`.",
    "Connect with `ssh abc123-64410f36@ssh.runpod.io -i ~/.ssh/id_ed25519`.",
    "Replace the last `torch.nn.Linear` layer and use a Linear warmup over 500 steps.",
    "Cache results in Redis, MySQL or Kafka, and post to a Slack webhook when the job ends.",
    "Put the new code path behind a feature flag.",
  ]) {
    assert.deepEqual(scanSkill(text), [], text);
  }
});

test("a long line is scanned in linear time", () => {
  const started = performance.now();
  assert.deepEqual(scanSkill("a,".repeat(100_000)), []);
  const elapsed = performance.now() - started;
  assert.ok(elapsed < 1_000, `scanning one 200,000-character line took ${Math.round(elapsed)} ms`);
});

test("skipped paths and binary files are not scanned, and packages/ is", () => {
  const leak = "Ask jane.doe@acme.dev for access.\n";
  const root = tree({
    "plugins/demo/node_modules/pkg/README.md": leak,
    "plugins/demo/.flash/out.md": leak,
    "ontology/build/graph.html": leak,
    "ontology/tools/src/validate.ts": leak,
    "ontology/tools/test/fixture.md": leak,
    "packages/knowledge/knowledge.json": leak,
    "packages/knowledge/runpod-plugin-knowledge-1.0.0.tgz": `\0${leak}`,
    "packages/knowledge/README.md": leak,
  });
  assert.deepEqual(scanFiles(root), {
    files: 1,
    binary: 1,
    findings: [{ file: "packages/knowledge/README.md", line: 1, why: "an email address" }],
  });
});

test("a rule that adds an image outside runpod/ fails, and every addition is listed", () => {
  const base = new Map([["pod.image", "Set `image` on create."]]);
  const head = new Map([
    [
      "pod.image",
      "Set `image` on create, such as `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`, or run " +
        "`docker pull nvidia/cuda:12.4.1-runtime-ubuntu22.04` with `HF_HOME=/workspace/hf`.",
    ],
  ]);
  const { added, errors } = compareRules(base, head);
  assert.deepEqual(
    added.map((item) => `${item.kind} ${item.text}`),
    [
      "command docker pull nvidia/cuda:12.4.1-runtime-ubuntu22.04",
      "image runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404",
      "image nvidia/cuda:12.4.1-runtime-ubuntu22.04",
      "env HF_HOME=/workspace/hf",
    ],
  );
  assert.deepEqual(errors, [
    "rule pod.image adds image nvidia/cuda:12.4.1-runtime-ubuntu22.04, which is not under runpod/",
  ]);
  assert.deepEqual(compareRules(head, head), { added: [], errors: [] });
});
