# SPDX-License-Identifier: MIT
"""Waveform envelope for visualization and silence-parameter suggestions from RMS."""

from __future__ import annotations

import math
import struct
import wave


def _compute_waveform_envelope_python(
    wav_path: str,
    *,
    num_bins: int = 2048,
) -> tuple[list[float], float]:
    if num_bins < 8:
        raise ValueError("num_bins too small")

    with wave.open(wav_path, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()

        if nchannels < 1 or framerate <= 0:
            raise ValueError("Invalid WAV parameters")
        if sampwidth not in (1, 2, 3, 4):
            raise ValueError(f"Unsupported WAV sample width: {sampwidth}")

        duration_sec = nframes / framerate
        frames_per_bin = max(1, nframes // num_bins)
        envelope = [0.0] * num_bins
        peak_scale = {1: 128.0, 2: 32768.0, 3: 8388608.0, 4: 2147483648.0}[sampwidth]

        bin_idx = 0
        frames_in_bin = 0
        pos = 0

        def frame_peak_abs(raw: bytes, offset: int) -> float:
            if sampwidth == 1:
                return max(abs(raw[offset + c] - 128) for c in range(nchannels)) / peak_scale
            if sampwidth == 2:
                return max(
                    abs(struct.unpack_from("<h", raw, offset + c * 2)[0]) for c in range(nchannels)
                ) / peak_scale
            if sampwidth == 3:
                m = 0.0
                for c in range(nchannels):
                    off = offset + c * 3
                    b0, b1, b2 = raw[off], raw[off + 1], raw[off + 2]
                    u = b0 | (b1 << 8) | (b2 << 16)
                    if u & 0x800000:
                        u -= 0x1000000
                    m = max(m, abs(float(u)))
                return m / peak_scale
            m = max(
                abs(float(struct.unpack_from("<i", raw, offset + c * 4)[0])) for c in range(nchannels)
            )
            return m / peak_scale

        frame_bytes = sampwidth * nchannels
        chunk_frames = max(frames_per_bin, 4096)

        while pos < nframes:
            take = min(chunk_frames, nframes - pos)
            raw = wf.readframes(take)
            for f in range(take):
                off = f * frame_bytes
                pk = frame_peak_abs(raw, off)
                envelope[bin_idx] = max(envelope[bin_idx], pk)
                frames_in_bin += 1
                pos += 1
                if frames_in_bin >= frames_per_bin and bin_idx < num_bins - 1:
                    frames_in_bin = 0
                    bin_idx += 1

        m = max(envelope) or 1e-12
        envelope = [min(1.0, v / m) for v in envelope]
        return envelope, duration_sec


def compute_waveform_envelope(
    wav_path: str,
    *,
    num_bins: int = 2048,
    backend: str | None = None,
) -> tuple[list[float], float]:
    """Peak envelope for drawing (one value per bin, normalized 0…1).

    Returns ``(envelope, duration_sec)``. Mono signal uses absolute sample peak per bin;
    multi-channel uses the max across channels per frame.

    ``backend`` may be ``'python'``, ``'native'``, ``'auto'``, or ``None`` (use settings / env).
    """
    from . import dsp_native
    from .dsp_prefs import resolve_dsp_backend

    use = resolve_dsp_backend(backend, native_available=dsp_native.is_available())
    if use == "native":
        return dsp_native.compute_waveform_envelope_native(wav_path, num_bins=num_bins)
    return _compute_waveform_envelope_python(wav_path, num_bins=num_bins)


def suggest_silence_params(
    rms_values: list[float],
    *,
    window_sec: float,
    duration_sec: float,
) -> tuple[float, float, str]:
    """Derive suggested threshold and minimum silence from an RMS profile.

    Uses a simple noise-vs-signal gap on sorted RMS, then measures silent-run
    lengths at the suggested threshold to pick a minimum silence duration.

    Returns ``(threshold_linear, min_silence_sec, explanation)``.
    """
    if not rms_values or window_sec <= 0 or duration_sec <= 0:
        return 0.018, 1.35, "Default suggestion (no analysis data)."

    xs = sorted(rms_values)
    n = len(xs)
    p10 = xs[max(0, int(0.10 * (n - 1)))]
    p45 = xs[max(0, int(0.45 * (n - 1)))]
    p85 = xs[max(0, int(0.85 * (n - 1)))]

    noise = max(p10, 1e-9)
    mid = max(p45, noise * 1.5)
    loud = max(p85, mid * 1.2)

    # Threshold between noise floor and typical "musical" RMS
    threshold = noise + 0.42 * (min(mid, loud) - noise)
    threshold = max(0.005, min(0.095, threshold))

    silent = [r < threshold for r in rms_values]
    runs_sec: list[float] = []
    i = 0
    while i < len(silent):
        if not silent[i]:
            i += 1
            continue
        j = i
        while j < len(silent) and silent[j]:
            j += 1
        runs_sec.append((j - i) * window_sec)
        i = j

    long_runs = [r for r in runs_sec if r >= 0.35]
    if len(long_runs) >= 3:
        long_runs.sort()
        pick = long_runs[len(long_runs) // 3]
        min_silence = max(0.45, min(3.0, pick * 0.92))
    elif long_runs:
        min_silence = max(0.45, min(3.0, sorted(long_runs)[len(long_runs) // 2] * 0.88))
    else:
        min_silence = 1.25

    min_silence = max(0.40, min(5.0, min_silence))
    note = (
        f"From RMS distribution (noise≈{noise:.4f}, loud≈{loud:.4f}); "
        f"{len(long_runs)} quiet runs ≥0.35s at trial threshold."
    )
    return threshold, min_silence, note
