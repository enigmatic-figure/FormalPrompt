from __future__ import annotations

import hashlib
import json
from typing import Any

from formalprompt.models import CanvasDocument


def canonical_document_bytes(document: dict[str, Any] | CanvasDocument) -> bytes:
    model = (
        document
        if isinstance(document, CanvasDocument)
        else CanvasDocument.model_validate(document)
    )
    return json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def document_sha256(document: dict[str, Any] | CanvasDocument) -> str:
    return hashlib.sha256(canonical_document_bytes(document)).hexdigest()
