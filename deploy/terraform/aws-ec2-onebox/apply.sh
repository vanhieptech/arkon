#!/usr/bin/env bash
# One-command deploy wrapper for Arkon EC2 one-box.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f terraform.tfvars ]]; then
  echo "Missing terraform.tfvars — copy from terraform.tfvars.example and set key_name."
  exit 1
fi

terraform init -upgrade
terraform apply "$@"

echo ""
echo "=== Outputs ==="
terraform output ui_url
terraform output api_url
echo "Admin password: terraform output -raw admin_password"
echo "Bootstrap log:  terraform output bootstrap_log"
