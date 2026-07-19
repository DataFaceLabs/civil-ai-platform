variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "cognito_user_pool_arn" {
  type = string
}

variable "cognito_user_pool_id" {
  type = string
}

variable "cognito_client_id" {
  type = string
}

variable "bedrock_policy_arn" {
  type = string
}

variable "dynamodb_table_arn" {
  type = string
}

variable "app_bucket_arn" {
  type = string
}

variable "agent_corpus_bucket" {
  type        = string
  default     = ""
  description = "Agent training-corpus bucket name. Empty disables corpus capture (writes are skipped)."
}

variable "agent_corpus_bucket_arn" {
  type        = string
  default     = ""
  description = "ARN of the agent training-corpus bucket, for the Lambda PutObject grant."
}

variable "data_api_base_url" {
  type = string
}

variable "dev_data_api_base_url" {
  type        = string
  default     = ""
  description = "Optional dev data plane selected only for exact dev_data_origins."
}

variable "dev_data_origins" {
  type        = list(string)
  default     = []
  description = "Exact browser Origins permitted to select dev_data_api_base_url."
}

variable "data_service_key_parameter" {
  type = string
}

variable "data_service_key" {
  type      = string
  sensitive = true
}

variable "create_http_api" {
  type    = bool
  default = false
}

variable "lambda_package_path" {
  type        = string
  default     = ""
  description = "Path to platform Lambda zip; required when create_http_api=true."
}

variable "dev_auth" {
  type        = bool
  default     = false
  description = <<-EOT
    Enables POST /v1/dev/bootstrap (email-only login, no real Cognito auth). The FE has
    no Cognito Hosted UI flow yet, so this is the only way to sign in until that's built.
    Anyone with the app URL and an email can sign in as any user -- never enable for an
    environment that isn't gated behind an obscure/unshared URL.
  EOT
}

