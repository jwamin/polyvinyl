# SPDX-License-Identifier: MIT
"""Filesystem-safe names and album folder layout."""

from __future__ import annotations

import re
from pathlib import Path


_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_path_component(name: str, *, max_length: int = 120) -> str:
    """Strip characters unsafe on common filesystems and trim whitespace."""
    s = _INVALID_FS.sub("", name).strip()
    s = re.sub(r"\s+", " ", s)
    if not s:
        s = "Unknown"
    return s[:max_length].rstrip()


def album_output_dir(base_dir: str | Path, artist: str, album: str) -> Path:
    """``base_dir / Artist / Album``."""
    root = Path(base_dir)
    return root / sanitize_path_component(artist) / sanitize_path_component(album)


def track_filename(index: int, title: str, *, extension: str = "flac") -> str:
    """``02 – Song Name.<ext>`` (1-based index). ``extension`` without a leading dot."""
    safe = sanitize_path_component(title, max_length=180)
    ext = extension.lstrip(".").lower()
    if not ext:
        ext = "flac"
    return f"{index:02d} – {safe}.{ext}"
