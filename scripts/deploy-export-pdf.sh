#!/usr/bin/env bash
# Build/push the LibreOffice export-pdf container and update the Lambda image.
# Decoupled from scripts/deploy-lambda.sh (zip API) — same reason LO is not in the zip.
#
# Usage:
#   AWS_PROFILE=civilai scripts/deploy-export-pdf.sh
#   AWS_PROFILE=civilai scripts/deploy-export-pdf.sh civilai-uat-export-pdf
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUNCTION_NAME="${1:-civilai-uat-export-pdf}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-civilai}"
IMAGE_DIR="${ROOT}/export-pdf"
TAG="${EXPORT_PDF_IMAGE_TAG:-latest}"

echo "=== resolve ECR repo for ${FUNCTION_NAME} ==="
ACCOUNT_ID="$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)"
REPO_NAME="${FUNCTION_NAME}"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

aws ecr describe-repositories --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --repository-names "$REPO_NAME" >/dev/null

echo "=== docker login ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com ==="
aws ecr get-login-password --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "=== build arm64 image (git: $(git -C "$ROOT" rev-parse --short HEAD)) ==="
docker buildx build \
  --platform linux/arm64 \
  --provenance=false \
  -t "${ECR_URI}:${TAG}" \
  --push \
  "$IMAGE_DIR"

echo "=== update Lambda ${FUNCTION_NAME} → ${ECR_URI}:${TAG} ==="
aws lambda update-function-code \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --function-name "$FUNCTION_NAME" \
  --image-uri "${ECR_URI}:${TAG}" \
  --query '[FunctionName,LastModified,CodeSha256]' \
  --output text

aws lambda wait function-updated \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --function-name "$FUNCTION_NAME"

echo "=== deploy-export-pdf complete ==="
