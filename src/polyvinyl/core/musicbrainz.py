# SPDX-License-Identifier: MIT
"""Release / track title lookup via the MusicBrainz web API (free, no API key)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Sequence


class ReleaseLookupError(Exception):
    """Lookup failed (network, rate limit, or empty result)."""


def _request_json(url: str, user_agent: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ReleaseLookupError(f"HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise ReleaseLookupError(str(e.reason)) from e
    return json.loads(body)


def _build_search_query(artist: str | None, album: str | None) -> str:
    parts: list[str] = []
    if artist and artist.strip():
        parts.append(f'artist:"{artist.strip()}"')
    if album and album.strip():
        parts.append(f'release:"{album.strip()}"')
    if not parts:
        raise ReleaseLookupError("Provide an artist name and/or album title.")
    return " AND ".join(parts)


def lookup_track_titles(
    *,
    artist: str | None,
    album: str | None,
    user_agent: str,
    pick_index: int = 0,
    throttle_sec: float = 1.1,
) -> tuple[str, str, list[str]]:
    """Return ``(artist_credit, release_title, track_titles)`` for a release.

    MusicBrainz limits anonymous traffic; we throttle consecutive calls and send a
    descriptive ``User-Agent`` (required by their terms of use).

    ``pick_index`` selects which hit to use when search returns several releases.
    """
    q = _build_search_query(artist, album)
    params = urllib.parse.urlencode({"query": q, "fmt": "json", "limit": "10"})
    search_url = f"https://musicbrainz.org/ws/2/release/?{params}"
    data = _request_json(search_url, user_agent)
    releases = data.get("releases") or []
    if not releases:
        raise ReleaseLookupError("No matching releases on MusicBrainz.")

    pick_index = max(0, min(pick_index, len(releases) - 1))
    release = releases[pick_index]
    mbid = release.get("id")
    title = release.get("title") or "Unknown Album"

    ac = release.get("artist-credit") or []
    artist_parts: list[str] = []
    for entry in ac:
        if not isinstance(entry, dict):
            continue
        if entry.get("name"):
            artist_parts.append(str(entry["name"]))
        elif isinstance(entry.get("artist"), dict):
            an = entry["artist"].get("name")
            if an:
                artist_parts.append(str(an))
    artist_line = ", ".join(artist_parts) if artist_parts else (artist or "").strip() or "Unknown Artist"

    time.sleep(throttle_sec)

    inc = urllib.parse.urlencode(
        {"fmt": "json", "inc": "artist-credits+recordings+release-groups"}
    )
    detail_url = f"https://musicbrainz.org/ws/2/release/{mbid}?{inc}"
    detail = _request_json(detail_url, user_agent)

    tracks_out: list[str] = []
    for medium in detail.get("media") or []:
        for tr in medium.get("tracks") or []:
            rec = tr.get("recording") or {}
            t = rec.get("title") or tr.get("title")
            if t:
                tracks_out.append(str(t))

    if not tracks_out:
        raise ReleaseLookupError("Release found but no track list was returned.")

    return artist_line, title, tracks_out


def titles_for_span_count(mb_titles: Sequence[str], n_spans: int) -> list[str]:
    """Align MusicBrainz titles with ``n_spans`` detected segments."""
    out: list[str] = []
    for i in range(n_spans):
        if i < len(mb_titles):
            out.append(mb_titles[i])
        else:
            out.append(f"Track {i + 1:02d}")
    return out
