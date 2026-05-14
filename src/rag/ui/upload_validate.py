"""Upload validation helpers — PDF magic-header check.

Per feature 003 research R-006: validate the PDF magic header at the
route boundary before any database mutation. The exception lives here
rather than in ``rag.ingest`` because validation is a UI/route concern
that runs before any ingest work begins.

The cancellation signal :class:`rag.ingest.pipeline.UploadCancelledError`
is defined on the ingest side; UI code imports it from there.
"""

from __future__ import annotations

from fastapi import UploadFile

# Per ISO 32000-1 §7.5.2 the canonical PDF magic is the five bytes "%PDF-"
# at offset 0. Some non-conforming PDFs prefix this with whitespace or a
# BOM; for the demo's reviewer-supplied PDFs we reject those — strict
# magic-at-byte-0 keeps the validation cheap and the error message clear.
_PDF_MAGIC = b"%PDF-"
_PDF_MAGIC_LEN = len(_PDF_MAGIC)


class InvalidPDFError(Exception):
    """Raised when an upload fails PDF magic-header validation.

    Carries an attribute ``observed`` with the (truncated, repr'd) first
    bytes of the upload so log records and error messages can name what
    was actually seen — useful when a renamed non-PDF reaches the route.
    """

    def __init__(self, observed: bytes) -> None:
        self.observed = observed
        super().__init__(
            f"upload does not start with PDF magic header {_PDF_MAGIC!r}; "
            f"observed first bytes: {observed!r}"
        )


async def validate_pdf_magic(upload: UploadFile) -> None:
    """Verify the upload starts with the PDF magic header.

    Reads the first 5 bytes from the upload's spooled buffer, then
    rewinds via ``seek(0)`` so the full upload remains available for
    downstream processing. Raises :class:`InvalidPDFError` if the magic
    doesn't match.
    """
    header = await upload.read(_PDF_MAGIC_LEN)
    await upload.seek(0)
    if header != _PDF_MAGIC:
        raise InvalidPDFError(observed=header)
