"""Upload validation helpers — format detection (PDF + DOCX magic headers).

Per feature 003 research R-006: validate magic headers at the route
boundary before any database mutation.

Supports:
- PDF: "%PDF-" at byte 0
- DOCX: "PK\x03\x04" (ZIP magic, since .docx is a ZIP archive)

The cancellation signal :class:`rag.ingest.pipeline.UploadCancelledError`
is defined on the ingest side; UI code imports it from there.
"""

from __future__ import annotations

from fastapi import UploadFile

_PDF_MAGIC = b"%PDF-"
_PDF_MAGIC_LEN = 5

_DOCX_MAGIC = b"PK\x03\x04"
_DOCX_MAGIC_LEN = 4

_VALID_MAGICS: dict[str, tuple[bytes, int]] = {
    ".pdf": (_PDF_MAGIC, _PDF_MAGIC_LEN),
    ".docx": (_DOCX_MAGIC, _DOCX_MAGIC_LEN),
}


class InvalidFileError(Exception):
    """Raised when an upload fails magic-header validation.

    Carries an attribute ``observed`` with the (truncated, repr'd) first
    bytes of the upload so log records and error messages can name what
    was actually seen — useful when a renamed file reaches the route.
    """

    def __init__(self, observed: bytes, expected: str) -> None:
        self.observed = observed
        self.expected = expected
        super().__init__(
            f"upload does not start with expected magic header for {expected}; "
            f"observed first bytes: {observed!r}"
        )


async def validate_file_magic(upload: UploadFile) -> str:
    """Verify the upload matches a known format by magic bytes.

    Detects the format from the upload's filename extension, then reads
    the magic bytes to confirm. Returns the detected format extension
    (".pdf" or ".docx").

    Reads the required bytes from the upload's buffer, then rewinds
    via ``seek(0)`` so the full upload remains available for downstream
    processing. Raises :class:`InvalidFileError` if no magic matches.
    """
    filename = (upload.filename or "").lower()

    # Try filename-extension-based matching first
    suffix = ""
    if filename.endswith(".pdf"):
        suffix = ".pdf"
    elif filename.endswith(".docx"):
        suffix = ".docx"

    if suffix not in _VALID_MAGICS:
        raise InvalidFileError(
            observed=b"<unknown>",
            expected=".pdf or .docx",
        )

    magic, magic_len = _VALID_MAGICS[suffix]
    header = await upload.read(magic_len)
    await upload.seek(0)

    if header != magic:
        raise InvalidFileError(observed=header, expected=suffix)

    return suffix


# Alias for backward compat with existing test files
async def validate_pdf_magic(upload: UploadFile) -> None:
    """Legacy: verify PDF magic only. Use validate_file_magic for multi-format."""
    result = await validate_file_magic(upload)
    if result != ".pdf":
        raise InvalidFileError(
            observed=b"<unknown>",
            expected=".pdf",
        )