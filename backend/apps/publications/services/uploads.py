"""Common handling of an uploaded PDF before it is stored (plan section 4.2).

Shared by the draft upload and the new-version upload: the declared
file is checked (extension and type) and copied to ``tmp/uploads``,
where :class:`~apps.publications.services.pdf.PdfService` validates it.
The caller owns the staged file and must delete it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from apps.publications.services.pdf import PdfInvalid, PdfService, PdfTooLarge
from apps.publications.services.storage import open_exclusive, upload_tmp_path
from config.exceptions import DomainError, ErrorCode

#: Declared types of the file part that can carry a PDF. Browsers send
#: ``application/octet-stream`` or nothing for some systems; the real
#: barrier is the content check, this only rejects an obviously wrong type.
ACCEPTED_CONTENT_TYPES = ("application/pdf", "application/x-pdf", "application/octet-stream", "")


def check_declared_file(uploaded: Any) -> None:
    """Extension and declared type: a cheap, early and strict filter."""
    if Path(uploaded.name or "").suffix.lower() != ".pdf":
        raise PdfInvalid("Solo se admiten archivos PDF (extensión .pdf).")
    declared = (uploaded.content_type or "").split(";")[0].strip().lower()
    if declared not in ACCEPTED_CONTENT_TYPES:
        raise DomainError(
            "El tipo de contenido del archivo no es PDF.",
            code=ErrorCode.PDF_UNSUPPORTED,
            details={"content_type": declared},
        )


def stage_upload(uploaded: Any, service: PdfService) -> Path:
    """Copy the upload to ``tmp/uploads``; the caller owns the staged file."""
    if uploaded.size > service.max_bytes:
        raise PdfTooLarge(service.max_bytes)
    staged = upload_tmp_path(uuid4())
    with open_exclusive(staged) as handle:
        for chunk in uploaded.chunks():
            handle.write(chunk)
    return staged
