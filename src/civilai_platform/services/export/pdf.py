"""DOCX → PDF conversion for the export pipeline (M1-X2).

Production: the zip API Lambda invokes the dedicated LibreOffice container Lambda
(`CIVILAI_EXPORT_PDF_FUNCTION`), which reads/writes S3. Local/tests: optional
in-process conversion via `soffice` or Docker when available.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def pdf_converter_function_name() -> str | None:
    name = (os.getenv("CIVILAI_EXPORT_PDF_FUNCTION") or "").strip()
    return name or None


def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Convert DOCX bytes to PDF via local LibreOffice or a Docker LO image.

    Used by optional integration tests / local smoke. Production uses
    `invoke_pdf_converter` against the container Lambda.
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        docx_path = work / "study.docx"
        docx_path.write_bytes(docx_bytes)
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(work),
                    str(docx_path),
                ],
                check=True,
                capture_output=True,
                timeout=90,
            )
        else:
            # Same image family used for fidelity checks in M1-DESIGN.
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{work}:/work",
                    "minidocks/libreoffice",
                    "soffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    "/work",
                    "/work/study.docx",
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        pdf_path = work / "study.pdf"
        if not pdf_path.is_file():
            raise RuntimeError("LibreOffice did not produce study.pdf")
        return pdf_path.read_bytes()


def invoke_pdf_converter(*, docx_s3_key: str, pdf_s3_key: str) -> None:
    """Ask the export-pdf container Lambda to convert S3 DOCX → S3 PDF."""
    import boto3

    from civilai_platform.settings import get_settings

    function_name = pdf_converter_function_name()
    if not function_name:
        raise RuntimeError("CIVILAI_EXPORT_PDF_FUNCTION unset")

    settings = get_settings()
    bucket = settings.app_bucket
    if not bucket:
        raise RuntimeError("CIVILAI_APP_BUCKET unset; cannot convert export PDF")

    payload = {
        "bucket": bucket,
        "docx_key": docx_s3_key,
        "pdf_key": pdf_s3_key,
    }
    client = boto3.client("lambda", region_name=settings.aws_region)
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    raw = response.get("Payload")
    body = raw.read() if raw is not None else b"{}"
    if response.get("FunctionError"):
        raise RuntimeError(f"export PDF Lambda error: {body.decode('utf-8', errors='replace')}")
    result = json.loads(body.decode("utf-8") or "{}")
    if not result.get("ok"):
        raise RuntimeError(f"export PDF converter returned unexpected payload: {result}")
    logger.info("PDF stored at %s", pdf_s3_key)
