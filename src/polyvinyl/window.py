# MIT License
#
# Copyright (c) 2026 jwamin
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import threading
import wave
from datetime import datetime
from pathlib import Path

from gettext import gettext as _

from gi.repository import Adw, Gtk, Gio, GLib, Pango, PangoCairo

import cairo

from polyvinyl.core import (
    ExportFormat,
    ReleaseLookupError,
    TrackSpan,
    WavFileInfo,
    album_output_dir,
    compute_waveform_envelope,
    delete_track,
    detect_track_spans,
    encode_wav_segment,
    find_ffmpeg,
    insert_cut,
    internal_cut_times,
    lookup_track_titles,
    merge_with_next,
    normalize_spans,
    rms_window_series,
    set_span_range,
    suggest_silence_params,
    titles_for_span_count,
    track_filename,
    read_wav_file_info,
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
    analyze_waveform_button = Gtk.Template.Child()
    waveform_draw = Gtk.Template.Child()
    track_list_box = Gtk.Template.Child()
    track_list_empty_label = Gtk.Template.Child()
    open_wav_button = Gtk.Template.Child()
    open_output_button = Gtk.Template.Child()
    wav_info_button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._wav_path: Path | None = None
        self._output_root: Path | None = None
        self._spans: list[TrackSpan] = []
        self._titles: list[str] = []
        self._busy = False
        self._pulse_source: int | None = None
        self._duration_sec: float = 0.0
        self._envelope: list[float] = []
        self._updating_track_rows = False

        app = self.get_application()
        self._app_version = getattr(app, 'version', None) or '0.1.0'

        self.open_wav_button.connect('clicked', self._on_open_wav_clicked)
        self.wav_info_button.connect('clicked', self._on_wav_info_clicked)
        self.open_output_button.connect('clicked', self._on_open_output_clicked)
        self.lookup_button.connect('clicked', self._on_lookup_clicked)
        self.detect_button.connect('clicked', self._on_detect_clicked)
        self.split_button.connect('clicked', self._on_split_clicked)
        self.analyze_waveform_button.connect('clicked', self._on_analyze_waveform_clicked)

        self.waveform_draw.set_draw_func(self._draw_waveform, None)
        self.waveform_draw.set_can_focus(True)

        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect('pressed', self._on_waveform_pressed)
        self.waveform_draw.add_controller(click)

        if not find_ffmpeg():
            self._append_log(_('ffmpeg was not found in PATH; export will fail until it is installed.'))

        self._sync_track_empty_label()
        self._sync_wav_info_sensitive()

    def _sync_wav_info_sensitive(self) -> None:
        self.wav_info_button.set_sensitive(not self._busy and self._wav_path is not None)

    def _append_log(self, line: str) -> None:
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end, line + '\n')

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for w in (
            self.lookup_button,
            self.detect_button,
            self.split_button,
            self.analyze_waveform_button,
        ):
            w.set_sensitive(not busy)
        self._sync_wav_info_sensitive()
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

    def _probe_duration(self, path: Path) -> float:
        try:
            with wave.open(str(path), 'rb') as wf:
                return wf.getnframes() / float(wf.getframerate())
        except Exception:
            return 0.0

    def _on_open_wav_clicked(self, *_args):
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
            self._duration_sec = self._probe_duration(self._wav_path)
            self._envelope = []
            self._spans = []
            self._refresh_track_rows()
            self.waveform_draw.queue_draw()
            self._sync_wav_info_sensitive()
            self._append_log(_('Source: {path}').format(path=path))

    def _channel_summary_translated(self, info: WavFileInfo) -> str:
        if info.channels == 1:
            return _('Mono')
        if info.channels == 2:
            return _('Stereo')
        return _('{n} channels').format(n=info.channels)

    def _duration_summary_translated(self, seconds: float) -> str:
        if seconds < 60:
            return _('{sec:.2f} seconds').format(sec=seconds)
        minutes, sec = divmod(seconds, 60.0)
        if minutes < 60:
            return _('{min:.0f} min {sec:.1f} s').format(min=minutes, sec=sec)
        hours, minutes = divmod(minutes, 60.0)
        return _('{hr:.0f} h {min:.0f} min {sec:.1f} s').format(hr=hours, min=minutes, sec=sec)

    def _build_wav_info_text(self, info: WavFileInfo) -> str:
        lines: list[str] = []
        lines.append(_('File name: {name}').format(name=info.path.name))
        lines.append(_('Full path: {path}').format(path=str(info.path)))

        sz = info.file_size_bytes
        if sz >= 1024 * 1024:
            lines.append(
                _('Size on disk: {mb:.2f} MiB ({bytes:,} bytes)').format(mb=sz / (1024 * 1024), bytes=sz))
        else:
            lines.append(_('Size on disk: {kb:.1f} KiB ({bytes:,} bytes)').format(kb=sz / 1024, bytes=sz))

        if info.file_modified_timestamp is not None:
            dt = datetime.fromtimestamp(info.file_modified_timestamp)
            lines.append(_('Last modified: {when}').format(when=dt.strftime('%c')))

        lines.append(
            _('Channels: {n} ({layout})').format(
                n=info.channels,
                layout=self._channel_summary_translated(info),
            )
        )
        lines.append(_('Sample rate: {rate:,} Hz').format(rate=info.sample_rate_hz))
        lines.append(_('Bit depth: {bits} bit').format(bits=info.bits_per_sample))
        if info.compression_type == 'NONE':
            lines.append(_('Compression: PCM (uncompressed)'))
        else:
            lines.append(
                _('Compression: {kind} ({detail})').format(
                    kind=info.compression_type,
                    detail=info.compression_name,
                )
            )

        lines.append(
            _('Duration: {sec:.3f} s ({human})').format(
                sec=info.duration_sec,
                human=self._duration_summary_translated(info.duration_sec),
            )
        )

        kbps = info.pcm_bitrate_bps // 1000
        lines.append(
            _('PCM bitrate (calculated): {kbps} kb/s').format(kbps=kbps),
        )

        approx_pcm = info.frame_count * info.channels * info.sample_width_bytes
        lines.append(_('Audio payload (approx.): {bytes:,} bytes').format(bytes=approx_pcm))
        lines.append(_('Sample frames: {frames:,}').format(frames=info.frame_count))

        if info.compression_type != 'NONE':
            lines.append(_('Note: Only uncompressed PCM is fully supported for splitting.'))

        return '\n'.join(lines)

    def _on_wav_info_clicked(self, *_args) -> None:
        if not self._wav_path:
            return
        try:
            info = read_wav_file_info(self._wav_path)
        except wave.Error as e:
            self._append_log(_('Could not read WAV metadata: {err}').format(err=e))
            err_dlg = Adw.AlertDialog(
                heading=_('Invalid WAV'),
                body=_('This file could not be parsed as a WAV container.\n{err}').format(err=e),
            )
            err_dlg.add_response('close', _('_Close'))
            err_dlg.set_default_response('close')
            err_dlg.set_close_response('close')
            err_dlg.present(self)
            return
        except OSError as e:
            self._append_log(_('Could not read file: {err}').format(err=e))
            return

        detail = self._build_wav_info_text(info)
        label = Gtk.Label(label=detail, selectable=True, wrap=True, xalign=0)
        label.add_css_class('monospace')
        label.set_width_chars(52)

        dlg = Adw.AlertDialog(
            heading=_('Rip file information'),
            body=_('Details from the WAV header and file timestamps (select text to copy).'),
        )
        dlg.set_extra_child(label)
        dlg.add_response('close', _('_Close'))
        dlg.set_default_response('close')
        dlg.set_close_response('close')
        dlg.present(self)

    def _on_open_output_clicked(self, *_args):
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

    def _draw_waveform(self, area: Gtk.DrawingArea, cr: cairo.Context, width: int, height: int, _data) -> None:
        cr.save()
        cr.rectangle(0, 0, width, height)
        cr.set_source_rgba(0.12, 0.13, 0.15, 1.0)
        cr.fill()

        if width < 2 or height < 2:
            cr.restore()
            return

        if not self._envelope:
            layout = area.create_pango_layout(_('Run “Analyze waveform and suggest” after opening a WAV.'))
            layout.set_alignment(Pango.Alignment.CENTER)
            layout.set_width(width * Pango.SCALE)
            _lw, lh = layout.get_pixel_size()
            cr.set_source_rgba(0.55, 0.56, 0.58, 1.0)
            cr.move_to(0, max(0, (height - lh) / 2))
            PangoCairo.show_layout(cr, layout)
            cr.restore()
            return

        mid = height / 2.0
        scale = max(4.0, mid - 8.0)
        n = len(self._envelope)
        cr.set_source_rgba(0.42, 0.55, 0.78, 0.85)
        cr.move_to(0, mid)
        for i, v in enumerate(self._envelope):
            x = (i / max(1, n - 1)) * (width - 1)
            cr.line_to(x, mid - min(1.0, max(0.0, v)) * scale)
        cr.line_to(width - 1, mid)
        cr.close_path()
        cr.fill()

        if self._duration_sec > 0 and self._spans:
            cr.set_source_rgba(0.95, 0.65, 0.15, 0.95)
            cr.set_line_width(1.5)
            for t in internal_cut_times(self._spans):
                x = (t / self._duration_sec) * (width - 1)
                cr.move_to(x, 0)
                cr.line_to(x, height)
                cr.stroke()

        cr.restore()

    def _on_waveform_pressed(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        if n_press != 2:
            return
        if not self._wav_path or self._duration_sec <= 0:
            self._append_log(_('Open a WAV and run waveform analysis before adding cuts.'))
            return
        if not self._envelope:
            self._append_log(_('Run waveform analysis first so the timeline matches the file.'))
            return
        w = float(self.waveform_draw.get_width())
        if w <= 0:
            return
        t = max(0.0, min(self._duration_sec, (x / w) * self._duration_sec))
        if t <= 0.02 or t >= self._duration_sec - 0.02:
            return
        try:
            if not self._spans:
                self._spans = normalize_spans([TrackSpan(0.0, self._duration_sec)], self._duration_sec)
            self._spans = insert_cut(self._spans, t, self._duration_sec)
        except ValueError as e:
            self._append_log(_('Could not add cut: {err}').format(err=e))
            return
        self._refresh_track_rows()
        self.waveform_draw.queue_draw()
        self._append_log(_('Inserted boundary at {t:.2f}s').format(t=t))

    def _on_analyze_waveform_clicked(self, *_args):
        if self._busy or not self._wav_path:
            if not self._wav_path:
                self._append_log(_('Choose a WAV file first.'))
            return
        self._set_busy(True)
        path = str(self._wav_path)
        window_ms = 60.0

        def work():
            try:
                env, dur = compute_waveform_envelope(path, num_bins=2048)
                rms, _times, duration, _sr = rms_window_series(path, window_ms=window_ms)
                thr, min_s, note = suggest_silence_params(
                    rms,
                    window_sec=window_ms / 1000.0,
                    duration_sec=duration,
                )
                GLib.idle_add(self._analyze_done, env, dur, thr, min_s, note, None)
            except Exception as e:
                GLib.idle_add(self._analyze_done, None, 0.0, None, None, None, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _analyze_done(self, envelope, duration_sec, thr, min_s, note, err):
        self._set_busy(False)
        if err:
            self._append_log(_('Waveform analysis failed: {err}').format(err=err))
            return
        assert envelope is not None and thr is not None and min_s is not None
        self._envelope = envelope
        self._duration_sec = duration_sec
        self.silence_row.get_adjustment().set_value(
            max(self.silence_row.get_adjustment().get_lower(),
                min(self.silence_row.get_adjustment().get_upper(), thr)))
        self.min_silence_row.get_adjustment().set_value(
            max(self.min_silence_row.get_adjustment().get_lower(),
                min(self.min_silence_row.get_adjustment().get_upper(), min_s)))
        self.waveform_draw.queue_draw()
        self._append_log(_('Suggested silence RMS threshold: {t:.4f}').format(t=thr))
        self._append_log(_('Suggested minimum silence: {s:.2f}s').format(s=min_s))
        if note:
            self._append_log(note)

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
        if spans:
            d = spans[-1].end_sec
            if d > 0:
                self._duration_sec = d
                spans = normalize_spans(spans, d)
        self._spans = spans
        self._append_log(_('Detected {n} segments:').format(n=len(spans)))
        for i, s in enumerate(spans, start=1):
            self._append_log(f'  {i:02d}. {s.start_sec:.2f}s – {s.end_sec:.2f}s')
        self._refresh_track_rows()
        self.waveform_draw.queue_draw()

    def _sync_track_empty_label(self) -> None:
        self.track_list_empty_label.set_visible(len(self._spans) == 0)

    def _refresh_track_rows(self) -> None:
        while True:
            row = self.track_list_box.get_row_at_index(0)
            if row is None:
                break
            self.track_list_box.remove(row)

        if not self._spans:
            self._sync_track_empty_label()
            return

        self._updating_track_rows = True
        try:
            for i, span in enumerate(self._spans):
                self.track_list_box.append(self._make_track_row(i, span))
        finally:
            self._updating_track_rows = False
        self._sync_track_empty_label()

    def _make_track_row(self, index: int, span: TrackSpan) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        lbl = Gtk.Label(label=_('Track {n}').format(n=index + 1))
        lbl.set_xalign(0)
        lbl.set_width_chars(8)
        box.append(lbl)

        start_adj = Gtk.Adjustment(
            value=span.start_sec,
            lower=0.0,
            upper=max(0.01, self._duration_sec or span.end_sec),
            step_increment=0.1,
            page_increment=1.0,
            page_size=0.0,
        )
        start_spin = Gtk.SpinButton(adjustment=start_adj, climb_rate=0.5, digits=2)
        start_spin.set_tooltip_text(_('Start time (seconds)'))
        start_spin.set_width_chars(8)

        end_adj = Gtk.Adjustment(
            value=span.end_sec,
            lower=0.01,
            upper=max(0.02, self._duration_sec or span.end_sec + 1),
            step_increment=0.1,
            page_increment=1.0,
            page_size=0.0,
        )
        end_spin = Gtk.SpinButton(adjustment=end_adj, climb_rate=0.5, digits=2)
        end_spin.set_tooltip_text(_('End time (seconds)'))
        end_spin.set_width_chars(8)

        def on_times_changed(*_args):
            if self._updating_track_rows:
                return
            try:
                self._spans = set_span_range(
                    self._spans,
                    index,
                    start_adj.get_value(),
                    end_adj.get_value(),
                    self._duration_sec or end_adj.get_value(),
                )
            except ValueError:
                self._updating_track_rows = True
                try:
                    cur = self._spans[index] if index < len(self._spans) else span
                    start_adj.set_value(cur.start_sec)
                    end_adj.set_value(cur.end_sec)
                finally:
                    self._updating_track_rows = False
                return
            self._refresh_track_rows()
            self.waveform_draw.queue_draw()

        start_adj.connect('value-changed', on_times_changed)
        end_adj.connect('value-changed', on_times_changed)

        box.append(Gtk.Label(label=_('Start')))
        box.append(start_spin)
        box.append(Gtk.Label(label=_('End')))
        box.append(end_spin)

        if index < len(self._spans) - 1:
            merge_btn = Gtk.Button()
            merge_btn.set_tooltip_text(_('Merge this track with the next'))
            merge_btn.set_icon_name('go-next-symbolic')
            merge_btn.connect('clicked', lambda *_i: self._on_merge_next(index))
            box.append(merge_btn)

        if len(self._spans) > 1:
            del_btn = Gtk.Button()
            del_btn.set_tooltip_text(_('Remove track (merge with neighbour)'))
            del_btn.set_icon_name('list-remove-symbolic')
            del_btn.connect('clicked', lambda *_i: self._on_delete_track(index))
            box.append(del_btn)

        row.set_child(box)
        return row

    def _on_merge_next(self, index: int) -> None:
        if self._duration_sec <= 0:
            return
        try:
            self._spans = merge_with_next(self._spans, index, self._duration_sec)
        except IndexError:
            return
        self._refresh_track_rows()
        self.waveform_draw.queue_draw()
        self._append_log(_('Merged track {n} with next.').format(n=index + 1))

    def _on_delete_track(self, index: int) -> None:
        if self._duration_sec <= 0:
            return
        try:
            self._spans = delete_track(self._spans, index, self._duration_sec)
        except IndexError:
            return
        self._refresh_track_rows()
        self.waveform_draw.queue_draw()
        self._append_log(_('Removed track {n}.').format(n=index + 1))

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
            self._append_log(_('Define tracks (detect silence or edit boundaries) before export.'))
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
