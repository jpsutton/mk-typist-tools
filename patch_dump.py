#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Patch the stock Typist app (V1.00.05, linked at 0x3200) so CMD_READ (0x12)
subcommand 0xFF returns 60 bytes of flash from the address in packet bytes 4..7.

This is the same convention pok3rtool's CYKB_Device.read_flash() uses. The patch
replaces the bounds check of the version-page read in the vendor command handler
(FUN_00006ca4, stock code at 0x6cec):

  0x6cec  28ff  cmp  r0, #255          sub == 0xff ?
  0x6cee  d10e  bne  0x6d0e            no: fall into the sub 0/1/2 checks
  0x6cf0  6868  ldr  r0, [r5, #4]      address from the request
  0x6cf2  213c  movs r1, #60           length
  0x6cf4  e032  b    0x6d5c            existing "copy r1 bytes from r0 and reply" path

Side effect: version-page reads (subs 0x20..0x27) stop working in the patched app.
Flash the result with cykb.py, then read flash with `cykb.py dump`. Get the stock
image with `cykb.py extract MK_Typist_V1.00.05NL.exe <dir>`.
Usage: patch_dump.py <stock.bin> <out.bin>
"""
import hashlib
import sys

BASE = 0x3200
STOCK_SHA256 = "0094d2472a2e160d095387df2f05ce13f78a38d21d45bf1ac33f84264efaea9c"
PATCH_ADDR = 0x6CEC
ORIGINAL = bytes.fromhex("2028 0ed3 0146 1f39 3c22")
PATCHED = bytes.fromhex("ff28 0ed1 6868 3c21 32e0")


def main(src, dst):
    data = bytearray(open(src, "rb").read())
    digest = hashlib.sha256(data).hexdigest()
    if digest != STOCK_SHA256:
        sys.exit(f"{src}: SHA-256 {digest} is not the stock V1.00.05 app")
    off = PATCH_ADDR - BASE
    if data[off:off + len(ORIGINAL)] != ORIGINAL:
        sys.exit(f"unexpected bytes at {PATCH_ADDR:#x}: {data[off:off + len(ORIGINAL)].hex()}")
    data[off:off + len(PATCHED)] = PATCHED
    open(dst, "xb").write(data)
    print(f"{dst}: {len(data)} bytes, SHA-256 {hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main(*sys.argv[1:])
