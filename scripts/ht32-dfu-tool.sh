#!/usr/bin/env bash
# Run hansemro/ht32-dfu-tool (Holtek ROM ISP over USB, 04d9:8010) from Docker.
# Build the image first: docker build -t mk-typist/ht32-dfu-tool -f docker/ht32-dfu-tool.Dockerfile docker
# The current directory is mounted at /work. Read-only commands: list, info.
# On a locked chip, mass erase also deletes the stock IAP bootloader.
set -euo pipefail
exec docker run --rm --privileged \
    -v /dev/bus/usb:/dev/bus/usb -v "$PWD":/work -w /work \
    mk-typist/ht32-dfu-tool "$@"
