---
concepts: [file-transfer]
---

# AWS CLI — one-time setup

Install the AWS CLI (only needed once, if `aws --version` fails). Credentials, region
rules, and commands are in [`aws.md`](aws.md).

```bash
# macOS
brew install awscli

# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install
```
