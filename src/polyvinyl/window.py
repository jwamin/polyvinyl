# MIT License
#
# Copyright (c) 2026 jwamin
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import threading
from pathlib import Path

from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from polyvinyl.core import (
    ExportFormat,
    ReleaseLookupError,
    TrackSpan,
    album_output_dir,
    detect_track_spans,
    encode_wav_segment,
    find_ffmpeg,
    lookup_track_titles,
    titles_for_span_count,
    track_filename,
)


def _ua(version: str) -> str:
    return f'Polyvinyl/{version} (+https://musicbrainz.org/doc/MusicBrainz_API)'


@Gtk.Template(resource_path='/org/jossy/gnome/polyvinyl/window.ui')
class PolyvinylWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'PolyvinylWindow'

    wav_label = Gtk.Template.Child()
    output_label = Gtk.Template.Child()
    artist_row = Gtk.Template.Child()
    album_row = Gtk.Template.Child()
    silence_row = Gtk.Template.Child()
    min_silence_row = Gtk.Template.Child()
    log_buffer = Gtk.Template.Child()
    progress_bar = Gtk.Template.Child()
    lookup_button = Gtk.Template.Child()
    detect_button = Gtk.Template.Child()
    split_button = Gtk.Template.Child()
    export_flac_row = Gtk.Template.Child()
    export_mp3_row = Gtk.Template.Child()
    export_wav_row = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._wav_path: Path | None = None
        self._output_root: Path | None = None
        self._spans: list[TrackSpan] = []
        self._titles: list[str] = []
        self._busy = False
        self._pulse_source: int | None = None

        app = self.get_application()
        self._app_version = getattr(app, 'version', None) or '0.1.0'

        self.lookup_button.connect('clicked', self._on_lookup_clicked)
        self.detect_button.connect('clicked', self._on_detect_clicked)
        self.split_button.connect('clicked', self._on_split_clicked)

        if not find_ffmpeg():
            self._append_log(_('ffmpeg was not found in PATH; export will fail until it is installed.'))

    def _append_log(self, line: str) -> None:
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end, line + '\n')

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for w in (self.lookup_button, self.detect_button, self.split_button):
            w.set_sensitive(not busy)
        self.progress_bar.set_visible(busy)
        if busy:
            self.progress_bar.pulse()
            if self._pulse_source is None:
                self._pulse_source = GLib.timeout_add(80, self._on_pulse_timeout)
        else:
            if self._pulse_source is not None:
                GLib.source_remove(self._pulse_source)
                self._pulse_source = None
            self.progress_bar.set_fraction(0.0)

    def _on_pulse_timeout(self) -> bool:
        if not self._busy:
            self._pulse_source = None
            return GLib.SOURCE_REMOVE
        self.progress_bar.pulse()
        return GLib.SOURCE_CONTINUE

    @Gtk.Template.Callback()
    def on_open_wav_clicked(self, *_args):
        dialog = Gtk.FileDialog(title=_('Open WAV rip'))
        filt = Gtk.FileFilter()
        filt.set_name(_('WAV audio'))
        filt.add_mime_type('audio/wav')
        filt.add_mime_type('audio/x-wav')
        filt.add_pattern('*.wav')
        dialog.set_default_filter(filt)
        dialog.open(self, None, self._wav_open_cb)

    def _wav_open_cb(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        path = file.get_path()
        if path:
            self._wav_path = Path(path)
            self.wav_label.set_label(self._wav_path.name)
            self._append_log(_('Source: {path}').format(path=path))

    @Gtk.Template.Callback()
    def on_open_output_clicked(self, *_args):
        dialog = Gtk.FileDialog(title=_('Output folder'))
        dialog.select_folder(self, None, self._folder_cb)

    def _folder_cb(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        path = file.get_path()
        if path:
            self._output_root = Path(path)
            self.output_label.set_label(path)
            self._append_log(_('Output root: {path}').format(path=path))

    def _on_lookup_clicked(self, *_args):
        if self._busy:
            return
        artist = self.artist_row.get_text().strip()
        album = self.album_row.get_text().strip()
        if not artist and not album:
            self._append_log(_('Enter an artist and/or album to look up.'))
            return

        self._set_busy(True)
        version = self._app_version

        def work():
            try:
                a, rel, titles = lookup_track_titles(
                    artist=artist or None,
                    album=album or None,
                    user_agent=_ua(version),
                )
                GLib.idle_add(self._lookup_done, a, rel, titles, None)
            except ReleaseLookupError as e:
                GLib.idle_add(self._lookup_done, None, None, None, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _lookup_done(self, artist_line, release_title, titles, err):
        self._set_busy(False)
        if err:
            self._append_log(_('Lookup failed: {err}').format(err=err))
            return
        self._titles = list(titles)
        self.artist_row.set_text(artist_line)
        self.album_row.set_text(release_title)
        self._append_log(_('Loaded {n} track titles from MusicBrainz.').format(n=len(self._titles)))
        for i, t in enumerate(self._titles, start=1):
            self._append_log(f'  {i:02d}. {t}')

    def _export_formats(self) -> list[ExportFormat]:
        fmts: list[ExportFormat] = []
        if self.export_flac_row.get_active():
            fmts.append('flac')
        if self.export_mp3_row.get_active():
            fmts.append('mp3')
        if self.export_wav_row.get_active():
            fmts.append('wav')
        return fmts

    def _silence_params(self) -> tuple[float, float]:
        threshold = float(self.silence_row.get_adjustment().get_value())
        min_sec = float(self.min_silence_row.get_adjustment().get_value())
        return threshold, min_sec

    def _on_detect_clicked(self, *_args):
        if self._busy or not self._wav_path:
            if not self._wav_path:
                self._append_log(_('Choose a WAV file first.'))
            return
        self._set_busy(True)
        wav = str(self._wav_path)
        thr, min_sec = self._silence_params()

        def work():
            try:
                spans = detect_track_spans(
                    wav,
                    silence_threshold_linear=thr,
                    min_silence_sec=min_sec,
                )
                GLib.idle_add(self._detect_done, spans, None)
            except Exception as e:
                GLib.idle_add(self._detect_done, None, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _detect_done(self, spans, err):
        self._set_busy(False)
        if err:
            self._append_log(_('Detection failed: {err}').format(err=err))
            return
        assert spans is not None
        self._spans = spans
        self._append_log(_('Detected {n} segments:').format(n=len(spans)))
        for i, s in enumerate(spans, start=1):
            self._append_log(f'  {i:02d}. {s.start_sec:.2f}s – {s.end_sec:.2f}s')

    def _on_split_clicked(self, *_args):
        if self._busy:
            return
        if not self._wav_path:
            self._append_log(_('Choose a WAV file first.'))
            return
        if not self._output_root:
            self._append_log(_('Choose an output folder first.'))
            return
        if not self._spans:
            self._append_log(_('Run track detection first.'))
            return

        formats = self._export_formats()
        if not formats:
            self._append_log(_('Enable at least one export format (FLAC, MP3, or WAV).'))
            return

        ff = find_ffmpeg()
        if not ff:
            self._append_log(_('ffmpeg not found; cannot export audio.'))
            return

        artist = self.artist_row.get_text().strip() or _('Unknown Artist')
        album = self.album_row.get_text().strip() or _('Unknown Album')
        names = titles_for_span_count(self._titles, len(self._spans))
        out_dir = album_output_dir(self._output_root, artist, album)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._append_log(_('Writing under {path}').format(path=out_dir))

        self._set_busy(True)
        wav = str(self._wav_path)
        spans = list(self._spans)

        def work():
            try:
                for i, span in enumerate(spans):
                    for fmt in formats:
                        name = track_filename(i + 1, names[i], extension=fmt)
                        target = out_dir / name
                        encode_wav_segment(
                            wav,
                            span.start_sec,
                            span.end_sec,
                            target,
                            format=fmt,
                            ffmpeg_bin=ff,
                        )
                        GLib.idle_add(self._append_log, _('  wrote {name}').format(name=name))
                GLib.idle_add(self._split_done, None)
            except Exception as e:
                GLib.idle_add(self._split_done, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _split_done(self, err: str | None):
        self._set_busy(False)
        if err:
            self._append_log(_('Export failed: {err}').format(err=err))
        else:
            self._append_log(_('Done.'))
