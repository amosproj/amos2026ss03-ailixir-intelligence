from __future__ import annotations

import re
from pathlib import Path

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

_MIME_BY_SUFFIX: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def infer_mime_type(image_path: Path) -> str:
    return _MIME_BY_SUFFIX.get(image_path.suffix.lower(), "application/octet-stream")


def image_sort_key(p: Path) -> tuple[int, str]:
    """Sort e.g. 'image (0).jpg', 'image (1).jpg' by the number in parentheses."""
    m = re.search(r"\((\d+)\)", p.stem)
    idx = int(m.group(1)) if m else 10**9
    return (idx, p.name.lower())