locals {
  name_prefix = "civilai-${var.environment}"
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      var.dynamodb_table_arn,
      "${var.dynamodb_table_arn}/index/*",
    ]
  }

  statement {
    sid    = "S3App"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      var.app_bucket_arn,
      "${var.app_bucket_arn}/*",
    ]
  }

  dynamic "statement" {
    for_each = var.agent_corpus_bucket_arn == "" ? [] : [1]
    content {
      sid    = "S3AgentCorpusWrite"
      effect = "Allow"
      # Write-only append of generation traces; the Lambda never reads or deletes the
      # corpus (that's the Phase 2 dataset-builder's job, out of the request path).
      actions   = ["s3:PutObject"]
      resources = ["${var.agent_corpus_bucket_arn}/*"]
    }
  }

  statement {
    sid    = "CognitoAdmin"
    effect = "Allow"
    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminDisableUser",
      "cognito-idp:AdminEnableUser",
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminSetUserPassword",
      "cognito-idp:AdminUpdateUserAttributes",
    ]
    resources = [var.cognito_user_pool_arn]
  }

  statement {
    sid    = "ReadSecrets"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:parameter/civilai/${var.environment}/*",
    ]
  }

  statement {
    sid       = "SelfInvokeAsyncAgent"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${var.aws_region}:*:function:${local.name_prefix}-api"]
  }
}

resource "aws_iam_role" "lambda" {
  name = "${local.name_prefix}-platform-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name_prefix}-platform-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_iam_role_policy_attachment" "bedrock" {
  role       = aws_iam_role.lambda.name
  policy_arn = var.bedrock_policy_arn
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  count      = var.create_http_api ? 1 : 0
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "platform" {
  count = var.create_http_api ? 1 : 0

  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda.arn
  handler       = "civilai_platform.lambda_handler.handler"
  runtime       = "python3.12"
  # scripts/package-lambda.sh builds native deps (pydantic-core, etc.) targeting
  # aarch64-manylinux2014 -- must match, or compiled extensions fail to import at cold
  # start ("No module named 'pydantic_core._pydantic_core'") since the default here is x86_64.
  architectures = ["arm64"]
  # Sync API Gateway requests must return in <=29s. Agent-runs and async tenant LLM
  # invoke enqueue Lambda Event workers (CIVILAI_AGENT_ASYNC=true). Draft LLM upstream
  # timeout is ~660s — worker needs Lambda max headroom (900s).
  timeout     = 900
  memory_size = 1024

  filename         = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

  lifecycle {
    # Code deploys are decoupled from infra applies: scripts/deploy-lambda.sh
    # (package + update-function-code) is the code path. Without this, any
    # machine holding a stale dist/platform-lambda.zip would silently ROLL BACK
    # the customer API on a routine `tofu apply` (observed 2026-07-19: local zip
    # from 07-15 vs deployed code from 07-17). The zip is still required at
    # create time for the initial deploy.
    ignore_changes = [filename, source_code_hash]
  }

  environment {
    variables = {
      CIVILAI_ENVIRONMENT           = var.environment
      CIVILAI_DEV_AUTH              = var.dev_auth ? "true" : "false"
      CIVILAI_STORE_BACKEND         = "dynamodb"
      CIVILAI_DYNAMODB_TABLE        = "civilai-app-${var.environment}"
      CIVILAI_ARTIFACT_BACKEND      = "s3"
      CIVILAI_APP_BUCKET            = replace(var.app_bucket_arn, "arn:aws:s3:::", "")
      CIVILAI_AGENT_CORPUS_BUCKET   = var.agent_corpus_bucket
      CIVILAI_DATA_API_BASE         = var.data_api_base_url
      CIVILAI_DEV_DATA_API_BASE     = var.dev_data_api_base_url
      CIVILAI_DEV_DATA_ORIGINS      = join(",", var.dev_data_origins)
      CIVILAI_DATA_SERVICE_KEY      = var.data_service_key
      CIVILAI_COGNITO_USER_POOL_ID  = var.cognito_user_pool_id
      CIVILAI_COGNITO_APP_CLIENT_ID = var.cognito_client_id
      # Live Strands agent (false). Local tests / e2e-platform.sh override to true.
      CIVILAI_AGENT_DRY_RUN = "false"
      # Return HTTP immediately for agent-runs and tenant LLM invoke; complete via
      # Lambda Event self-invoke (API Gateway ~29s sync cap). Also read as
      # CIVILAI_LLM_ASYNC default by llm_invoke.llm_invoke_async_enabled().
      CIVILAI_AGENT_ASYNC = "true"
      # Section drafts use the deterministic fetch/dispatch/render pipeline instead of
      # the legacy multi-turn Strands tool loop (keeps facts section-scoped, lower tokens).
      CIVILAI_DRAFT_PIPELINE = "1"
      # API Gateway's own cors_configuration below already scopes allow_origins to "*" at
      # the edge; matching it here (rather than the app's localhost-only default) is what
      # lets FastAPI's CORSMiddleware answer the OPTIONS preflight route (see
      # aws_apigatewayv2_route.options_proxy) with a 2xx instead of a 400 "disallowed
      # origin". Real authorization still comes from the Cognito JWT authorizer on every
      # other route -- this only affects which script-origins may attempt a request.
      CIVILAI_CORS_ORIGINS = "*"
    }
  }
}

# Platform reads service key from SSM at cold start — wire via env or extend settings.py.
# Until then, pass plaintext via tofu variable at deploy time (see uat README).

resource "aws_apigatewayv2_api" "main" {
  count         = var.create_http_api ? 1 : 0
  name          = "${local.name_prefix}-http"
  protocol_type = "HTTP"

  cors_configuration {
    # Auth is a Bearer token in the Authorization header (Cognito JWT authorizer below),
    # not cookies -- credentialed CORS isn't needed, and AWS rejects allow_credentials=true
    # combined with a wildcard origin anyway.
    # API Gateway's own CORS layer takes precedence over whatever the Lambda/FastAPI
    # CORSMiddleware would return -- if a preflight requests a header outside this static
    # list (e.g. x-tenant-id, which the FE sends on every tenant-scoped call), API Gateway
    # drops the CORS headers from the response entirely rather than returning a partial
    # match. Every header the platform client actually sends must be listed here.
    allow_credentials = false
    allow_headers     = ["authorization", "content-type", "x-request-id", "x-tenant-id", "x-dev-user-id"]
    allow_methods     = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_origins     = ["*"]
    max_age           = 300
  }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  count = var.create_http_api ? 1 : 0

  api_id           = aws_apigatewayv2_api.main[0].id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito"

  jwt_configuration {
    audience = [var.cognito_client_id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${var.cognito_user_pool_id}"
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  count = var.create_http_api ? 1 : 0

  api_id                 = aws_apigatewayv2_api.main[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.platform[0].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  count = var.create_http_api ? 1 : 0

  api_id    = aws_apigatewayv2_api.main[0].id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"

  # $default is a catch-all -- when dev_auth is on there's no Cognito token to authorize
  # (the FE has no Hosted UI flow yet, see dev_auth var doc), so the gate has to move down
  # to the app layer (get_auth_context's X-Dev-User-Id fallback) or every request 401s at
  # API Gateway before Lambda ever runs.
  authorization_type = var.dev_auth ? "NONE" : "JWT"
  authorizer_id      = var.dev_auth ? null : aws_apigatewayv2_authorizer.cognito[0].id
}

# Browsers never send an Authorization header on a CORS preflight OPTIONS request, so
# routing OPTIONS through $default's JWT authorizer makes every preflight 401 -- and a
# non-2xx preflight response is rejected by the browser regardless of the CORS headers
# API Gateway's cors_configuration attaches to it. This explicit, unauthenticated route
# takes priority over $default for OPTIONS and lets FastAPI's own CORSMiddleware answer
# the preflight; the actual request on every other method still requires a valid JWT.
resource "aws_apigatewayv2_route" "options_proxy" {
  count = var.create_http_api ? 1 : 0

  api_id    = aws_apigatewayv2_api.main[0].id
  route_key = "OPTIONS /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"

  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "health" {
  count = var.create_http_api ? 1 : 0

  api_id    = aws_apigatewayv2_api.main[0].id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

# /v1/public/* is unauthenticated by design -- it serves tenant branding (name + logo)
# for a login page to render BEFORE the user has a token. Behind the $default JWT
# authorizer it 401s for logged-out visitors, which surfaces as an "Organization not
# found" error boundary on the FE. The app-layer router under this prefix takes no auth
# dependency and exposes no sensitive data, so exempt it from the authorizer.
resource "aws_apigatewayv2_route" "public" {
  count = var.create_http_api ? 1 : 0

  api_id    = aws_apigatewayv2_api.main[0].id
  route_key = "GET /v1/public/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"

  authorization_type = "NONE"
}

# Access-log group was originally created out-of-band (console, release-migration
# era) and imported into state 2026-07-19 — without this resource + the stage block
# below, every plan wanted to strip live access logging.
resource "aws_cloudwatch_log_group" "apigw_access" {
  count = var.create_http_api ? 1 : 0

  name              = "/aws/apigateway/${local.name_prefix}-access"
  retention_in_days = 3
}

resource "aws_apigatewayv2_stage" "default" {
  count = var.create_http_api ? 1 : 0

  api_id      = aws_apigatewayv2_api.main[0].id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigw_access[0].arn
    format          = "$context.requestId $context.requestTime $context.httpMethod $context.path $context.status ip=$context.identity.sourceIp ua=$context.identity.userAgent sub=$context.authorizer.claims.sub"
  }
}

resource "aws_lambda_permission" "apigw" {
  count = var.create_http_api ? 1 : 0

  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.platform[0].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main[0].execution_arn}/*/*"
}

output "lambda_role_arn" {
  value = aws_iam_role.lambda.arn
}

output "lambda_function_name" {
  value = var.create_http_api ? aws_lambda_function.platform[0].function_name : ""
}

output "api_endpoint" {
  value = var.create_http_api ? aws_apigatewayv2_api.main[0].api_endpoint : "https://api-${var.environment}.civil1.ai"
}
