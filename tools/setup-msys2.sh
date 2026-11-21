#!/usr/bin/env bash
set -euo pipefail
pacman -Sy --noconfirm
pacman -S --needed --noconfirm \
  git patch make \
  mingw-w64-clang-x86_64-toolchain \
  mingw-w64-clang-x86_64-cmake \
  mingw-w64-clang-x86_64-ninja \
  mingw-w64-clang-x86_64-pkgconf \
  mingw-w64-clang-x86_64-python \
  mingw-w64-clang-x86_64-vulkan-headers \
  mingw-w64-clang-x86_64-vulkan-loader \
  mingw-w64-clang-x86_64-vulkan-memory-allocator \
  mingw-w64-clang-x86_64-glslang \
  mingw-w64-clang-x86_64-sdl3 \
  mingw-w64-clang-x86_64-fmt \
  mingw-w64-clang-x86_64-boost \
  mingw-w64-clang-x86_64-robin-map \
  mingw-w64-clang-x86_64-xxhash \
  mingw-w64-clang-x86_64-zlib \
  mingw-w64-clang-x86_64-zydis \
  mingw-w64-clang-x86_64-nasm \
  mingw-w64-clang-x86_64-spirv-tools \
  mingw-w64-clang-x86_64-spirv-headers \
  mingw-w64-clang-x86_64-spirv-cross \
  mingw-w64-clang-x86_64-ffmpeg \
  mingw-w64-clang-x86_64-protobuf \
  mingw-w64-clang-x86_64-nlohmann-json \
  mingw-w64-clang-x86_64-openssl \
  mingw-w64-clang-x86_64-miniupnpc
pacman -Q > "/a/everybodys golf ps4/tools/msys2-package-versions.txt"
printf 'MSYS2 CLANG64 setup complete\n'
