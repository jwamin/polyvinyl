pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'polyvinyl'
gnome = import('gnome')

gnome.compile_resources('polyvinyl',
  'polyvinyl.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'polyvinyl.in',
  output: 'polyvinyl',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

polyvinyl_pkg = files(
  'polyvinyl/__init__.py',
  'polyvinyl/main.py',
  'polyvinyl/window.py',
)

polyvinyl_core = files(
  'polyvinyl/core/__init__.py',
  'polyvinyl/core/silence.py',
  'polyvinyl/core/analysis.py',
  'polyvinyl/core/segments.py',
  'polyvinyl/core/musicbrainz.py',
  'polyvinyl/core/export.py',
  'polyvinyl/core/naming.py',
  'polyvinyl/core/wav_info.py',
)

install_data(polyvinyl_pkg, install_dir: moduledir)
install_data(polyvinyl_core, install_dir: moduledir / 'core')
