"""Replace Ghidra DAT_<addr> literal-pool reads with the 32-bit value stored there.

Usage: python3 resolve_literals.py <image.bin> <base-hex> <in.c> <out.c>
"""
import re
import struct
import sys

PORTS = {0x400B0000: "GPIOA", 0x400B2000: "GPIOB", 0x400B4000: "GPIOC", 0x400B6000: "GPIOD", 0x400B8000: "GPIOE"}
GPIO_REGS = ["DIRCR", "INER", "PUR", "PDR", "ODR", "DRVR", "LOCKR", "DINR", "DOUTR", "SRR", "RR"]


def label(v):
    for base, name in PORTS.items():
        off = v - base
        if 0 <= off < 0x2C and off % 4 == 0:
            return f"{name}_{GPIO_REGS[off // 4]}" if off else f"{name}_BASE"
    return None


def main(img, base, src, dst):
    data = open(img, "rb").read()
    base = int(base, 16)

    def sub(m):
        addr = int(m.group(1), 16)
        off = addr - base
        if 0 <= off <= len(data) - 4 and off % 4 == 0:
            v = struct.unpack_from("<I", data, off)[0]
            name = label(v)
            return f"/*{name}*/0x{v:08x}" if name else f"0x{v:x}"
        return m.group(0)

    text = open(src).read()
    open(dst, "w").write(re.sub(r"\bDAT_([0-9a-f]{8})\b", sub, text))


if __name__ == "__main__":
    main(*sys.argv[1:5])
