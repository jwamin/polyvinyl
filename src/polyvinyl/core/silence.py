# SPDX-License-Identifier: MIT
"""Detect track boundaries in a WAV rip using sustained low-energy (silence) gaps."""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass


@dataclass(frozen=True)
class TrackSpan:
    """Half-open interval [start_sec, end_sec) in the source WAV."""

    start_sec: float
    end_sec: float


def _rms_linear_mono(block: bytes, sampwidth: int, nchannels: int) -> float:
    """Root mean square of interleaved PCM block, normalized to ~0..1."""
    if not block:
        return 0.0
    frame_bytes = sampwidth * nchannels
    nframes = len(block) // frame_bytes
    if nframes == 0:
        return 0.0

    acc = 0.0
    peak_scale = 1.0
    if sampwidth == 1:
        peak_scale = 128.0
        for f in range(nframes):
            base = f * frame_bytes
            for c in range(nchannels):
                v = block[base + c] - 128
                acc += v * v
    elif sampwidth == 2:
        peak_scale = 32768.0
        for f in range(nframes):
            base = f * frame_bytes
            for c in range(nchannels):
                v = struct.unpack_from("<h", block, base + c * 2)[0]
                acc += v * v
    elif sampwidth == 3:
        peak_scale = 8388608.0  # 2**23
        for f in range(nframes):
            base = f * frame_bytes
            for c in range(nchannels):
                off = base + c * 3
                b0, b1, b2 = block[off], block[off + 1], block[off + 2]
                u = b0 | (b1 << 8) | (b2 << 16)
                if u & 0x800000:
                    u -= 0x1000000
                acc += float(u) * float(u)
    elif sampwidth == 4:
        peak_scale = 2147483648.0
        for f in range(nframes):
            base = f * frame_bytes
            for c in range(nchannels):
                v = struct.unpack_from("<i", block, base + c * 4)[0]
                acc += float(v) * float(v)
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth} bytes")

    denom = nframes * nchannels
    return math.sqrt(acc / denom) / peak_scale


def detect_track_spans(
    wav_path: str,
    *,
    silence_threshold_linear: float = 0.018,
    min_silence_sec: float = 1.35,
    window_ms: float = 60.0,
    boundary_pad_sec: float = 0.05,
) -> list[TrackSpan]:
    """Find cue points from long silence regions between tracks.

    ``silence_threshold_linear`` is RMS relative to full scale (roughly 0–1). Vinyl
    surface noise usually sits above true digital silence; increase this if splits
    are too aggressive, decrease if silence is not detected.

    ``min_silence_sec`` should exceed the longest intra-track pause but stay below
    typical groove gaps between LP sides or tracks (often 1–3 s).
    """
    if silence_threshold_linear <= 0:
        raise ValueError("silence_threshold_linear must be positive")
    if min_silence_sec <= 0:
        raise ValueError("min_silence_sec must be positive")

    with wave.open(wav_path, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()

        if nchannels < 1 or framerate <= 0:
            raise ValueError("Invalid WAV parameters")
        if sampwidth not in (1, 2, 3, 4):
            raise ValueError(f"Unsupported WAV sample width: {sampwidth}")

        window_frames = max(1, int(framerate * window_ms / 1000.0))
        frame_bytes = sampwidth * nchannels

        silent_flags: list[bool] = []
        times_center: list[float] = []

        pos = 0
        while pos < nframes:
            take = min(window_frames, nframes - pos)
            raw = wf.readframes(take)
            pos += take
            rms = _rms_linear_mono(raw, sampwidth, nchannels)
            silent_flags.append(rms < silence_threshold_linear)
            # Window centers for boundary placement
            t_end = pos / framerate
            t_start = (pos - take) / framerate
            times_center.append((t_start + t_end) / 2.0)

    if not silent_flags:
        duration = nframes / framerate
        return [TrackSpan(0.0, duration)]

    # Long silent runs (indices into silent_flags)
    min_windows = max(1, int(math.ceil(min_silence_sec / (window_ms / 1000.0))))
    split_centers: list[float] = []
    i = 0
    nwin = len(silent_flags)
    while i < nwin:
        if not silent_flags[i]:
            i += 1
            continue
        j = i
        while j < nwin and silent_flags[j]:
            j += 1
        run_len = j - i
        if run_len >= min_windows:
            mid = i + run_len // 2
            split_centers.append(times_center[mid])
        i = j

    duration_sec = nframes / framerate
    boundaries = [0.0] + split_centers + [duration_sec]
    boundaries.sort()

    spans: list[TrackSpan] = []
    pad = max(0.0, boundary_pad_sec)
    for a, b in zip(boundaries, boundaries[1:]):
        start = min(duration_sec, max(0.0, a + pad))
        end = min(duration_sec, max(0.0, b - pad))
        if end - start > 0.05:
            spans.append(TrackSpan(start_sec=start, end_sec=end))

    if not spans:
        return [TrackSpan(0.0, duration_sec)]
    return spans
