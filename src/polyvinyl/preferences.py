# SPDX-License-Identifier: MIT
"""Application preferences (GSettings-backed)."""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

_SCHEMA_ID = 'org.jossy.gnome.polyvinyl'
_DSP_KEY = 'dsp-backend'
_BACKENDS = ('auto', 'python', 'native')


def show_preferences_window(parent: Gtk.Window | None) -> None:
    settings = Gio.Settings.new(_SCHEMA_ID)

    if hasattr(Adw, 'PreferencesDialog'):
        win = Adw.PreferencesDialog()
    else:
        win = Adw.PreferencesWindow()
    if parent is not None:
        win.set_transient_for(parent)
        win.set_modal(True)

    page = Adw.PreferencesPage(title=_('General'))
    group = Adw.PreferencesGroup(
        title=_('Audio analysis'),
        description=_(
            'Waveform envelope and RMS windows for silence detection. '
            'Native C uses the same algorithms in a small shared library (Linux, macOS on Intel and Apple silicon). '
            'Python is always available when the native library is missing.'
        ),
    )
    model = Gtk.StringList.new(
        [
            _('Automatic (prefer native if installed)'),
            _('Python'),
            _('Native C'),
        ],
    )
    row = Adw.ComboRow(
        title=_('DSP library'),
        subtitle=_('Applies to the next waveform analysis or silence detection run'),
        model=model,
    )

    def row_index_for_settings() -> int:
        try:
            s = settings.get_string(_DSP_KEY)
        except Exception:
            s = 'auto'
        if s not in _BACKENDS:
            s = 'auto'
        return _BACKENDS.index(s)

    def apply_settings_to_row(*_args) -> None:
        row.set_selected(row_index_for_settings())

    def on_row_selected(*_args) -> None:
        i = int(row.get_selected())
        if 0 <= i < len(_BACKENDS):
            settings.set_string(_DSP_KEY, _BACKENDS[i])

    apply_settings_to_row()
    settings.connect(f'changed::{_DSP_KEY}', apply_settings_to_row)
    row.connect('notify::selected', on_row_selected)

    group.add(row)
    page.add(group)
    win.add(page)
    if isinstance(win, Adw.PreferencesDialog):
        win.present(parent if isinstance(parent, Gtk.Window) else None)
    else:
        win.present()
