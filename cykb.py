#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CYKB client for the stock Cheng Yong IAP bootloader on the MK Typist (and related boards).

Talks to the vendor HID interface of the stock application or the stock IAP over Linux
hidraw, and decodes the vendor "maaV102" updater. Protocol, updater format and XOR key
follow pok3rtool (https://github.com/pok3r-custom/pok3rtool). Background and evidence:
https://github.com/jpsutton/mk-typist-research

IAP addresses are relative to 0x3000 (the version page); the application is at +0x200.

Commands:
  info                                  read-only: bootloader info block and mode
  version                               read-only, stock app only: version page 0x3000..0x31DF
  sum <image.bin>                       read-only, IAP only: compare flash sum/CRC with an image
  extract <updater.exe> <out-dir>       offline: application images and version pages
  check <image.bin> [version.bin]       offline: run the pre-flash checks on files
  reboot-bl                             app -> IAP (stock app; QMK uses Fn+Esc or Esc at plug-in)
  reboot-fw                             IAP -> app
  flash <image.bin> <version.bin> [--yes]
                                        ERASES and rewrites 0x3000.. through the IAP
  dump <out.bin> [start] [end]          needs an app patched with patch_dump.py
"""
import glob
import hashlib
import os
import select
import struct
import sys
import zlib
from pathlib import Path

VID = 0x04D9
# pid: (mode, product, tested)
PIDS = {
    0x0301: ("app", "MK Typist", True),
    0x1301: ("iap", "MK Typist", True),
    0x0296: ("app", "Ducky One 2", False),
    0x1296: ("iap", "Ducky One 2", False),
}

CMD_RESET, RESET_BL, RESET_FW = 0x11, 0, 1
CMD_READ, READ_BL_INFO, READ_MODE, READ_VERSION, READ_ADDR = 0x12, 0, 2, 0x20, 0xFF
CMD_FW, FW_ERASE, FW_SUM, FW_CRC = 0x1D, 0, 1, 2
CMD_ADDR, ADDR_GET, ADDR_SET = 0x1E, 0, 1
CMD_WRITE, RESP_WRITE_ADDR = 0x1F, 2

IAP_BASE = 0x3000
APP_OFFSET = 0x200      # app at 0x3200
PAGE = 0x200
FLASH_END = 0x1FE00     # HT32F52352: 130,560 B main flash
MIN_ERASE = 0x7E00      # 0x3000..0xADFF, the stock application's span
APP_HEADER = (0x9F8, (0x04040000, 0x34000001))  # application signature and checksum control

# POK3R RGB XOR key (pok3rtool). Equals the first 52 bytes of the IAP's RC4 keystream,
# so it is only valid when every write packet carries exactly 52 bytes.
XOR_KEY = [0xe7c29474, 0x79084b10, 0x53d54b0d, 0xfc1e8f32, 0x48e81a9b, 0x773c808e, 0xb7483552,
           0xd9cb8c76, 0x2a8c8bc6, 0x0967ada8, 0xd4520f5c, 0xd0c3279d, 0xeac091c5]


def xor_encode(data):
    assert len(data) % 4 == 0
    words = struct.unpack(f"<{len(data) // 4}I", data)
    return struct.pack(f"<{len(words)}I", *(w ^ XOR_KEY[i % len(XOR_KEY)] for i, w in enumerate(words)))


def checksum(data):
    return sum(b << ((i & 3) * 8) for i, b in enumerate(data)) & 0xFFFFFFFF


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ---- image and version page checks (mirror the IAP's own boot check) ----

def check_image(image):
    """Return the image padded to 4 bytes, or exit if the IAP would not start or verify it."""
    if len(image) % 4:
        image += b"\xff" * (4 - len(image) % 4)
    if len(image) < 0x1000:
        sys.exit("image is shorter than 0x1000 bytes; the IAP cannot verify it")
    if APP_OFFSET + len(image) > FLASH_END - IAP_BASE:
        sys.exit("image does not fit in flash")
    sp, reset = struct.unpack_from("<II", image, 0)
    if not (0x20000000 <= sp <= 0x20004000) or not (IAP_BASE + APP_OFFSET < reset < FLASH_END):
        sys.exit(f"vector table does not look like an app linked at 0x3200 (SP {sp:#x}, reset {reset:#x})")
    off, want = APP_HEADER
    got = struct.unpack_from("<2I", image, off)
    if got != want:
        sys.exit(f"application header at 0x3BF8 is {got[0]:08x} {got[1]:08x}, need 04040000 34000001")
    return image


def check_version_page(vpage):
    """Exit unless the IAP's application check would accept this version page."""
    if not 0xB4 <= len(vpage) <= PAGE:
        sys.exit(f"version page is {len(vpage)} bytes; expected 180..512")
    magic = struct.unpack_from("<I", vpage, 0xB0)[0]
    n = magic >> 18
    if magic & 0x3FFFF != 0x5AA5 or n > 14:
        sys.exit(f"version page magic at 0x30B0 is {magic:#010x}; is this an unconverted updater template?")
    words = struct.unpack_from(f"<{n}I", vpage, 0x78)
    if 0xFFFFFFFF in words:
        sys.exit("version page has an erased word in 0x3078..; the IAP would not start the app")
    return words[-1] >> 16 if n else None  # application PID


# ---- updater (maaV102) ----

def decode_package_data(data):
    b = bytearray(data)
    for i in range(4, len(b), 5):
        b[i - 4], b[i] = b[i], b[i - 4]
    for i in range(1, len(b), 2):
        b[i - 1], b[i] = b[i], b[i - 1]
    return bytes((((x - 7) << 4) + (x >> 4)) & 0xFF for x in b)


def wstr(raw):
    return raw.decode("utf-16-le").split("\0")[0]


def version_template_to_page(t):
    """The updater stores the magic's count byte at 0xAE; on flash it sits at 0xB2."""
    t = bytearray(t)
    if len(t) < 0xB4 or t[0xAF:0xB4] != b"\xff\xa5\x5a\xff\x00":
        sys.exit(f"unexpected version template tail {t[0xAC:0xB4].hex()}")
    t[0xB2], t[0xAE] = t[0xAE], 0xFF
    return bytes(t)


def extract(path, outdir):
    data = open(path, "rb").read()
    trailer_len = 0xB24  # sizeof(maav102_info) in pok3rtool
    info = decode_package_data(data[-trailer_len:])
    if info[-11:-3] != b".maaV102":
        sys.exit(f"{path}: not a maaV102 updater")
    _, _, pid = struct.unpack_from("<IHH", info, 0)
    boot_vid, boot_pid, app_vid, app_pid = struct.unpack_from("<4I", info, 0x14)
    product, version = wstr(info[0x26 + 2 * 0x208:0x26 + 3 * 0x208]), wstr(info[0x26 + 3 * 0x208:0x846])
    print(f"{path}: SHA-256 {sha256(data)}")
    print(f"  product {product} {version}, app {app_vid:04x}:{app_pid:04x}, IAP {boot_vid:04x}:{boot_pid:04x}")
    layouts = []
    for i in range(9):
        fw_len, ver_len = struct.unpack_from("<II", info, 0x848 + i * 80)
        if fw_len:
            layouts.append((wstr(info[0x848 + i * 80 + 8:0x848 + i * 80 + 68]), fw_len, ver_len))
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    pos = len(data) - trailer_len - sum(f + v for _, f, v in layouts)
    for name, fw_len, ver_len in layouts:
        image = xor_encode(decode_package_data(data[pos:pos + fw_len]))  # XOR is its own inverse
        pos += fw_len
        vpage = version_template_to_page(decode_package_data(data[pos:pos + ver_len]))
        pos += ver_len
        stem = f"{app_pid:04x}-{name.replace(' ', '_')}-{version}"
        for suffix, blob in (("app", image), ("version", vpage)):
            out = outdir / f"{stem}-{suffix}.bin"
            if out.exists():
                sys.exit(f"{out} exists; not overwriting")
            out.write_bytes(blob)
            print(f"  {out}: {len(blob)} bytes, SHA-256 {sha256(blob)}")


# ---- device ----

def find_device():
    """Return (path, pid) of the vendor (usage page 0xFF00) hidraw node."""
    found = []
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = open(f"{node}/device/uevent").read()
        hid_id = next(l.split("=")[1] for l in uevent.splitlines() if l.startswith("HID_ID="))
        _, vid, pid = (int(x, 16) for x in hid_id.split(":"))
        if vid != VID or pid not in PIDS:
            continue
        if open(f"{node}/device/report_descriptor", "rb").read()[:3] != b"\x06\x00\xff":
            continue
        found.append((f"/dev/{os.path.basename(node)}", pid))
    if len(found) != 1:
        sys.exit(f"expected one supported keyboard vendor interface, found {found}")
    return found[0]


class Cykb:
    def __init__(self):
        self.path, self.pid = find_device()
        self.mode, self.product, tested = PIDS[self.pid]
        if not tested:
            print(f"WARNING: {self.product} ({VID:04x}:{self.pid:04x}) has never been tested with this tool")
        try:
            self.fd = os.open(self.path, os.O_RDWR)
        except PermissionError:
            sys.exit(f"no access to {self.path}; install udev/50-mk-typist.rules")

    def cmd(self, cmd, sub=0, data=b"", timeout=1.0):
        pkt = struct.pack("<BBH", cmd, sub, 0) + data
        os.write(self.fd, b"\0" + pkt.ljust(64, b"\0"))
        return self.recv(timeout)

    def recv(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            raise TimeoutError("no response")
        return os.read(self.fd, 64)

    def expect(self, resp, cmd, sub):
        if resp[0] != cmd or resp[1] != sub or resp[2:4] != b"\0\0":
            raise RuntimeError(f"error response {resp[:4].hex()}, expected {cmd:02x} {sub:02x}")
        return resp[4:]

    def info(self):
        r = self.expect(self.cmd(CMD_READ, READ_BL_INFO), CMD_READ, READ_BL_INFO)
        (_, _, vid, pid, _, _, _, _, _, _, fw_offset, fw_pages, page_size, model, _) = \
            struct.unpack_from("<IIHHHHIIIIHHH10sI", r)
        mode = self.expect(self.cmd(CMD_READ, READ_MODE), CMD_READ, READ_MODE)[0]
        return dict(boot_vid=vid, boot_pid=pid, fw_offset=fw_offset, fw_pages=fw_pages,
                    page_size=page_size, model=model.rstrip(b"\0").decode(), mode=mode)

    def version_page(self):
        return b"".join(self.expect(self.cmd(CMD_READ, READ_VERSION + i), CMD_READ, READ_VERSION + i)[:60]
                        for i in range(8))

    def sum_crc(self, addr, size):
        args = struct.pack("<II", addr, size)
        s = struct.unpack_from("<I", self.expect(self.cmd(CMD_FW, FW_SUM, args, 3), CMD_FW, FW_SUM))[0]
        c = struct.unpack_from("<I", self.expect(self.cmd(CMD_FW, FW_CRC, args, 3), CMD_FW, FW_CRC))[0]
        return s, c

    def read(self, addr):
        return self.expect(self.cmd(CMD_READ, READ_ADDR, struct.pack("<I", addr)), CMD_READ, READ_ADDR)[:60]

    def erase(self, addr, size):
        os.write(self.fd, b"\0" + struct.pack("<BBHII", CMD_FW, FW_ERASE, 0, addr, size).ljust(64, b"\0"))
        self.expect(self.recv(30), CMD_FW, FW_ERASE)

    def write(self, addr, data):
        self.expect(self.cmd(CMD_ADDR, ADDR_SET, struct.pack("<I", addr)), CMD_ADDR, ADDR_SET)
        r = self.expect(self.cmd(CMD_ADDR, ADDR_GET, struct.pack("<I", 0xFFFFFFFF)), CMD_ADDR, ADDR_GET)
        if struct.unpack_from("<I", r)[0] != addr:
            raise RuntimeError(f"address set failed: {r[:4].hex()}")
        for p in range(0, len(data), 52):
            chunk = data[p:p + 52]
            r = self.expect(self.cmd(CMD_WRITE, len(chunk), chunk), CMD_ADDR, RESP_WRITE_ADDR)
            if struct.unpack_from("<I", r)[0] != addr + p + len(chunk):
                raise RuntimeError(f"write ack {r[:4].hex()} at offset {p:#x}")

    def reset(self, sub):
        os.write(self.fd, b"\0" + struct.pack("<BBH", CMD_RESET, sub, 0).ljust(64, b"\0"))


def load(path):
    data = open(path, "rb").read()
    print(f"{path}: {len(data)} bytes, SHA-256 {sha256(data)}")
    return data


def flash(dev, image, vpage, assume_yes):
    if dev.mode != "iap":
        sys.exit("flash needs the IAP: run reboot-bl (stock) or press Fn+Esc (QMK) first")
    image = check_image(image)
    app_pid = check_version_page(vpage)
    if app_pid is not None and app_pid != dev.pid - 0x1000:
        print(f"WARNING: version page names app PID {app_pid:04x}, this IAP belongs to {dev.pid - 0x1000:04x}")
    info = dev.info()
    if (info["fw_offset"], info["page_size"]) != (APP_OFFSET, PAGE):
        sys.exit(f"unexpected IAP info {info}")
    if APP_OFFSET + len(image) > info["fw_pages"] * PAGE:
        sys.exit("image is larger than the IAP's writable area")
    # at least the stock app's pages, so a smaller image leaves no stale code behind
    span = max(-(-(APP_OFFSET + len(image)) // PAGE) * PAGE, MIN_ERASE)
    print(f"\nThis ERASES flash {IAP_BASE:#x}..{IAP_BASE + span - 1:#x} on {dev.product} ({dev.path}),")
    print(f"writes the application ({len(image)} bytes) at {IAP_BASE + APP_OFFSET:#x}, verifies it,")
    print(f"and only then writes the version page. The stock IAP at 0x0000..0x2FFF is not touched.")
    if not assume_yes and input("Type 'yes' to continue: ").strip() != "yes":
        sys.exit("aborted; nothing written")
    print("erase")
    dev.erase(0, span)
    print("write application")
    enc = xor_encode(image)
    dev.write(APP_OFFSET, enc)
    got = dev.sum_crc(APP_OFFSET, len(image))
    if got != (checksum(enc), zlib.crc32(enc)):
        sys.exit(f"verify FAILED {got}; version page NOT written, the IAP stays in control. Retry the flash.")
    print("verify OK; write version page")
    dev.write(0, vpage)
    print("done; run reboot-fw to start the application")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        sys.exit(__doc__)
    op, args = argv[0], argv[1:]

    if op == "extract":
        return extract(*args[:2])
    if op == "check":
        check_image(load(args[0]))
        if len(args) > 1:
            pid = check_version_page(load(args[1]))
            print(f"version page names app PID {pid:04x}")
        return print("OK")

    dev = Cykb()
    print(f"device {dev.path}: {dev.product} {dev.mode} ({VID:04x}:{dev.pid:04x})")
    if op == "info":
        print(dev.info())
    elif op == "version":
        if dev.mode != "app":
            sys.exit("version reads only work in the stock application")
        page = dev.version_page()
        for i in range(0, len(page), 32):
            print(f"  {IAP_BASE + i:#06x}: {page[i:i + 32].hex()}")
    elif op == "sum":
        if dev.mode != "iap":
            sys.exit("sum needs the IAP")
        image = load(args[0])
        image += b"\xff" * (-len(image) % 4)
        enc = xor_encode(image)
        want = (checksum(enc), zlib.crc32(enc))
        got = dev.sum_crc(APP_OFFSET, len(image))
        print(f"expected sum {want[0]:08x} crc {want[1]:08x}")
        print(f"device   sum {got[0]:08x} crc {got[1]:08x}")
        print("MATCH" if got == want else "MISMATCH")
    elif op == "dump":
        start = int(args[1], 0) if len(args) > 1 else 0
        end = int(args[2], 0) if len(args) > 2 else FLASH_END
        if os.path.exists(args[0]):
            sys.exit(f"{args[0]} exists; never overwrite a dump")
        out = b""
        addr = start
        while addr < end:
            # last chunk is read 60 bytes back from the end so it never crosses it
            a = min(addr, end - 60)
            out = out[:a - start] + dev.read(a)
            addr = a + 60
            if (addr - start) % 0x1000 < 60:
                print(f"  {addr:#07x}", flush=True)
        out = out[:end - start]
        open(args[0], "xb").write(out)
        print(f"{args[0]}: {len(out)} bytes, SHA-256 {sha256(out)}")
    elif op == "reboot-bl":
        dev.reset(RESET_BL)
    elif op == "reboot-fw":
        dev.reset(RESET_FW)
    elif op == "flash":
        files = [a for a in args if not a.startswith("--")]
        flash(dev, load(files[0]), load(files[1]), "--yes" in args)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
