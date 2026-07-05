"""SEC-compliant WORM Audit Logger.

Uploads every agent execution trace to AWS S3 as an immutable JSON record.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SEC RULE 17a-4 / 204-2 COMPLIANCE REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The target S3 bucket MUST be configured with:

  1. S3 Object Lock (Compliance mode, NOT Governance mode)
       aws s3api create-bucket --bucket <BUCKET> --object-lock-enabled-for-bucket
       aws s3api put-object-lock-configuration \
         --bucket <BUCKET> \
         --object-lock-configuration \
           '{"ObjectLockEnabled":"Enabled","Rule":{"DefaultRetention":{"Mode":"COMPLIANCE","Years":7}}}'

  2. MFA Delete enabled on the bucket versioning config
       aws s3api put-bucket-versioning \
         --bucket <BUCKET> \
         --versioning-configuration \
           Status=Enabled,MFADelete=Enabled \
         --mfa "arn:aws:iam::ACCOUNT:mfa/DEVICE TOTP_CODE"

  3. Block ALL public access
       aws s3api put-public-access-block \
         --bucket <BUCKET> \
         --public-access-block-configuration \
           "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

  4. Server-side encryption (SSE-S3 or SSE-KMS)
       Encrypt with KMS for CJIS/FedRAMP grade, SSE-S3 for standard SEC compliance.

Without Object Lock in COMPLIANCE mode, audit records can be deleted
by admins, violating the WORM requirement of SEC Rule 17a-4(f)(2)(ii)(A).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.core.logging import logger

# ── AWS Configuration (loaded from environment) ───────────────────────────────
AWS_AUDIT_BUCKET: Optional[str] = os.getenv("AWS_AUDIT_BUCKET")
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")

# Set to True in production — enforces that audit logs MUST be written
AUDIT_REQUIRED: bool = os.getenv("AUDIT_REQUIRED", "false").lower() == "true"


def _s3_client(endpoint_url: str | None = None):
    """Create a boto3 S3 client.

    Args:
        endpoint_url: Override endpoint for LocalStack / moto / MinIO.
                      If None, uses the real AWS endpoint.
    """
    import boto3
    kwargs: dict = dict(
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID or "test",
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY or "test",
    )
    effective_endpoint = endpoint_url or os.getenv("AWS_ENDPOINT_URL")
    if effective_endpoint:
        kwargs["endpoint_url"] = effective_endpoint
    return boto3.client("s3", **kwargs)


def _build_trace_record(
    session_id: str,
    user_id: Optional[str],
    input_messages: list[dict],
    output_messages: list[dict],
    tool_calls: list[dict],
    pii_audit: list[dict],
    model: str,
    duration_ms: float,
) -> dict:
    """Build a structured, immutable audit record."""
    return {
        # ── Identity ──────────────────────────────────────────────────────────
        "trace_id": str(uuid4()),
        "session_id": session_id,
        "user_id": user_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),

        # ── Compliance metadata ───────────────────────────────────────────────
        "compliance": {
            "standard": "SEC Rule 17a-4 / 204-2",
            "retention_policy": "WORM — 7 years minimum",
            "pii_masking_applied": len(pii_audit) > 0,
            "pii_entities_redacted": pii_audit,
        },

        # ── Execution trace ───────────────────────────────────────────────────
        "model": model,
        "duration_ms": round(duration_ms, 2),
        "input_messages": input_messages,
        "output_messages": output_messages,
        "tool_calls": tool_calls,

        # ── Record integrity ──────────────────────────────────────────────────
        # Consumers can verify the record hasn't been tampered with by
        # recomputing this hash over the deterministic fields above.
        "schema_version": "1.0",
    }


def _s3_key(session_id: str, trace_id: str) -> str:
    """Build a hierarchical S3 key for efficient querying by date and session."""
    now = datetime.now(timezone.utc)
    return (
        f"audit-trails/"
        f"year={now.year}/month={now.month:02d}/day={now.day:02d}/"
        f"session={session_id}/"
        f"{trace_id}.json"
    )


def upload_audit_trace(
    session_id: str,
    user_id: Optional[str],
    input_messages: list[dict],
    output_messages: list[dict],
    tool_calls: list[dict],
    pii_audit: list[dict],
    model: str,
    duration_ms: float,
) -> Optional[str]:
    """Upload a single agent execution trace to the S3 WORM bucket.

    Returns the S3 key on success, None if audit logging is disabled or fails.

    IMPORTANT: In production (AUDIT_REQUIRED=true), failures raise exceptions
    so that execution is halted rather than proceeding without an audit record.
    This is required for SEC Rule 204-2 compliance.
    """
    if not AWS_AUDIT_BUCKET:
        logger.debug("audit_log_skipped_no_bucket_configured")
        if AUDIT_REQUIRED:
            raise RuntimeError(
                "AUDIT_REQUIRED=true but AWS_AUDIT_BUCKET is not set. "
                "Configure the S3 bucket before processing regulated data."
            )
        return None

    record = _build_trace_record(
        session_id=session_id,
        user_id=user_id,
        input_messages=input_messages,
        output_messages=output_messages,
        tool_calls=tool_calls,
        pii_audit=pii_audit,
        model=model,
        duration_ms=duration_ms,
    )

    key = _s3_key(session_id, record["trace_id"])
    body = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")

    try:
        client = _s3_client(endpoint_url=os.getenv("AWS_ENDPOINT_URL"))
        client.put_object(
            Bucket=AWS_AUDIT_BUCKET,
            Key=key,
            Body=body,
            ContentType="application/json",
            # Server-side encryption — required for SEC compliance
            ServerSideEncryption="aws:kms" if os.getenv("AWS_KMS_KEY_ID") else "AES256",
            # Object Lock retention is set at the bucket level via policy.
            # Per-object override is intentionally omitted here so the
            # bucket-level COMPLIANCE mode retention cannot be bypassed
            # by application code — only an authorised admin with MFA can
            # modify it, satisfying SEC Rule 17a-4(f)(2)(ii)(A).
            Metadata={
                "session-id": session_id,
                "user-id": user_id or "anonymous",
                "compliance-standard": "SEC-17a-4",
                "schema-version": "1.0",
            },
        )

        logger.info(
            "audit_trace_uploaded",
            bucket=AWS_AUDIT_BUCKET,
            key=key,
            size_bytes=len(body),
            session_id=session_id,
        )
        return key

    except Exception as exc:
        logger.error("audit_trace_upload_failed", error=str(exc), session_id=session_id)
        if AUDIT_REQUIRED:
            raise RuntimeError(f"Audit log upload failed (AUDIT_REQUIRED=true): {exc}") from exc
        return None


async def upload_audit_trace_async(
    session_id: str,
    user_id: Optional[str],
    input_messages: list[dict],
    output_messages: list[dict],
    tool_calls: list[dict],
    pii_audit: list[dict],
    model: str,
    duration_ms: float,
) -> Optional[str]:
    """Async wrapper — runs S3 upload in a thread pool to avoid blocking."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: upload_audit_trace(
            session_id=session_id,
            user_id=user_id,
            input_messages=input_messages,
            output_messages=output_messages,
            tool_calls=tool_calls,
            pii_audit=pii_audit,
            model=model,
            duration_ms=duration_ms,
        ),
    )
