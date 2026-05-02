# SPDX-License-Identifier: MIT
"""Preview the selected track from a WAV file (GStreamer, or ffplay fallback)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from gi.repository import GLib

_GST = None
_GST_FAILED = False


def gst_available() -> bool:
    global _GST, _GST_FAILED
    if _GST_FAILED:
        return False
    if _GST is not None:
        return True
    try:
        import gi

        gi.require_version('Gst', '1.0')
        from gi.repository import Gst

        Gst.init(None)
        _GST = Gst
        return True
    except Exception:
        _GST_FAILED = True
        return False


class WavPreviewPlayer:
    """Play ``[start_sec, end_sec)`` of a WAV. Pause/resume only when using GStreamer."""

    def __init__(self, on_stopped: object | None = None) -> None:
        self._on_stopped = on_stopped
        self._pipe = None
        self._tick_id: int | None = None
        self._end_ns = 0
        self._ffproc: subprocess.Popen | None = None
        self._mode: str | None = None

    def _emit_stopped(self) -> None:
        if self._on_stopped is not None:
            self._on_stopped()

    def stop(self) -> None:
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
        if self._pipe is not None and _GST is not None:
            self._pipe.set_state(_GST.State.NULL)
            self._pipe = None
        if self._ffproc is not None:
            try:
                self._ffproc.terminate()
            except Exception:
                pass
            self._ffproc = None
        had = self._mode is not None
        self._mode = None
        if had:
            self._emit_stopped()

    def pause(self) -> None:
        if self._pipe is not None and _GST is not None:
            self._pipe.set_state(_GST.State.PAUSED)

    def resume(self) -> None:
        if self._pipe is not None and _GST is not None:
            self._pipe.set_state(_GST.State.PLAYING)

    def is_gst_paused(self) -> bool:
        if self._pipe is None or _GST is None:
            return False
        Gst = _GST
        ret, st, _pending = self._pipe.get_state(0)
        if ret == Gst.StateChangeReturn.FAILURE:
            return False
        return st == Gst.State.PAUSED

    def can_pause(self) -> bool:
        return self._mode == 'gst' and self._pipe is not None

    def is_active(self) -> bool:
        if self._pipe is not None:
            return True
        if self._ffproc is not None and self._ffproc.poll() is None:
            return True
        return False

    def play(self, wav_path: Path, start_sec: float, end_sec: float) -> bool:
        self.stop()
        start_sec = max(0.0, float(start_sec))
        end_sec = max(start_sec + 0.05, float(end_sec))

        if gst_available():
            if self._play_gst(wav_path, start_sec, end_sec):
                return True
        ffplay = shutil.which('ffplay')
        if ffplay:
            return self._play_ffplay(ffplay, wav_path, start_sec, end_sec)
        return False

    def _play_ffplay(self, ffplay: str, path: Path, start: float, end: float) -> bool:
        dur = end - start
        cmd = [
            ffplay,
            '-nodisp',
            '-autoexit',
            '-loglevel',
            'quiet',
            '-ss',
            str(start),
            '-t',
            str(dur),
            str(path),
        ]
        try:
            self._ffproc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self._ffproc = None
            return False
        self._mode = 'ffplay'
        GLib.timeout_add(400, self._ffplay_watch)
        return True

    def _ffplay_watch(self) -> bool:
        if self._ffproc is None:
            return False
        code = self._ffproc.poll()
        if code is None:
            return True
        self._ffproc = None
        self._mode = None
        self._emit_stopped()
        return False

    def _play_gst(self, path: Path, start: float, end: float) -> bool:
        assert _GST is not None
        Gst = _GST
        uri = GLib.filename_to_uri(str(path.resolve()), None)
        pipe = Gst.ElementFactory.make('playbin', None)
        if pipe is None:
            return False
        pipe.set_property('uri', uri)
        self._end_ns = int(end * Gst.SECOND)
        ret = pipe.set_state(Gst.State.PAUSED)
        if ret == Gst.StateChangeReturn.FAILURE:
            pipe.set_state(Gst.State.NULL)
            return False
        pipe.get_state(Gst.CLOCK_TIME_NONE)
        if not pipe.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            int(start * Gst.SECOND),
        ):
            pipe.set_state(Gst.State.NULL)
            return False
        ret = pipe.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            pipe.set_state(Gst.State.NULL)
            return False
        self._pipe = pipe
        self._mode = 'gst'
        self._tick_id = GLib.timeout_add(120, self._gst_tick)
        return True

    def _gst_tick(self) -> bool:
        if self._pipe is None or _GST is None:
            self._tick_id = None
            return False
        ok, pos = self._pipe.query_position(_GST.Format.TIME)
        if ok and pos >= self._end_ns - 100_000_000:
            self.stop()
            return False
        return True
