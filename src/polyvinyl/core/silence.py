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


def _filter_split_centers_by_min_gap(
    centers: list[float],
    duration_sec: float,
    min_gap_sec: float,
) -> list[float]:
    """Drop suggested cut times so consecutive kept cuts are at least ``min_gap_sec`` apart,
    and the first / last resulting segments are at least ``min_gap_sec`` long.
    """
    if min_gap_sec <= 0 or not centers:
        return sorted(centers)
    centers = sorted(centers)
    out: list[float] = []
    last_boundary = 0.0
    for t in centers:
        if t - last_boundary < min_gap_sec:
            continue
        if duration_sec - t < min_gap_sec:
            continue
        out.append(t)
        last_boundary = t
    return out


def _rms_window_series_python(
    wav_path: str,
    *,
    window_ms: float = 60.0,
) -> tuple[list[float], list[float], float, int]:
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")

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

        rms_values: list[float] = []
        times_center: list[float] = []

        pos = 0
        while pos < nframes:
            take = min(window_frames, nframes - pos)
            raw = wf.readframes(take)
            pos += take
            rms = _rms_linear_mono(raw, sampwidth, nchannels)
            rms_values.append(rms)
            t_end = pos / framerate
            t_start = (pos - take) / framerate
            times_center.append((t_start + t_end) / 2.0)

        duration_sec = nframes / framerate
        return rms_values, times_center, duration_sec, framerate


def rms_window_series(
    wav_path: str,
    *,
    window_ms: float = 60.0,
    backend: str | None = None,
) -> tuple[list[float], list[float], float, int]:
    """Scan the WAV file and return RMS per analysis window.

    Returns ``(rms_linear_values, window_center_times_sec, duration_sec, frame_rate)``.

    ``backend`` may be ``'python'``, ``'native'``, ``'auto'``, or ``None`` (use settings / env).
    """
    from . import dsp_native
    from .dsp_prefs import resolve_dsp_backend

    use = resolve_dsp_backend(backend, native_available=dsp_native.is_available())
    if use == "native":
        return dsp_native.rms_window_series_native(wav_path, window_ms=window_ms)
    return _rms_window_series_python(wav_path, window_ms=window_ms)


def detect_track_spans(
    wav_path: str,
    *,
    silence_threshold_linear: float = 0.018,
    min_silence_sec: float = 1.35,
    min_split_gap_sec: float = 30.0,
    target_track_count: int | None = None,
    window_ms: float = 60.0,
    boundary_pad_sec: float = 0.05,
    backend: str | None = None,
) -> list[TrackSpan]:
    """Find cue points from long silence regions between tracks.

    ``silence_threshold_linear`` is RMS relative to full scale (roughly 0–1). Vinyl
    surface noise usually sits above true digital silence; increase this if splits
    are too aggressive, decrease if silence is not detected.

    ``min_silence_sec`` should exceed the longest intra-track pause but stay below
    typical groove gaps between LP sides or tracks (often 1–3 s).

    ``min_split_gap_sec`` enforces a minimum timeline distance between consecutive
    suggested cuts (and from file start / end), so silence within a song does not
    flood the marker list.

    If ``target_track_count`` is set (e.g. number of MusicBrainz titles), the
    result is adjusted to exactly that many tracks when possible by merging weak
    boundaries or splitting the longest segments.
    """
    if silence_threshold_linear <= 0:
        raise ValueError("silence_threshold_linear must be positive")
    if min_silence_sec <= 0:
        raise ValueError("min_silence_sec must be positive")
    if min_split_gap_sec < 0:
        raise ValueError("min_split_gap_sec must be non-negative")

    silent_flags: list[bool]
    times_center: list[float]
    duration_sec: float

    rms_values, times_center, duration_sec, framerate = rms_window_series(
        wav_path, window_ms=window_ms, backend=backend
    )
    silent_flags = [rms < silence_threshold_linear for rms in rms_values]
    nframes = int(round(duration_sec * framerate))

    if not silent_flags:
        return [TrackSpan(0.0, duration_sec)]

    window_sec = window_ms / 1000.0
    min_windows = max(1, int(math.ceil(min_silence_sec / window_sec)))
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

    split_centers = _filter_split_centers_by_min_gap(split_centers, duration_sec, min_split_gap_sec)

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

    if target_track_count is not None and target_track_count >= 1:
        from .segments import adjust_span_count_to_target

        spans = adjust_span_count_to_target(spans, target_track_count, duration_sec)

    return spans
