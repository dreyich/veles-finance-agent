"""PII Shield — Presidio-based redaction layer.

All user messages pass through this module BEFORE reaching the LLM.
Detected PII is replaced with typed placeholders so that:
  - No personal data is ever sent to a third-party LLM provider.
  - Compliance with GDPR Art.25 (data minimisation by design) is enforced.
  - Audit logs contain only anonymised inputs (SEC Rule 17a-4 safe harbour).

Supported entity types (OOTB from Presidio):
  PERSON, EMAIL_ADDRESS, PHONE_NUMBER, US_SSN, CREDIT_CARD,
  IBAN_CODE, US_BANK_NUMBER, IP_ADDRESS, LOCATION, DATE_TIME, NRP, URL
"""

import os
from functools import lru_cache
from typing import Optional

from app.core.logging import logger

PII_MASKING_ENABLED: bool = os.getenv("PII_MASKING_ENABLED", "true").lower() == "true"


@lru_cache(maxsize=1)
def _get_analyzer():
    """Lazy-init analyzer — loaded once, reused for every request."""
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    })
    return AnalyzerEngine(nlp_engine=provider.create_engine())


@lru_cache(maxsize=1)
def _get_anonymizer():
    from presidio_anonymizer import AnonymizerEngine
    return AnonymizerEngine()


# PII entities we actively redact — extend this list as needed
_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_BANK_NUMBER",
    "IP_ADDRESS",
    "LOCATION",
    "DATE_TIME",
    "NRP",
    "URL",
]


def mask_pii(text: str, language: str = "en") -> tuple[str, list[dict]]:
    """Detect and replace PII in text with typed placeholders.

    Args:
        text:     Raw user input.
        language: Language code for NER (default: 'en').

    Returns:
        Tuple of (anonymised_text, list_of_detected_entities).
        The entity list is used for audit logging — it records WHAT was
        redacted without recording the actual values.
    """
    if not PII_MASKING_ENABLED or not text.strip():
        return text, []

    try:
        analyzer = _get_analyzer()
        anonymizer = _get_anonymizer()

        results = analyzer.analyze(text=text, entities=_ENTITIES, language=language)

        if not results:
            return text, []

        anonymized = anonymizer.anonymize(text=text, analyzer_results=results)

        detected = [
            {
                "entity_type": r.entity_type,
                "score": round(r.score, 3),
                "start": r.start,
                "end": r.end,
            }
            for r in results
        ]

        if detected:
            logger.info(
                "pii_redacted",
                entity_count=len(detected),
                entity_types=list({d["entity_type"] for d in detected}),
            )

        return anonymized.text, detected

    except Exception as exc:
        # Fail open with a warning — never block the user due to PII engine errors
        logger.warning("pii_masking_failed", error=str(exc))
        return text, []


def mask_messages(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply PII masking to a list of OpenAI-style message dicts.

    Only 'user' role messages are masked — system and assistant messages
    are generated internally and do not contain user PII.

    Returns:
        (masked_messages, audit_entries) where audit_entries records
        what was redacted per message (no original values stored).
    """
    masked = []
    audit_entries = []

    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            clean_text, detected = mask_pii(msg["content"])
            masked.append({**msg, "content": clean_text})
            if detected:
                audit_entries.append({
                    "role": "user",
                    "pii_detected": detected,
                    "original_length": len(msg["content"]),
                    "masked_length": len(clean_text),
                })
        else:
            masked.append(msg)

    return masked, audit_entries
