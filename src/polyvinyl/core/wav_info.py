# SPDX-License-Identifier: MIT
"""Inspect PCM WAV files for duration, channels, bitrate, and filesystem facts."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WavFileInfo:
    """Structured metadata for a RIFF WAVE file opened with :mod:`wave`."""

    path: Path
    file_size_bytes: int
    file_modified_timestamp: float | None
    channels: int
    sample_rate_hz: int
    sample_width_bytes: int
    frame_count: int
    compression_type: str
    compression_name: str

    @property
    def duration_sec(self) -> float:
        if self.sample_rate_hz <= 0:
            return 0.0
        return self.frame_count / float(self.sample_rate_hz)

    @property
    def bits_per_sample(self) -> int:
        return self.sample_width_bytes * 8

    @property
    def pcm_bitrate_bps(self) -> int:
        """Uncompressed PCM bitrate (bits per second)."""
        return self.sample_rate_hz * self.channels * self.bits_per_sample

    def channel_description(self) -> str:
        if self.channels == 1:
            return "mono"
        if self.channels == 2:
            return "stereo"
        return f"{self.channels} channels"


def read_wav_file_info(path: str | Path) -> WavFileInfo:
    """Read WAV parameters and basic filesystem stats.

    Raises :exc:`wave.Error` or :exc:`OSError` if the file is missing or not a WAV
    container the stdlib can parse.
    """
    p = Path(path)
    st = p.stat()
    with wave.open(str(p), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        nframes = wf.getnframes()
        comptype = wf.getcomptype()
        compname = wf.getcompname()

    return WavFileInfo(
        path=p.resolve(),
        file_size_bytes=st.st_size,
        file_modified_timestamp=st.st_mtime,
        channels=channels,
        sample_rate_hz=rate,
        sample_width_bytes=sampwidth,
        frame_count=nframes,
        compression_type=comptype,
        compression_name=compname or comptype,
    )
