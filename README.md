# Polyvinyl

GTK 4 / Libadwaita app that **splits long vinyl WAV captures into separate tracks** using **silence detection**, looks up **track titles** via the free **[MusicBrainz](https://musicbrainz.org/)** API, and exports **FLAC**, **MP3**, and/or **16‑bit WAV** with sane folder and file naming.

**Repository:** [github.com/jwamin/polyvinyl](https://github.com/jwamin/polyvinyl)

![Polyvinyl main window](docs/screenshot.png)

The image above is an **illustrative preview** of the layout (Libadwaita preferences-style UI, header bar, activity log). Your installed theme may differ slightly.

## Features

- **Silence-based cueing** — configurable RMS threshold and minimum silence duration to match groove noise on your pressing.
- **MusicBrainz lookup** — enter artist and/or album; the app fetches a track list (rate-limited, descriptive User-Agent, no API key).
- **Multi-format export** — enable any combination of FLAC (lossless), MP3 (LAME VBR), and PCM WAV per run.
- **Library-style paths** — `{library}/{Artist}/{Album}/{NN} – {Title}.{ext}` with filesystem-safe names.
- **Reusable core** — `polyvinyl.core` has **no GTK dependency** (detection, lookup, naming, ffmpeg-backed export) for scripts or future front ends.

## Requirements

- **Python 3**, **PyGObject**, **GTK 4**, **Libadwaita** (typical GNOME app stack).
- **ffmpeg** on `PATH`. MP3 export needs **libmp3lame** in your ffmpeg build.

Flatpak/runtime images often need ffmpeg bundled or supplied via an extension; the stock GNOME runtime may not include every encoder.

## Build & run (Meson)

```sh
meson setup build --prefix=/usr
meson compile -C build
sudo meson install -C build
polyvinyl
```

After `meson compile -C build`, bundled UI resources are emitted under `build/`; running from the install prefix (or Flatpak) is the most reliable way to exercise the full UI.

## Flatpak

`org.jossy.gnome.polyvinyl.json` is a starter manifest (adjust module sources and add **ffmpeg** if needed). Build with `flatpak-builder` against `org.gnome.Platform`.

## Library usage

```python
from polyvinyl.core import (
    detect_track_spans,
    lookup_track_titles,
    encode_wav_segment,
    album_output_dir,
    track_filename,
)
```

Install layout puts the package under the Meson `pkgdatadir` (e.g. `share/polyvinyl/polyvinyl/`); the launcher adds that path to `PYTHONPATH`.

## License

MIT — see [COPYING](COPYING).
