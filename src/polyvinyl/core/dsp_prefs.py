# SPDX-License-Identifier: MIT
"""Which implementation runs waveform / silence DSP (Python vs native C)."""

from __future__ import annotations

import os
from typing import Literal

BackendMode = Literal['auto', 'python', 'native']

_SCHEMA_ID = 'org.jossy.gnome.polyvinyl'
_KEY = 'dsp-backend'
_VALID: frozenset[str] = frozenset({'auto', 'python', 'native'})


def _from_gsettings() -> str | None:
    try:
        from gi.repository import Gio

        s = Gio.Settings.new(_SCHEMA_ID)
        v = s.get_string(_KEY)
        return v if v in _VALID else 'auto'
    except Exception:
        return None


def configured_backend() -> BackendMode:
    """User preference: GSettings when available, else POLYVINYL_DSP_BACKEND, else auto."""
    g = _from_gsettings()
    if g is not None:
        return g  # type: ignore[return-value]
    env = os.environ.get('POLYVINYL_DSP_BACKEND', 'auto').lower().strip()
    if env in _VALID:
        return env  # type: ignore[return-value]
    return 'auto'


def resolve_dsp_backend(
    requested: BackendMode | str | None,
    *,
    native_available: bool,
) -> Literal['python', 'native']:
    """Map auto / explicit choice to an implementation key."""
    base = requested if requested is not None else configured_backend()
    if isinstance(base, str):
        b = base.lower().strip()
    else:
        b = str(base)
    if b not in _VALID:
        b = 'auto'
    if b == 'python':
        return 'python'
    if b == 'native':
        return 'native' if native_available else 'python'
    return 'native' if native_available else 'python'
