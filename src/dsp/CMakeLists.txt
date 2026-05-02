# SPDX-License-Identifier: MIT
# Optional build of libpolyvinyl_dsp (static .a, shared .so/.dylib, and macOS framework).
cmake_minimum_required(VERSION 3.16)
project(polyvinyl_dsp LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(POLYVINYL_DSP_SOURCES polyvinyl_dsp.c)
set(POLYVINYL_DSP_PUBLIC_HEADER "${CMAKE_CURRENT_SOURCE_DIR}/polyvinyl_dsp.h")

# Static archive (all platforms)
add_library(polyvinyl_dsp_static STATIC ${POLYVINYL_DSP_SOURCES})
target_include_directories(polyvinyl_dsp_static PUBLIC
  "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>"
  "$<INSTALL_INTERFACE:include>")
set_target_properties(polyvinyl_dsp_static PROPERTIES OUTPUT_NAME polyvinyl_dsp)
if(UNIX)
  target_compile_definitions(polyvinyl_dsp_static PRIVATE _DEFAULT_SOURCE)
endif()

# Shared library for ctypes / Meson-style installs (libpolyvinyl_dsp.so / .dylib)
add_library(polyvinyl_dsp SHARED ${POLYVINYL_DSP_SOURCES})
target_include_directories(polyvinyl_dsp PUBLIC
  "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>"
  "$<INSTALL_INTERFACE:include>")
set_target_properties(polyvinyl_dsp PROPERTIES
  OUTPUT_NAME polyvinyl_dsp
  VERSION 0.1.0
  SOVERSION 0
  PUBLIC_HEADER "${POLYVINYL_DSP_PUBLIC_HEADER}")
if(UNIX)
  target_compile_definitions(polyvinyl_dsp PRIVATE _DEFAULT_SOURCE)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  target_link_libraries(polyvinyl_dsp_static INTERFACE m)
  target_link_libraries(polyvinyl_dsp PRIVATE m)
endif()

# macOS / iOS-style dynamic framework (load e.g. PolyvinylDSP.framework/PolyvinylDSP)
if(APPLE)
  add_library(polyvinyl_dsp_framework SHARED ${POLYVINYL_DSP_SOURCES})
  target_compile_definitions(polyvinyl_dsp_framework PRIVATE _DEFAULT_SOURCE)
  target_include_directories(polyvinyl_dsp_framework PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>"
    "$<INSTALL_INTERFACE:include>")
  set_target_properties(polyvinyl_dsp_framework PROPERTIES
    FRAMEWORK TRUE
    FRAMEWORK_VERSION A
    MACOSX_FRAMEWORK_IDENTIFIER org.jossy.polyvinyl.dsp
    OUTPUT_NAME PolyvinylDSP
    PUBLIC_HEADER "${POLYVINYL_DSP_PUBLIC_HEADER}")
endif()

include(GNUInstallDirs)
install(TARGETS polyvinyl_dsp_static polyvinyl_dsp
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
  PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/polyvinyl)

if(APPLE)
  install(TARGETS polyvinyl_dsp_framework
    FRAMEWORK DESTINATION ${CMAKE_INSTALL_LIBDIR}
    PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/polyvinyl)
endif()
