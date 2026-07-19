"""DOCX → PDF converter for the Civil1 export path (M1-X2).

Invoked by the zip API Lambda after `study.docx` is stored. Contract:

  in:  {"bucket": str, "docx_key": str, "pdf_key": str}
  out: {"ok": true, "pdf_key": str}

LibreOffice runs headless against /tmp; Civil1 OFL fonts are baked into the image.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# LibreOffice profile must live on a writable FS (Lambda only allows /tmp).
_LO_PROFILE = "file:///tmp/lo_profile"
_SOFFICE = os.environ.get("CIVILAI_SOFFICE", "soffice")


def _s3():
    return boto3.client("s3")


def convert_file(docx_path: Path, out_dir: Path) -> Path:
    """Run LibreOffice headless conversion; return the produced PDF path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        _SOFFICE,
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--nodefault",
        "--nofirststartwizard",
        f"-env:UserInstallation={_LO_PROFILE}",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(out_dir),
        str(docx_path),
    ]
    logger.info("running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
        env={**os.environ, "HOME": "/tmp", "SAL_USE_VCLPLUGIN": "svp"},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"soffice failed ({result.returncode}): "
            f"stdout={result.stdout[-500:]!r} stderr={result.stderr[-500:]!r}"
        )
    pdf_path = out_dir / f"{docx_path.stem}.pdf"
    if not pdf_path.is_file():
        raise RuntimeError(f"PDF not produced at {pdf_path}; soffice out={result.stdout!r}")
    return pdf_path


def handle(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    bucket = str(event.get("bucket") or os.environ.get("CIVILAI_APP_BUCKET") or "")
    docx_key = str(event.get("docx_key") or "")
    pdf_key = str(event.get("pdf_key") or "")
    if not (bucket and docx_key and pdf_key):
        raise ValueError("bucket, docx_key, and pdf_key are required")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        work = Path(tmp)
        docx_path = work / "study.docx"
        _s3().download_file(bucket, docx_key, str(docx_path))
        pdf_path = convert_file(docx_path, work)
        _s3().upload_file(
            str(pdf_path),
            bucket,
            pdf_key,
            ExtraArgs={"ContentType": "application/pdf"},
        )
    logger.info("converted s3://%s/%s -> s3://%s/%s", bucket, docx_key, bucket, pdf_key)
    return {"ok": True, "pdf_key": pdf_key}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint (awslambdaric)."""
    # API Gateway / test wrappers sometimes wrap the body.
    if isinstance(event.get("body"), str):
        event = json.loads(event["body"] or "{}")
    return handle(event, context)
