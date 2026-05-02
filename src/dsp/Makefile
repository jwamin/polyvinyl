# SPDX-License-Identifier: MIT
# Convenience wrapper around CMake (out-of-tree build).
CMAKE ?= cmake
BUILD_DIR ?= build-cmake
BUILD_TYPE ?= Release
GENERATOR ?=

.PHONY: all static shared framework configure clean

all: configure
	$(CMAKE) --build $(BUILD_DIR) --parallel

configure:
	$(CMAKE) -S . -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) $(GENERATOR)

static: configure
	$(CMAKE) --build $(BUILD_DIR) --target polyvinyl_dsp_static --parallel

shared: configure
	$(CMAKE) --build $(BUILD_DIR) --target polyvinyl_dsp --parallel

framework: configure
	@if [ "$$(uname -s)" != "Darwin" ]; then echo "framework target is only for Apple platforms"; exit 1; fi
	$(CMAKE) --build $(BUILD_DIR) --target polyvinyl_dsp_framework --parallel

clean:
	rm -rf "$(BUILD_DIR)"
