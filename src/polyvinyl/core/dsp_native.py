# SPDX-License-Identifier: MIT
"""ctypes wrapper for libpolyvinyl_dsp (installed next to this package)."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


class PvDspRmsResult(ctypes.Structure):
    _fields_ = [
        ('rms', ctypes.POINTER(ctypes.c_double)),
        ('times_center', ctypes.POINTER(ctypes.c_double)),
        ('n', ctypes.c_size_t),
        ('duration_sec', ctypes.c_double),
        ('sample_rate', ctypes.c_int),
        ('error', ctypes.c_char_p),
    ]


class PvDspEnvResult(ctypes.Structure):
    _fields_ = [
        ('envelope', ctypes.POINTER(ctypes.c_double)),
        ('n_bins', ctypes.c_size_t),
        ('duration_sec', ctypes.c_double),
        ('error', ctypes.c_char_p),
    ]


_lib: ctypes.CDLL | None = None
_load_failed = False
_load_error: str | None = None


def _lib_names() -> tuple[str, ...]:
    if sys.platform == 'win32':
        return ('polyvinyl_dsp.dll',)
    if sys.platform == 'darwin':
        return ('libpolyvinyl_dsp.dylib',)
    return ('libpolyvinyl_dsp.so',)


def _candidate_paths() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get('POLYVINYL_DSP_LIB')
    if env:
        out.append(Path(env))
    core = Path(__file__).resolve().parent
    for n in _lib_names():
        out.append(core / n)
    if sys.platform == 'darwin':
        out.append(core / 'PolyvinylDSP.framework' / 'PolyvinylDSP')
    # Meson build tree: …/build/src/dsp/
    root = os.environ.get('MESON_BUILD_ROOT')
    if root:
        for n in _lib_names():
            out.append(Path(root) / 'src' / 'dsp' / n)
        if sys.platform == 'darwin':
            out.append(Path(root) / 'src' / 'dsp' / 'PolyvinylDSP.framework' / 'PolyvinylDSP')
    dev_dsp = core.parents[2] / 'dsp'
    for n in _lib_names():
        out.append(dev_dsp / n)
    if sys.platform == 'darwin':
        cb = os.environ.get('POLYVINYL_DSP_CMAKE_BUILD', str(dev_dsp / 'build-cmake'))
        out.append(Path(cb) / 'PolyvinylDSP.framework' / 'PolyvinylDSP')
    return out


def _load() -> ctypes.CDLL | None:
    global _lib, _load_failed, _load_error
    if _load_failed:
        return None
    if _lib is not None:
        return _lib
    for p in _candidate_paths():
        if not p.is_file():
            continue
        try:
            lib = ctypes.CDLL(str(p))
        except OSError as e:
            _load_error = str(e)
            continue
        lib.pv_dsp_rms_window_series.argtypes = [
            ctypes.c_char_p,
            ctypes.c_double,
            ctypes.POINTER(PvDspRmsResult),
        ]
        lib.pv_dsp_rms_window_series.restype = ctypes.c_int
        lib.pv_dsp_free_rms_result.argtypes = [ctypes.POINTER(PvDspRmsResult)]
        lib.pv_dsp_free_rms_result.restype = None
        lib.pv_dsp_waveform_envelope.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.POINTER(PvDspEnvResult),
        ]
        lib.pv_dsp_waveform_envelope.restype = ctypes.c_int
        lib.pv_dsp_free_env_result.argtypes = [ctypes.POINTER(PvDspEnvResult)]
        lib.pv_dsp_free_env_result.restype = None
        _lib = lib
        _load_error = None
        return lib
    _load_failed = True
    return None


def is_available() -> bool:
    return _load() is not None


def last_load_error() -> str | None:
    _load()
    return _load_error


def rms_window_series_native(wav_path: str, *, window_ms: float) -> tuple[list[float], list[float], float, int]:
    lib = _load()
    if lib is None:
        raise OSError(_load_error or 'libpolyvinyl_dsp not found')
    out = PvDspRmsResult()
    rc = lib.pv_dsp_rms_window_series(wav_path.encode('utf-8'), float(window_ms), ctypes.byref(out))
    try:
        if rc != 0 or out.error:
            msg = out.error.decode('utf-8', errors='replace') if out.error else 'rms_window_series failed'
            raise RuntimeError(msg)
        n = int(out.n)
        rms = [float(out.rms[i]) for i in range(n)] if out.rms and n else []
        times = [float(out.times_center[i]) for i in range(n)] if out.times_center and n else []
        return rms, times, float(out.duration_sec), int(out.sample_rate)
    finally:
        lib.pv_dsp_free_rms_result(ctypes.byref(out))


def compute_waveform_envelope_native(wav_path: str, *, num_bins: int) -> tuple[list[float], float]:
    lib = _load()
    if lib is None:
        raise OSError(_load_error or 'libpolyvinyl_dsp not found')
    out = PvDspEnvResult()
    rc = lib.pv_dsp_waveform_envelope(wav_path.encode('utf-8'), int(num_bins), ctypes.byref(out))
    try:
        if rc != 0 or out.error:
            msg = out.error.decode('utf-8', errors='replace') if out.error else 'waveform_envelope failed'
            raise RuntimeError(msg)
        nb = int(out.n_bins)
        env = [float(out.envelope[i]) for i in range(nb)] if out.envelope and nb else []
        return env, float(out.duration_sec)
    finally:
        lib.pv_dsp_free_env_result(ctypes.byref(out))
