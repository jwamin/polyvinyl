# SPDX-License-Identifier: MIT
"""Reusable vinyl-sidecar utilities: silence-based splitting, MusicBrainz lookup, audio export.

This package is intentionally free of GTK imports so it can be reused from CLI tools,
tests, or ports to other languages via the same algorithms.
"""

from .export import ExportFormat, encode_wav_segment, encode_wav_segment_flac, find_ffmpeg
from .musicbrainz import ReleaseLookupError, lookup_track_titles, titles_for_span_count
from .naming import album_output_dir, sanitize_path_component, track_filename
from .silence import TrackSpan, detect_track_spans

__all__ = [
    "TrackSpan",
    "detect_track_spans",
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
]
