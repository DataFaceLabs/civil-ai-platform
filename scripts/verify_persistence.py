#!/usr/bin/env python3
"""Print platform persistence status."""

from __future__ import annotations

import json
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


def verify_file_store() -> int:
    snapshot = Path(FILE_STORE_PATH) / "store.json"
    print(f"File store: {snapshot.resolve()}")
    if not snapshot.exists():
        print("No persisted data yet (create a project in the UI first).")
        return 0

    raw = json.loads(snapshot.read_text(encoding="utf-8"))
    projects = raw.get("projects", {})
    states = raw.get("states", {})
    print(f"Projects on disk: {len(projects)}")
    for key, payload in sorted(projects.items()):
        print(f"  - {payload.get('name', '(unnamed)')} [{payload.get('project_id', key)}]")
    print(f"Project states on disk: {len(states)}")
    return 0


def verify_dynamodb() -> int:
    if DYNAMODB_ENDPOINT:
        ddb = boto3.resource(
            "dynamodb",
            region_name=REGION,
            endpoint_url=DYNAMODB_ENDPOINT,
            aws_access_key_id="local",
            aws_secret_access_key="local",
        )
    else:
        session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=REGION)
        ddb = session.resource("dynamodb")
    table = ddb.Table(TABLE_NAME)

    print(f"DynamoDB endpoint: {DYNAMODB_ENDPOINT or 'AWS default'}")
    print(f"Table: {TABLE_NAME}")
    try:
        table.load()
    except ClientError as exc:
        print(f"DynamoDB table not accessible: {exc}", file=sys.stderr)
        return 1

    resp = table.scan(
        FilterExpression="begins_with(SK, :prefix) AND entityType = :et",
        ExpressionAttributeValues={":prefix": "PROJECT#", ":et": "Project"},
    )
    projects = resp.get("Items", [])
    print(f"Projects in DynamoDB: {len(projects)}")
    for item in sorted(projects, key=lambda i: i.get("SK", "")):
        payload = json.loads(item["payload"])
        print(
            f"  - {payload.get('name', '(unnamed)')} "
            f"[{payload.get('project_id', '?')}]"
        )
    return 0


def verify_s3() -> int:
    if os.environ.get("CIVILAI_ARTIFACT_BACKEND", "s3") != "s3":
        return 0
    s3 = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=REGION).client("s3")
    print(f"S3 bucket: {BUCKET_NAME}")
    try:
        keys = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="tenant/", MaxKeys=20)
        count = keys.get("KeyCount", 0)
        print(f"S3 artifact objects under tenant/ (sample, max 20): {count}")
        for obj in keys.get("Contents", []):
            print(f"  - {obj['Key']} ({obj['Size']} bytes)")
    except ClientError as exc:
        print(f"S3 bucket not accessible: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    print(f"Store backend: {STORE_BACKEND}")
    print()
    if STORE_BACKEND == "file":
        code = verify_file_store()
    elif STORE_BACKEND == "dynamodb":
        code = verify_dynamodb()
    else:
        print("Memory store — nothing to verify on disk.")
        code = 0
    if code != 0:
        return code
    print()
    return verify_s3()


if __name__ == "__main__":
    raise SystemExit(main())
