#!/usr/bin/env bash
# Save USB descriptors for the keyboard into ./usb-captures/. Read-only.
# Usage: scripts/usb_capture.sh <mode-label> [VID:PID]
#   mode-label: e.g. normal, bootloader
#   VID:PID: optional; without it, all devices with Holtek VID 04d9 are captured.
set -euo pipefail
mode="${1:?usage: $0 <mode-label> [VID:PID]}"
out="usb-captures/$(date +%F)_${mode}"
mkdir -p "$(dirname "$out")"

ids=("${2:-}")
if [ -z "${ids[0]}" ]; then
    mapfile -t ids < <(lsusb | awk '$6 ~ /^04d9:/ {print $6}' | sort -u)
fi
if [ "${#ids[@]}" -eq 0 ] || [ -z "${ids[0]}" ]; then
    echo "No 04d9 device found. Full lsusb:" >&2
    lsusb >&2
    exit 1
fi

{
    echo "# captured $(date -Is), mode=$mode"
    lsusb
    for id in "${ids[@]}"; do
        echo
        echo "## lsusb -v -d $id"
        lsusb -v -d "$id" 2>&1 || true
    done
    echo
    echo "## kernel log (last 40 USB lines)"
    journalctl -k --no-pager -n 400 2>/dev/null | grep -i usb | tail -40 || true
} > "$out.txt"
echo "Saved $out.txt"
