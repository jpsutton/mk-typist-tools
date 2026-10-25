# MK Typist tools

Host-side tools from the QMK port of the **Mechanical Keyboards MK Typist** (a Ducky One 2 PCB with a Holtek HT32F52352 and the stock Cheng Yong IAP bootloader).

- Research, protocol details, recovery options and safety notes: [jpsutton/mk-typist-research](https://github.com/jpsutton/mk-typist-research)
- QMK keyboard `mk/typist`: branch [`mk-typist`](https://github.com/jpsutton/qmk_firmware/tree/mk-typist) of `jpsutton/qmk_firmware`

These docs only cover how to run the tools. Read the research repo's [Flashing and recovery](https://github.com/jpsutton/mk-typist-research/blob/main/docs/flashing-and-recovery.md) page before writing anything to a keyboard.

Note: The most natural way (in late 2026) to get this running on your own keyboard is to point your favorite AI coding agent at this repo and ask it to build the firmware for you. All the necessary context it needs exists in this repo and the 2 related ones listed above.

## Tools

| Path | What it does |
| --- | --- |
| `cykb.py` | Talks to the stock application and stock IAP over Linux hidraw: info, sum/CRC check, flash, reboot, dump. Also extracts application images and flash-ready version pages from the vendor updater |
| `patch_dump.py` | Patches the stock V1.00.05 application so it can read out all of flash (for backing up the IAP) |
| `keytest.py` | Terminal key tester that draws the board from a QMK `keyboard.json` and reads evdev directly |
| `udev/50-mk-typist.rules` | Lets a logged-in user reach the keyboard's vendor interface and the Holtek ROM ISP |
| `scripts/qmk.sh` | QMK CLI in Docker |
| `scripts/openocd.sh`, `docker/openocd-ht32.Dockerfile` | hansemro's HT32 OpenOCD fork in Docker |
| `scripts/ht32-dfu-tool.sh`, `docker/ht32-dfu-tool.Dockerfile` | hansemro's ROM ISP tool in Docker |
| `scripts/usb_capture.sh` | Saves `lsusb -v` and kernel USB messages |
| `ghidra/` | Headless Ghidra helpers used on the stock firmware |

Requirements: Linux, Python 3.10 or newer (standard library only), and Docker for the `scripts/`.

## Flash QMK

1. Install the udev rule, then replug the keyboard:

   ```sh
   sudo cp udev/50-mk-typist.rules /etc/udev/rules.d/
   sudo udevadm control --reload && sudo udevadm trigger
   ```

2. Download `mk_typist_default-YYYYMMDD.bin` from [Releases](https://github.com/jpsutton/mk-typist-tools/releases) and check it against `SHA256SUMS`. Or build the firmware yourself:

   ```sh
   git clone --recurse-submodules -b mk-typist https://github.com/jpsutton/qmk_firmware.git
   scripts/qmk.sh compile -kb mk/typist -km default
   ```

3. Get the version page from the vendor updater, `MK_Typist_V1.00.05NL.exe`. Download links and its SHA-256 are in the research repo's [Sources](https://github.com/jpsutton/mk-typist-research/blob/main/docs/sources.md#vendor-files-not-redistributed) page. The tool decodes the file but never runs it.

   ```sh
   ./cykb.py extract MK_Typist_V1.00.05NL.exe stock/
   ```

   This writes `stock/0301-US_Layout-V1.00.05-app.bin` (the stock firmware) and `stock/0301-US_Layout-V1.00.05-version.bin`.

4. Put the keyboard in the IAP bootloader (it shows up as `04d9:1301`):
   - stock firmware: `./cykb.py reboot-bl`
   - QMK: hold Esc while plugging in, or press Fn+Esc

5. Flash and start it:

   ```sh
   ./cykb.py info
   ./cykb.py flash qmk_firmware/mk_typist_default.bin stock/0301-US_Layout-V1.00.05-version.bin
   ./cykb.py reboot-fw
   ```

   `flash` checks the image and version page, shows what it will erase and asks for `yes`. It writes the version page only after the image verifies, so a failed flash leaves the IAP in control and you can retry.

To go back to stock, flash `stock/0301-US_Layout-V1.00.05-app.bin` the same way.

## Ducky One 2 (UNTESTED)

> [!WARNING]
> **Nobody has run this firmware on a Ducky One 2.** Everything below comes from static analysis of Ducky's updaters, not from a real board. If it goes wrong, you can lose the stock bootloader for good, and there is no public backup of it. Only try this if you accept that risk.

**Why we think it might work.** The Typist is built on a Ducky One 2 PCB (DK11-ONE02). Ducky's own full-size One 2 updaters (non-backlit DKON1808 and backlit DKON1808S, V1.01.01) use the same Cheng Yong firmware platform. Their keymap table, matrix pins, LED driver pins, SPI flash pins, load address and bootloader header are byte-identical to the Typist's. Details: research repo, [Related boards](https://github.com/jpsutton/mk-typist-research/blob/main/docs/related-boards.md#ducky-one-2-full-size).

**What it does not cover:**

- Any One 2 other than the full-size DKON1808 and DKON1808S. The RGB model has no public firmware to compare. The Mini and SF use a different MCU, and the TKL was not checked.
- Older or regional production runs, which may differ.
- The One 2's bootloader itself. It is not in the updater, so it has never been seen.
- The ISO (EU) extra key. The firmware only has the ANSI layout.
- The backlight. Only the Typist's 4 indicator positions are driven.

**If you try it, run the read-only checks first** and stop at the first surprise:

1. `lsusb` shows `04d9:0296`.
2. `./cykb.py extract One2_NonBacklit_V1.01.01.exe one2/` (or the backlit updater, from [Ducky's downloads page](https://ducky.global/pages/downloads)). This also gives you the stock image for going back.
3. Enter the bootloader with `./cykb.py reboot-bl`. It should show up as `04d9:1296`.
4. `./cykb.py info` should report firmware offset 0x200 and page size 0x200.
5. `./cykb.py sum one2/0296-US_Layout-V1.01.01-app.bin` should print `MATCH`. That proves the bootloader takes the same commands and encoding, assuming your board runs V1.01.01.

Only after all five pass, flash the release firmware with the **One 2's** version page, `one2/0296-US_Layout-V1.01.01-version.bin`. The tool warns that the One 2 is untested. Under QMK the board shows up as `4d4b:5459` "MK Typist". Esc at plug-in or Fn+Esc returns to the bootloader, if the matrix really is the same.

The worst case is firmware that starts but has a wrong matrix or broken USB. Then neither key combo reaches the bootloader. The only way out is the Holtek ROM ISP mass erase, which deletes the stock bootloader. `patch_dump.py` only knows the Typist's stock firmware, so it cannot back up a One 2's bootloader first.

Please open an issue with your results, good or bad.

## Other commands

```sh
./cykb.py check image.bin version.bin  # offline: run the pre-flash checks
./cykb.py version                      # stock app only: show the version page
./cykb.py sum stock/0301-…-app.bin     # IAP only: is this image what is installed? (read-only)
./patch_dump.py stock/0301-…-app.bin dumpread.bin
./cykb.py dump flash.bin               # after flashing dumpread.bin: read 0x0..0x1FDFF
sudo ./keytest.py qmk_firmware/keyboards/mk/typist keytest.log
```

## CI and releases

- **CI** (`.github/workflows/ci.yml`) runs on every push and pull request. It runs the unit tests on Python 3.10 and 3.13 and ShellCheck. It also builds `mk/typist:default` from `jpsutton/qmk_firmware@mk-typist` in the QMK CLI container and runs `cykb.py check` on the result.
- **Release** (`.github/workflows/release.yml`) is started by hand from the Actions tab. It runs CI, then publishes a release tagged with the UTC date (`YYYYMMDD`) containing the firmware and `SHA256SUMS`. The release notes link the exact QMK and tools commits. One release per day; a second run on the same day fails.

## Status

- Tested on one MK Typist with stock V1.00.05. `cykb.py` was cleaned up for publishing after that testing. Its protocol code is unchanged, but the new checks and the `extract` command have only been tested offline against the vendor updaters.
- Ducky One 2 IDs (`04d9:0296` and `04d9:1296`) are recognised but untested. See [Ducky One 2 (UNTESTED)](#ducky-one-2-untested).
- Linux only.

## Credits and license

The CYKB protocol, the `maaV102` updater format and the XOR key come from [pok3rtool](https://github.com/pok3r-custom/pok3rtool) (GPL-3.0). The Docker images build [hansemro/openocd-ht32](https://github.com/hansemro/openocd-ht32) and [hansemro/ht32-dfu-tool](https://github.com/hansemro/ht32-dfu-tool). Full credits are in the research repo.

GPL-3.0-or-later, see [LICENSE](LICENSE). Vendor files are not included.
