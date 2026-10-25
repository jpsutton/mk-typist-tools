# MK Typist tools

Host-side tools from the QMK port of the **Mechanical Keyboards MK Typist** (a Ducky One 2 PCB with a Holtek HT32F52352 and the stock Cheng Yong IAP bootloader).

- Research, protocol details, recovery options and safety notes: [jpsutton/mk-typist-research](https://github.com/jpsutton/mk-typist-research)
- QMK keyboard `mk/typist`: branch [`mk-typist`](https://github.com/jpsutton/qmk_firmware/tree/mk-typist) of `jpsutton/qmk_firmware`

These docs only cover how to run the tools. Read the research repo's [Flashing and recovery](https://github.com/jpsutton/mk-typist-research/blob/main/docs/flashing-and-recovery.md) page before writing anything to a keyboard.

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

2. Build the firmware:

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

## Other commands

```sh
./cykb.py version                      # stock app only: show the version page
./cykb.py sum stock/0301-…-app.bin     # IAP only: is this image what is installed? (read-only)
./patch_dump.py stock/0301-…-app.bin dumpread.bin
./cykb.py dump flash.bin               # after flashing dumpread.bin: read 0x0..0x1FDFF
sudo ./keytest.py qmk_firmware/keyboards/mk/typist keytest.log
```

## Status

- Tested on one MK Typist with stock V1.00.05. `cykb.py` was cleaned up for publishing after that testing. Its protocol code is unchanged, but the new checks and the `extract` command have only been tested offline against the vendor updaters.
- Ducky One 2 IDs (`04d9:0296` and `04d9:1296`) are recognised but untested. See the research repo's [Related boards](https://github.com/jpsutton/mk-typist-research/blob/main/docs/related-boards.md#ducky-one-2-full-size) page before trying one.
- Linux only.

## Credits and license

The CYKB protocol, the `maaV102` updater format and the XOR key come from [pok3rtool](https://github.com/pok3r-custom/pok3rtool) (GPL-3.0). The Docker images build [hansemro/openocd-ht32](https://github.com/hansemro/openocd-ht32) and [hansemro/ht32-dfu-tool](https://github.com/hansemro/ht32-dfu-tool). Full credits are in the research repo.

GPL-3.0-or-later, see [LICENSE](LICENSE). Vendor files are not included.
