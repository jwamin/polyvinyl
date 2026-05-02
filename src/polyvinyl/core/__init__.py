# SPDX-License-Identifier: MIT
"""Reusable vinyl-sidecar utilities: silence-based splitting, MusicBrainz lookup, audio export.

This package is intentionally free of GTK imports so it can be reused from CLI tools,
tests, or ports to other languages via the same algorithms.
"""

from .analysis import compute_waveform_envelope, suggest_silence_params
from .export import ExportFormat, encode_wav_segment, encode_wav_segment_flac, find_ffmpeg
from .musicbrainz import ReleaseLookupError, lookup_track_titles, titles_for_span_count
from .naming import album_output_dir, sanitize_path_component, track_filename
from .segments import (
    delete_track,
    insert_cut,
    internal_cut_times,
    merge_with_next,
    normalize_spans,
    set_span_range,
    split_span_at,
)
from .silence import TrackSpan, detect_track_spans, rms_window_series
from .wav_info import WavFileInfo, read_wav_file_info

__all__ = [
    "TrackSpan",
    "detect_track_spans",
    "rms_window_series",
    "compute_waveform_envelope",
    "suggest_silence_params",
    "lookup_track_titles",
    "titles_for_span_count",
    "ReleaseLookupError",
    "find_ffmpeg",
    "ExportFormat",
    "encode_wav_segment",
    "encode_wav_segment_flac",
    "sanitize_path_component",
    "album_output_dir",
    "track_filename",
    "normalize_spans",
    "internal_cut_times",
    "split_span_at",
    "merge_with_next",
    "delete_track",
    "insert_cut",
    "set_span_range",
    "WavFileInfo",
    "read_wav_file_info",
]
