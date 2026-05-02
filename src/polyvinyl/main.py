# MIT License
#
# Copyright (c) 2026 jwamin
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# SPDX-License-Identifier: MIT

import sys
import gi

from gettext import gettext as _

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Gio, Adw
from .window import PolyvinylWindow


class PolyvinylApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self, version: str):
        super().__init__(application_id='org.jossy.gnome.polyvinyl',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
                         resource_base_path='/org/jossy/gnome/polyvinyl')
        self.version = version
        self.create_action('quit', lambda *_: self.quit(), ['<control>q'])
        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('shortcuts', self.on_shortcuts_action, ['<control>slash'])

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = PolyvinylWindow(application=self)
        win.present()

    def on_about_action(self, *_args):
        about = Adw.AboutDialog(application_name='Polyvinyl',
                                application_icon='org.jossy.gnome.polyvinyl',
                                developer_name='jwamin',
                                version=self.version,
                                translator_credits=_('translator-credits'),
                                developers=['jwamin'],
                                copyright='© 2026 jwamin',
                                comments=_('Split vinyl WAV rips into FLAC, MP3, or WAV tracks using silence '
                                           'detection and MusicBrainz metadata.'))
        about.present(self.props.active_window)

    def on_preferences_action(self, _widget, __):
        print('app.preferences action activated')

    def on_shortcuts_action(self, *_args):
        builder = Gtk.Builder.new_from_resource(
            '/org/jossy/gnome/polyvinyl/shortcuts-dialog.ui')
        shortcuts = builder.get_object('shortcuts_dialog')
        shortcuts.present(self.props.active_window)

    def create_action(self, name, callback, shortcuts=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version):
    """The application's entry point."""
    app = PolyvinylApplication(version)
    return app.run(sys.argv)
