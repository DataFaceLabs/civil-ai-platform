# Local platform API

```bash
cd civil-ai-platform
make install
cp .env.example .env.local   # edit AWS_PROFILE if needed
make persistence             # create civilai-app-dev table + S3 CORS
make api                     # http://localhost:8001 (reads .env.local)
```

## Durable persistence (default)

| Layer | Backend | Location |
| --- | --- | --- |
| Projects, tenants, workflow state | **AWS DynamoDB** | `civilai-app-dev` table in your AWS account |
| Uploaded documents | **S3** | `s3://civilai-data/tenant/...` |

Requires `AWS_PROFILE` (or default credentials) with DynamoDB and S3 permissions.

### Setup

```bash
# .env.local — no endpoint URL means real AWS DynamoDB
CIVILAI_STORE_BACKEND=dynamodb
CIVILAI_DYNAMODB_TABLE=civilai-app-dev
CIVILAI_ARTIFACT_BACKEND=s3
CIVILAI_APP_BUCKET=civilai-data
AWS_PROFILE=civilai
AWS_REGION=us-east-1

make persistence
make api
```

### Verify

After creating projects in the workbench:

```bash
make verify-persistence
```

Restart `make api` and reload the browser — projects should still load.

## DynamoDB Local (optional, no AWS)

If you prefer a local DynamoDB instance instead of AWS:

```bash
# .env.local
CIVILAI_DYNAMODB_ENDPOINT_URL=http://localhost:8002

make persistence-up   # starts Docker + provisions table
make api
```

Stop local DynamoDB:

```bash
make persistence-down
```

## Enable in frontend

```bash
# civil-ai-fe/.env.local
VITE_CIVILAI_PLATFORM_MODE=true
VITE_CIVILAI_PLATFORM_API=http://localhost:8001
```

Keep `civil-ai-data` on port 8000 for site payloads.

## Memory mode (ephemeral)

```bash
CIVILAI_STORE_BACKEND=memory
CIVILAI_ARTIFACT_BACKEND=memory
```

## File store (no AWS)

```bash
CIVILAI_STORE_BACKEND=file
CIVILAI_FILE_STORE_PATH=.local/platform-store
```

## AWS deploy

```bash
cd infra/opentofu/environments/dev
tofu init
tofu plan
tofu apply
```

Set `CIVILAI_STORE_BACKEND=dynamodb` and Cognito env vars on Lambda.
