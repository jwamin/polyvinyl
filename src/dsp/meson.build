cc = meson.get_compiler('c')
math_dep = cc.find_library('m', required: false)

dsp_deps = []
if math_dep.found()
  dsp_deps += math_dep
endif

polyvinyl_dsp_lib = shared_library(
  'polyvinyl_dsp',
  'polyvinyl_dsp.c',
  c_args: ['-D_DEFAULT_SOURCE'],
  dependencies: dsp_deps,
  install: true,
  install_dir: moduledir / 'core',
)
