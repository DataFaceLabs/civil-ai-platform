#!/usr/bin/env python3
"""Provision persistence for local platform dev (idempotent)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("CIVILAI_DYNAMODB_TABLE", "civilai-app-dev")
BUCKET_NAME = os.environ.get("CIVILAI_APP_BUCKET", "civilai-data")
REGION = os.environ.get("AWS_REGION", "us-east-1")
STORE_BACKEND = os.environ.get("CIVILAI_STORE_BACKEND", "file")
FILE_STORE_PATH = os.environ.get("CIVILAI_FILE_STORE_PATH", ".local/platform-store")
DYNAMODB_ENDPOINT = os.environ.get("CIVILAI_DYNAMODB_ENDPOINT_URL") or None
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]


def ensure_file_store() -> None:
    path = Path(FILE_STORE_PATH)
    path.mkdir(parents=True, exist_ok=True)
    print(f"File store ready: {path.resolve()}")


def _ddb_client():
    if DYNAMODB_ENDPOINT:
        return boto3.client(
            "dynamodb",
            region_name=REGION,
            endpoint_url=DYNAMODB_ENDPOINT,
            aws_access_key_id="local",
            aws_secret_access_key="local",
        )
    profile = os.environ.get("AWS_PROFILE")
    return boto3.Session(profile_name=profile, region_name=REGION).client("dynamodb")


def ensure_dynamodb_table(ddb) -> None:
    existing = ddb.list_tables().get("TableNames", [])
    if TABLE_NAME in existing:
        print(f"DynamoDB table already exists: {TABLE_NAME}")
        return

    target = DYNAMODB_ENDPOINT or "AWS"
    print(f"Creating DynamoDB table on {target}: {TABLE_NAME}")
    ddb.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
            {"AttributeName": "GSI2PK", "AttributeType": "S"},
            {"AttributeName": "GSI2SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "GSI2",
                "KeySchema": [
                    {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        SSESpecification={"Enabled": True},
    )
    waiter = ddb.get_waiter("table_exists")
    waiter.wait(TableName=TABLE_NAME)
    print(f"DynamoDB table ready: {TABLE_NAME}")


def ensure_s3_cors(s3) -> None:
    artifact_backend = os.environ.get("CIVILAI_ARTIFACT_BACKEND", "s3")
    if artifact_backend != "s3":
        print(f"Skipping S3 CORS (artifact backend: {artifact_backend})")
        return

    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
    except ClientError as exc:
        print(f"S3 bucket not accessible: {BUCKET_NAME} ({exc})", file=sys.stderr)
        raise SystemExit(1) from exc

    existing_rules: list[dict] = []
    try:
        cors = s3.get_bucket_cors(Bucket=BUCKET_NAME)
        existing_rules = cors.get("CORSRules", [])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchCORSConfiguration":
            raise

    origins = {o for rule in existing_rules for o in rule.get("AllowedOrigins", [])}
    missing = [o for o in CORS_ORIGINS if o not in origins]
    if not missing and existing_rules:
        print(f"S3 CORS already configured on: {BUCKET_NAME}")
        return

    merged_origins = sorted(set(origins) | set(CORS_ORIGINS))
    rule = {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT", "HEAD"],
        "AllowedOrigins": merged_origins,
        "ExposeHeaders": ["ETag"],
        "MaxAgeSeconds": 3600,
    }
    s3.put_bucket_cors(Bucket=BUCKET_NAME, CORSConfiguration={"CORSRules": [rule]})
    print(f"S3 CORS updated on: {BUCKET_NAME}")


def main() -> int:
    print(f"Store backend: {STORE_BACKEND}")
    if STORE_BACKEND == "file":
        ensure_file_store()
    elif STORE_BACKEND == "dynamodb":
        print(f"DynamoDB endpoint: {DYNAMODB_ENDPOINT or 'AWS default'}")
        print(f"DynamoDB table: {TABLE_NAME}")
        ensure_dynamodb_table(_ddb_client())
    else:
        print("Memory store — no provisioning required")

    ensure_s3_cors(
        boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=REGION).client("s3")
    )

    print()
    print("Persistence ready. Restart platform API if it is already running:")
    print("  cd civil-ai-platform && make api")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClientError as exc:
        print(f"AWS error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
