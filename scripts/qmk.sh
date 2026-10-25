#!/usr/bin/env bash
# Run the QMK CLI from the official Docker image against a qmk_firmware checkout.
# QMK_DIR defaults to ./qmk_firmware (clone of jpsutton/qmk_firmware, branch mk-typist).
# Example: scripts/qmk.sh compile -kb mk/typist -km default
set -euo pipefail
qmk_dir="$(cd "${QMK_DIR:-qmk_firmware}" && pwd)"
tty_flag=()
[ -t 0 ] && tty_flag=(-it)
exec docker run --rm "${tty_flag[@]}" --user "$(id -u):$(id -g)" \
    -e HOME=/tmp -e QMK_HOME=/qmk_firmware \
    -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
    -v "$qmk_dir":/qmk_firmware -w /qmk_firmware \
    ghcr.io/qmk/qmk_cli:latest qmk "$@"
