# SPDX-License-Identifier: MIT
"""CRUD-style helpers for track spans (non-overlapping regions along a timeline)."""

from __future__ import annotations

from polyvinyl.core.silence import TrackSpan


def spans_cover_timeline(spans: list[TrackSpan], duration_sec: float, eps: float = 1e-6) -> bool:
    if not spans:
        return duration_sec <= eps
    if abs(spans[0].start_sec - 0.0) > eps:
        return False
    if abs(spans[-1].end_sec - duration_sec) > eps:
        return False
    for a, b in zip(spans, spans[1:]):
        if abs(a.end_sec - b.start_sec) > eps:
            return False
    return True


def normalize_spans(spans: list[TrackSpan], duration_sec: float, *, min_track_sec: float = 0.05) -> list[TrackSpan]:
    """Sort, clamp to ``[0, duration]``, merge overlaps, drop tiny segments."""
    if duration_sec <= 0:
        return []

    cleaned: list[TrackSpan] = []
    for s in sorted(spans, key=lambda x: (x.start_sec, x.end_sec)):
        start = max(0.0, min(duration_sec, s.start_sec))
        end = max(0.0, min(duration_sec, s.end_sec))
        if end - start >= min_track_sec:
            cleaned.append(TrackSpan(start_sec=start, end_sec=end))

    if not cleaned:
        return [TrackSpan(0.0, duration_sec)] if duration_sec > min_track_sec else []

    merged: list[TrackSpan] = [cleaned[0]]
    for s in cleaned[1:]:
        last = merged[-1]
        # Merge only true overlaps; preserve touching boundaries (adjacent tracks).
        if s.start_sec < last.end_sec - 1e-9:
            merged[-1] = TrackSpan(start_sec=last.start_sec, end_sec=max(last.end_sec, s.end_sec))
        else:
            merged.append(s)

    # Snap first/last to timeline ends if nearly flush
    if merged:
        merged[0] = TrackSpan(start_sec=0.0, end_sec=merged[0].end_sec)
        merged[-1] = TrackSpan(start_sec=merged[-1].start_sec, end_sec=duration_sec)

    return [s for s in merged if s.end_sec - s.start_sec >= min_track_sec]


def internal_cut_times(spans: list[TrackSpan]) -> list[float]:
    """Boundary times strictly inside the timeline (not 0 / duration)."""
    return [s.end_sec for s in spans[:-1]] if len(spans) > 1 else []


def split_span_at(spans: list[TrackSpan], index: int, split_sec: float, duration_sec: float) -> list[TrackSpan]:
    """Split span ``index`` at ``split_sec``. Returns normalized spans."""
    if not (0 <= index < len(spans)):
        raise IndexError('track index out of range')
    s = spans[index]
    if not (s.start_sec < split_sec < s.end_sec):
        raise ValueError('split time must lie strictly inside the track')
    new = list(spans)
    new[index : index + 1] = [
        TrackSpan(start_sec=s.start_sec, end_sec=split_sec),
        TrackSpan(start_sec=split_sec, end_sec=s.end_sec),
    ]
    return normalize_spans(new, duration_sec)


def merge_with_next(spans: list[TrackSpan], index: int, duration_sec: float) -> list[TrackSpan]:
    """Merge track ``index`` with track ``index + 1``."""
    if index < 0 or index >= len(spans) - 1:
        raise IndexError('cannot merge: invalid index')
    a, b = spans[index], spans[index + 1]
    new = list(spans)
    new[index : index + 2] = [TrackSpan(start_sec=a.start_sec, end_sec=b.end_sec)]
    return normalize_spans(new, duration_sec)


def merge_with_previous(spans: list[TrackSpan], index: int, duration_sec: float) -> list[TrackSpan]:
    """Merge track ``index`` with track ``index - 1``."""
    if index <= 0 or index >= len(spans):
        raise IndexError('cannot merge: invalid index')
    return merge_with_next(spans, index - 1, duration_sec)


def delete_track(spans: list[TrackSpan], index: int, duration_sec: float) -> list[TrackSpan]:
    """Remove a track by merging it with the next neighbour, or previous if it is the last."""
    if len(spans) <= 1:
        return list(spans)
    if index < 0 or index >= len(spans):
        raise IndexError('track index out of range')
    if index < len(spans) - 1:
        return merge_with_next(spans, index, duration_sec)
    return merge_with_previous(spans, index, duration_sec)


def set_span_range(spans: list[TrackSpan], index: int, start_sec: float, end_sec: float, duration_sec: float) -> list[TrackSpan]:
    """Edit start/end of one track; neighbours are trimmed or expanded to keep one contiguous timeline."""
    if not (0 <= index < len(spans)):
        raise IndexError('track index out of range')
    start_sec = max(0.0, min(duration_sec, start_sec))
    end_sec = max(0.0, min(duration_sec, end_sec))
    if end_sec - start_sec < 0.05:
        raise ValueError('track shorter than minimum length')

    new = list(spans)
    if index > 0:
        prev = new[index - 1]
        new[index - 1] = TrackSpan(start_sec=prev.start_sec, end_sec=start_sec)
    else:
        start_sec = 0.0

    if index < len(spans) - 1:
        nxt = new[index + 1]
        new[index + 1] = TrackSpan(start_sec=end_sec, end_sec=nxt.end_sec)
    else:
        end_sec = duration_sec

    new[index] = TrackSpan(start_sec=start_sec, end_sec=end_sec)
    return normalize_spans(new, duration_sec)


def adjust_span_count_to_target(
    spans: list[TrackSpan],
    target: int,
    duration_sec: float,
    *,
    min_piece_sec: float = 0.05,
) -> list[TrackSpan]:
    """Increase or decrease the number of spans to ``target`` (>= 1).

    When reducing, merges the pair of neighbours where the shorter of the two
    tracks is smallest (drops the weakest boundary first). When increasing,
    repeatedly splits the longest track at its midpoint until no segment is long
    enough to split or ``target`` is reached.
    """
    if target < 1:
        return normalize_spans(spans, duration_sec)
    spans = normalize_spans(spans, duration_sec)
    if not spans:
        return [TrackSpan(0.0, duration_sec)] if duration_sec > min_piece_sec else []

    while len(spans) > target:
        best_i = 0
        best_score = float('inf')
        for i in range(len(spans) - 1):
            len_i = spans[i].end_sec - spans[i].start_sec
            len_j = spans[i + 1].end_sec - spans[i + 1].start_sec
            score = min(len_i, len_j)
            if score < best_score:
                best_score = score
                best_i = i
        spans = merge_with_next(spans, best_i, duration_sec)

    while len(spans) < target:
        i = max(range(len(spans)), key=lambda k: spans[k].end_sec - spans[k].start_sec)
        s = spans[i]
        if s.end_sec - s.start_sec < 2 * min_piece_sec + 1e-6:
            break
        mid = (s.start_sec + s.end_sec) / 2.0
        spans = split_span_at(spans, i, mid, duration_sec)

    return normalize_spans(spans, duration_sec)


def insert_cut(spans: list[TrackSpan], cut_sec: float, duration_sec: float) -> list[TrackSpan]:
    """Insert a boundary at ``cut_sec`` by splitting the containing track."""
    if not (0.0 < cut_sec < duration_sec):
        raise ValueError('cut must be inside the timeline')
    for i, s in enumerate(spans):
        if s.start_sec < cut_sec < s.end_sec:
            return split_span_at(spans, i, cut_sec, duration_sec)
    raise ValueError('no track contains the cut time')
