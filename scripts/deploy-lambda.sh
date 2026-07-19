#!/usr/bin/env bash
# Deploy platform Lambda CODE (not infra). This is the only code-deploy path:
# the tofu lambda resource ignores source_code_hash so a routine `tofu apply`
# can never roll the API back to a stale local zip (see modules/api-gateway).
#
# Usage: scripts/deploy-lambda.sh [function-name]
#   AWS_PROFILE=civilai scripts/deploy-lambda.sh            # civilai-uat-api
#   AWS_PROFILE=civilai scripts/deploy-lambda.sh my-fn-name
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUNCTION_NAME="${1:-civilai-uat-api}"
ZIP="${ROOT}/infra/dist/platform-lambda.zip"

echo "=== packaging (git ref: $(git -C "$ROOT" rev-parse --abbrev-ref HEAD) @ $(git -C "$ROOT" rev-parse --short HEAD)) ==="
"${ROOT}/scripts/package-lambda.sh"

echo "=== deploying ${ZIP} -> ${FUNCTION_NAME} ==="
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://${ZIP}" \
  --query '[FunctionName,LastModified,CodeSha256]' \
  --output text

aws lambda wait function-updated --function-name "$FUNCTION_NAME"
echo "=== deploy complete ==="
