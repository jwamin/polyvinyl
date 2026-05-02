# SPDX-License-Identifier: MIT
"""Encode WAV segments with ffmpeg (FLAC, MP3, PCM WAV)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

ExportFormat = Literal["flac", "mp3", "wav"]

_VALID_FORMATS: frozenset[str] = frozenset({"flac", "mp3", "wav"})


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _codec_args(fmt: ExportFormat) -> list[str]:
    if fmt == "flac":
        return ["-c:a", "flac", "-compression_level", "8"]
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]
    if fmt == "wav":
        return ["-c:a", "pcm_s16le"]
    raise ValueError(f"Unknown format: {fmt!r}")


def encode_wav_segment(
    wav_path: str | Path,
    start_sec: float,
    end_sec: float,
    out_path: str | Path,
    *,
    format: ExportFormat = "flac",
    ffmpeg_bin: str | None = None,
) -> None:
    """Write ``[start_sec, end_sec)`` from ``wav_path`` using ffmpeg.

    Formats:

    - ``flac`` — lossless FLAC (compression level 8).
    - ``mp3`` — LAME VBR (~190 kbps equivalent at ``-q:a 2``); requires libmp3lame.
    - ``wav`` — 16-bit little-endian PCM WAV.
    """
    if format not in _VALID_FORMATS:
        raise ValueError(f"format must be one of {sorted(_VALID_FORMATS)}, got {format!r}")
    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")

    ffmpeg = ffmpeg_bin or find_ffmpeg()
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg not found in PATH")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(wav_path),
        "-ss",
        f"{start_sec:.6f}",
        "-to",
        f"{end_sec:.6f}",
        *_codec_args(format),
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"ffmpeg failed: {msg}")


def encode_wav_segment_flac(
    wav_path: str | Path,
    start_sec: float,
    end_sec: float,
    out_flac: str | Path,
    *,
    ffmpeg_bin: str | None = None,
) -> None:
    """Write ``[start_sec, end_sec)`` from ``wav_path`` to lossless FLAC."""
    encode_wav_segment(
        wav_path,
        start_sec,
        end_sec,
        out_flac,
        format="flac",
        ffmpeg_bin=ffmpeg_bin,
    )
