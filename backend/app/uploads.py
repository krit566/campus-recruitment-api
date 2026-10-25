"""Resume uploads: PDF only, at most 2 MB, stored under UPLOAD_DIR with a name the server chooses.

Why each check exists:
- size is checked while reading (at most MAX_BYTES + 1 bytes are read), so a huge upload cannot fill memory;
- the type is checked from the file's first bytes (%PDF-), not only from the name or the browser's Content-Type,
  which the client controls;
- the stored file name is a random id, so a name like "../../app/main.py" cannot write outside the folder;
  the original name is kept only for display.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from .services import ApiError

MAX_BYTES = 2 * 1024 * 1024


def upload_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "uploads")).resolve()


def display_name(name: str | None) -> str:
    base = os.path.basename((name or "resume.pdf").replace("\\", "/"))
    base = re.sub(r"[^\w .()-]", "_", base).strip() or "resume.pdf"
    return base[:120]


async def save_resume(student_id: int, file: UploadFile) -> tuple[str, str]:
    """Validates and writes the file. Returns (stored path, display name)."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ApiError(413, "the resume must be at most 2 MB")
    if not data:
        raise ApiError(422, "the file is empty")
    if not data.startswith(b"%PDF-") or (file.content_type and file.content_type not in ("application/pdf", "application/octet-stream")):
        raise ApiError(415, "the resume must be a PDF file")
    folder = upload_dir() / "resumes" / str(student_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.pdf"
    path.write_bytes(data)
    return str(path), display_name(file.filename)


def remove_quietly(path: str | None) -> None:
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
