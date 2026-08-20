#!/usr/bin/env bash
# Deploy platform Lambda CODE (not infra). This is the only code-deploy path:
# the tofu lambda resource ignores source_code_hash so a routine `tofu apply`
# can never roll the API back to a stale local zip (see modules/api-gateway).
#
# Usage: scripts/deploy-lambda.sh [function-name]
#   AWS_PROFILE=civilai scripts/deploy-lambda.sh            # civilai-uat-api
#   AWS_PROFILE=civilai scripts/deploy-lambda.sh my-fn-name
#
# Large packages: the zip is ~48MB and AWS direct --zip-file uploads often time
# out from CI. Set LAMBDA_DEPLOY_S3_BUCKET (and optional LAMBDA_DEPLOY_S3_PREFIX)
# to upload via S3 instead. CI always sets the bucket.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUNCTION_NAME="${1:-civilai-uat-api}"
ZIP="${ROOT}/infra/dist/platform-lambda.zip"
S3_BUCKET="${LAMBDA_DEPLOY_S3_BUCKET:-}"
S3_PREFIX="${LAMBDA_DEPLOY_S3_PREFIX:-ci/platform-lambda/}"

echo "=== packaging (git ref: $(git -C "$ROOT" rev-parse --abbrev-ref HEAD) @ $(git -C "$ROOT" rev-parse --short HEAD)) ==="
"${ROOT}/scripts/package-lambda.sh"

echo "=== deploying ${ZIP} -> ${FUNCTION_NAME} ==="
if [[ -n "${S3_BUCKET}" ]]; then
  key="${S3_PREFIX%/}/$(git -C "$ROOT" rev-parse --short HEAD)-$(date -u +%Y%m%d%H%M%S).zip"
  echo "via s3://${S3_BUCKET}/${key}"
  aws s3 cp "${ZIP}" "s3://${S3_BUCKET}/${key}"
  aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --s3-bucket "${S3_BUCKET}" \
    --s3-key "${key}" \
    --query '[FunctionName,LastModified,CodeSha256]' \
    --output text
else
  aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${ZIP}" \
    --query '[FunctionName,LastModified,CodeSha256]' \
    --output text
fi

aws lambda wait function-updated --function-name "${FUNCTION_NAME}"
echo "=== deploy complete ==="
