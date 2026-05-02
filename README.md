# Polyvinyl

GTK 4 / Libadwaita app that **splits long vinyl WAV captures into separate tracks** using **silence detection**, looks up **track titles** via the free **[MusicBrainz](https://musicbrainz.org/)** API, and exports **FLAC**, **MP3**, and/or **16‑bit WAV** with sane folder and file naming.

**Repository:** [github.com/jwamin/polyvinyl](https://github.com/jwamin/polyvinyl)

![Polyvinyl main window](docs/screenshot.png)

The image above is an **illustrative preview** of the layout (Libadwaita preferences-style UI, header bar, activity log). Your installed theme may differ slightly.

## Features

- **Silence-based cueing** — configurable RMS threshold and minimum silence duration to match groove noise on your pressing.
- **Waveform analysis** — builds a peak envelope for the whole rip, estimates noise vs programme level, and **suggests** RMS threshold and minimum silence (applied to the spin buttons; tune manually if needed). After analyze, **initial track markers** are placed from silence detection. The drawing shows **visual feedback** for the current threshold (blue where RMS is below threshold, green where gaps meet minimum silence) and a dashed reference line versus peak level. **Refresh markers** re-runs detection when you change the silence spins.
- **Track boundary CRUD** — after detection or analysis, edit **start/end** per track, **merge** with the next track, **remove** a track (merge with a neighbour), **double‑click the waveform** to insert a new cut, or **single‑click near a boundary** for a popover that maps **MusicBrainz lookup titles** to the tracks before and after that cut.
- **MusicBrainz lookup** — enter artist and/or album; the app fetches a track list (rate-limited, descriptive User-Agent, no API key).
- **Multi-format export** — enable any combination of FLAC (lossless), MP3 (LAME VBR), and PCM WAV per run.
- **Library-style paths** — `{library}/{Artist}/{Album}/{NN} – {Title}.{ext}` with filesystem-safe names.
- **Reusable core** — `polyvinyl.core` has **no GTK dependency** (RMS/waveform analysis, silence detection, segment CRUD helpers, lookup, naming, ffmpeg-backed export) for scripts or future front ends.
- **Native C DSP (optional)** — the same **RMS window series** and **waveform envelope** algorithms are implemented in **`libpolyvinyl_dsp`** (plain C99, no external audio deps) for **Linux** and **macOS** on **Intel and Apple silicon**. Meson builds the shared library and installs it next to the Python modules. **Preferences → General** (or the `dsp-backend` GSetting / `POLYVINYL_DSP_BACKEND` environment variable: `auto`, `python`, `native`) selects **Python**, **native C**, or **automatic** fallback when the library is missing.

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

After `meson compile -C build`, bundled UI resources are emitted under `build/`; running from the install prefix (or Flatpak) is the most reliable way to exercise the full UI. The C DSP library is built as `build/src/dsp/libpolyvinyl_dsp.so` (or `.dylib` on macOS); when running from a checkout without installing, set **`POLYVINYL_DSP_LIB`** to that path (or **`MESON_BUILD_ROOT`** so the loader checks `build/src/dsp/`) to try the native backend.

## Flatpak

`org.jossy.gnome.polyvinyl.json` is a starter manifest (adjust module sources and add **ffmpeg** if needed). Build with `flatpak-builder` against `org.gnome.Platform`.

## Library usage

```python
from polyvinyl.core import (
    rms_window_series,
    compute_waveform_envelope,
    suggest_silence_params,
    detect_track_spans,
    insert_cut,
    set_span_range,
    lookup_track_titles,
    encode_wav_segment,
    album_output_dir,
    track_filename,
)
```

Install layout puts the package under the Meson `pkgdatadir` (e.g. `share/polyvinyl/polyvinyl/`); the launcher adds that path to `PYTHONPATH`.

## License

MIT — see [COPYING](COPYING).
