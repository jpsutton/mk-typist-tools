#!/usr/bin/env bash
# Run hansemro's HT32 OpenOCD fork from Docker. The current directory is mounted at /work.
# Build the image first: docker build -t mk-typist/openocd-ht32 -f docker/openocd-ht32.Dockerfile docker
# Config for the Typist: openocd/typist.cfg in jpsutton/mk-typist-research.
# --privileged is needed for the USB probe (CMSIS-DAP over hidraw or libusb).
set -euo pipefail
tty_flag=()
[ -t 0 ] && tty_flag=(-it)
exec docker run --rm "${tty_flag[@]}" --privileged \
    -v /dev:/dev -v "$PWD":/work -w /work \
    -p 127.0.0.1:3333:3333 -p 127.0.0.1:4444:4444 -p 127.0.0.1:6666:6666 \
    mk-typist/openocd-ht32 "$@"
