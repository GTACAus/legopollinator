# legopollinator: The Pollination Problem

Firmware for the GTAC **robot pollinator**'s LMS-ESP32 board, which also shares
the internet, plus the hub program and the activity's website (`newsite/`).
The iPad joins the board's own Wi-Fi (e.g. **ROBOT 7**) and can both browse the
web and drive the robot, so students don't switch between the robot's Wi-Fi and
the site's Wi-Fi.

Made from the robot arm's firmware (legodisco): the same boards, Wi-Fi and
provisioning, with the muscle sensor removed and a remote and code blocks for a
driving robot:

| Port | Motor |
|---|---|
| A | the GTAC board |
| C | right wheel (as seen from behind the robot) |
| D | left wheel (mounted mirrored) |
| E | the pollination arm |

Runs on the **LMS-ESP32 v2** (ESP32-PICO-V3-02), the boards in use, and on the
older v1 (ESP32-WROVER): the firmware tells them apart by itself.

No Wi-Fi names or passwords are in this repo or the firmware: they are
entered when the boards are flashed (see [Flashing a classroom set](#flashing-a-classroom-set))
and live only in each board's `config.py`.

Three parts work together:

| Part | Where | Runs on |
|---|---|---|
| Firmware: hotspot, internet sharing, the iPad page, the "distance sensor" | `app/`, `firmware/` | the LMS-ESP32 board |
| Hub program | `SPIKE code/pollinator-spike.py` | the SPIKE Prime hub, program slot 0 |
| Provisioning | `tools/provision.py` | the computer that flashes the boards |

This repo is also copied into the website as `newsite/roboarm_mini/lms_esp32/`.

## For students

| | |
|---|---|
| Wi-Fi | the name on the board (e.g. **ROBOT 7**), with the hotspot password set when flashing |
| Remote | **http://gtac.local** or **http://10.10.10.10** (or the "Robot arm" app) |
| Internet | works as normal while on the board's Wi-Fi |

Every board answers to `gtac.local` on its own Wi-Fi, so the address is the
same for every robot. If the hotspot password differs from the one on the
printed QR codes, reprint them.

### The page (The Pollination Problem)

- **Basic**: hold a control to move. The starting remote has **D-pad 1** on
  the wheels (up / down: C and D forward / back; left / right: a pivot turn,
  only C or only D drives) and **slider 2** on the arm (E back and forth).
  In ⚙ settings a control's axis can be set to **Wheels (C + D)** or any one
  motor. **✎ Change remote** turns the board into a canvas: drag controls
  anywhere, ⚙ sets one up, ✕ removes it, up to 5. **⌂ Home** sends the arm
  home (the wheels stay put).
- **Advanced (code)**: each press of a control runs its Blockly script once.
  On this page the program is always running (there's no Run button); in the
  code canvas it has Run / Stop, plus *Hide remote* and *↺ Reset canvas*.
- **Blocks**: *Movement* (both wheels): **move forward / backward / left / right for
  [3] cm / seconds** and **set movement speed**. *Motors*: **rotate [motor]
  forwards / backwards for [3] seconds / degrees**, set speed, go to position, start,
  stop, move the arm home, stop all. Then Events, Control, Sensing, Operators.
  Centimetres use the 88 mm wheel (49295): 1 cm = 13.0 degrees of wheel turn.
  The starting program: forward / backward move 3 cm, left / right turn for 1 second,
  the slider rotates E for 1 second.

Remote layouts and programs are kept until the iPad's tab is closed.

### Hub buttons (while the hub program runs)

| Button | Does |
|---|---|
| Left | scrolls the battery level across the lights (also printed in the SPIKE App console) |
| Both, for 1 second | the board's Wi-Fi on / off message (the board ignores it: its hotspot stays on) |

The hub shows **P** when the board is connected and **?** while it waits.

### If the robot drives the wrong way

At the top of `SPIKE code/pollinator-spike.py`, `DIRECTIONS = (1, 1, -1, 1, 1)`
sets forward for B, C, D, E, F. If UP drives backwards, flip the signs of both
C and D; if UP spins the robot on the spot, flip just one of them. Wheel speeds
are `DRIVE_SPEEDS` (slow, medium, fast in degrees per second); the page's
blocks use the same numbers (`DRIVE_DPS` in the blocks) to time their moves.

## How it behaves

- **Hotspot always on.** It comes up at power-up; the hub's Wi-Fi on/off
  message is ignored, so a SPIKE program ending can't cut the iPad's internet.
- **Internet from the site's Wi-Fi (the "uplink").** The board joins the
  strongest access point of the uplink network and shares it with NAT, in C
  (module `repeater`), so forwarding never waits on the Python loop. The
  forwarding runs on CPU core 0 and the arm's Python on core 1.
- **While the remote is open, the uplink is left alone.** No scans or
  reconnects, because a scan pauses the hotspot for about 1.5 s, which could
  trip the stop-all-motors safety rule. If the uplink drops while driving,
  the board reconnects once the page is closed.
- **While the remote is closed,** the Python loop checks the web server
  every 20 ms instead of continuously. The hub link keeps running, since the
  hub needs its "distance sensor" at all times.
- **Joining the hub never stalls the page.** With no hub answering, each try
  takes about 6 s; it runs a step at a time, so the web server keeps working.
- **Stuck connections are cleared.** A page download or live link that makes
  no progress for 10 s (an iPad that slept or left) is closed, so it can't tie
  up sockets and memory.
- **If the uplink is down** (or none was set), the iPad is given the board as
  its DNS server and gets the old captive pop-up, so the robot still works
  offline. Leases last 2 minutes, so an iPad switches between captive and
  internet within about a minute of the uplink coming or going.
- **Only the hotspot can reach the robot.** The web server listens on
  10.10.10.10 only, so other devices on the uplink network can't drive it.

## How the board and the hub talk

The board pretends to be a LEGO Distance Sensor on hub **port A**.

- **Board → hub**: the distance reading. 50 mm is "idle" (the board is there,
  the remote is closed: after 1.5 s of it the hub stops any running motor);
  1100 + 5 × *code* is a command. Codes: 0–34 a motor's run state (motor × 7 +
  state: 0 stop, 1–3 forward slow / medium / fast, 4–6 back), 35 stop all,
  36 home (the arm; not the wheels), 37 re-read homes, 38–40 drive header
  (+ speed), 43–87 go-to header, 88–159 a value in 5° steps, 160–174 turn
  header. A drive is its header then two values: pattern × 18 + full turns
  (pattern 0 forward, 1 back, 2 left: C only, 3 right: D only), then the rest
  of the degrees in 5° steps; each wheel turns that many degrees. A command is
  held for two of the hub's reads; the same code twice in a row needs a
  different reading between.
- **Hub → board**: the sensor's four lights. `1, on` Wi-Fi; `2, motor, angle÷100,
  angle%100` a position; `3, …` a home position; `4, 1, 0, fitted-motors mask`
  status; `5, percent, mV÷100, mV%100` battery (8050 mV is sent as 80, 50).

The page asks the board with `c=drive&w=f|b|l|r&g=<wheel degrees>&v=<speed 0-2>`,
next to the arm's `c=turn`, `c=go`, `c=home` and `c=stop`, and `m=` with the
five motors' run states.

Use the matching hub program: the robot arm's program (`arm-spike-app3.py`)
doesn't know the drive command and treats the idle reading as a muscle signal.

## Flashing a classroom set

One-time setup on the computer:

```bash
pip install esptool mpremote
```

Then, with Thonny closed:

```bash
python tools/provision.py
```

The first time, it asks for the Wi-Fi settings:

| Setting | Example |
|---|---|
| Hotspot name, before the number | `ROBOT` (boards become ROBOT 1, ROBOT 2, ...) |
| Hotspot password | what students type, or what's on the QR codes |
| Network to share internet from | the site's Wi-Fi name (empty for none) |
| Its password | hidden as you type |

and offers to keep them in `tools/site.json` (ignored by git) so later
sessions don't ask again. Use `--ask` to change them.

Then, for each board, it asks you to plug it in, and:

1. reads its MAC address and picks its number: the next free one, or the
   same as last time if this board has been flashed before;
2. wipes it and flashes `firmware/dist/legopollinator.bin`;
3. writes `config.py` (its name and the Wi-Fi settings) and `main.py`;
4. watches it boot and checks its hotspot comes up;
5. tells you the name to put on the label, and asks for the next board.

Numbers are remembered in `tools/boards.csv`. Each board takes about 30 s,
because the whole app, page files included, is in the one firmware image.

```bash
python tools/provision.py --start 12      # new boards from 12
python tools/provision.py --number 7      # one board as number 7 (a replacement)
python tools/provision.py --port COM8     # use this port instead of waiting for a new board
python tools/provision.py --ask           # enter different Wi-Fi settings
```

To move boards to another site's Wi-Fi, re-run with `--ask` and the new
settings; each board keeps its number.

### Updating boards that are already set up

`main.py` hasn't changed, so a new release is just the new
`firmware/dist/legopollinator.bin`. Either re-run `provision.py` (wipes the board
and writes its settings again), or flash without erasing, which keeps the
board's name and Wi-Fi settings:

```bash
python -m esptool --port COM8 write-flash -z 0x1000 firmware/dist/legopollinator.bin
```

Then load the matching hub program onto each hub (below).

### The hub program

Load `SPIKE code/pollinator-spike.py` onto each hub: in the SPIKE App, a new
Python project, paste the file in, and download it to program slot **0**.
When it starts, its console says where it reads the battery from, or that the
hub doesn't report it.

### On Windows (PowerShell)

Provisioning only needs Python and the committed `firmware/dist/legopollinator.bin`,
not the build toolchain.

1. Install Python 3 from python.org and tick **Add python.exe to PATH**.
2. Install the tools and run the script (`py` is Windows' Python launcher;
   `python` also works if it's on the PATH):

   ```powershell
   py -m pip install esptool mpremote
   py tools\provision.py
   ```

3. If a plugged-in board doesn't appear as a **COM** port in Device Manager,
   install the driver for its USB chip (WCH CH340/CH9102 or Silicon Labs
   CP210x; Device Manager shows which).
4. Close Thonny first: it holds the COM port.

### Getting IT to allow the boards online

The uplink network may only let known devices onto the internet. As the
boards are flashed, provisioning writes **`tools/authorization-request.txt`**:
a ready-to-send list of the boards and their MAC addresses to give IT. Because
each board NATs its iPad, only these board addresses ever appear on the uplink
network, so that one list is all IT needs. Fill in the name/contact lines at
the top before sending.

A board that is on the uplink but not yet allowed joins it and gets no address
(`/stats` shows it not connected).

Rebuild the list at any time without flashing:

```bash
python tools/provision.py --authorization
```

## Building the firmware

```bash
firmware/build.sh
```

The first run (shared with legodisco, so already done on a computer that has built it) downloads MicroPython v1.29.0 and ESP-IDF v5.5.2 and installs
the Xtensa toolchain (about 3 GB in all, into `~/esp/legodisco-deps` and
`~/.espressif`; override the former with `LEGODISCO_DEPS`). Output:
`firmware/dist/legopollinator.bin`.

### On Windows: WSL

The build needs Linux or macOS. On Windows, use Ubuntu in WSL:

```powershell
wsl --install -d Ubuntu      # once; then create a user and type exit
wsl -d Ubuntu                # opens Ubuntu from PowerShell (exit to leave)
```

Once, inside Ubuntu:

```bash
sudo apt update && sudo apt install -y build-essential git make python3 python3-pip python3-venv cmake ninja-build libusb-1.0-0 wget flex bison gperf ccache libffi-dev libssl-dev dfu-util
```

Then build from the repo's Windows folder, e.g.
`cd /mnt/c/Users/<you>/Documents/GitHub/legopollinator && bash firmware/build.sh`, and
flash from PowerShell (WSL can't see the COM ports). If the script fails with
`$'\r': command not found`, Git gave it Windows line endings:
`sed -i 's/\r$//' firmware/build.sh`.

After the first build, back Ubuntu up (with its 3 GB of tools) so it never
has to be set up again:

```powershell
wsl --export Ubuntu C:\Users\<you>\Documents\wsl-ubuntu-backup.tar
wsl --import Ubuntu C:\Users\<you>\wsl\Ubuntu C:\Users\<you>\Documents\wsl-ubuntu-backup.tar   # to restore
```

### Changing the page

The page files are kept gzipped in `app/www` (`app.js.gz`, `blockly.js.gz`
with the blocks at its end, `index.html.gz`, `style.css.gz`). Unzip, edit,
gzip again, then build: `tools/make_www.py` (run by `build.sh`) packs them
into the firmware and stamps `blockly.js?v=` in `app.js`, so iPads fetch a
changed `blockly.js` instead of a cached one.

To try the page without a board:

```bash
python tools/mock_board.py        # then open http://localhost:8765
```

It serves the page with a pretend board and hub behind it;
`http://localhost:8765/log` shows what the page sent.

| Path | What |
|---|---|
| `app/arm.py` | the pollinator program (keeps the arm's file name, so boards' `main.py` is unchanged): hub commands, page messages, hub status for `/stats` |
| `app/config.py` | not in the repo: written to each board by `tools/provision.py` |
| `app/web.py` | hotspot, uplink, web server, WebSocket, `/stats`; serves page files from flash |
| `app/lump.py` | the Distance Sensor that the hub sees (LEGO's LUMP protocol); picks the board's LEGO port pins |
| `app/simhub.py` | fake hub for the test board (see below) |
| `app/main.py` | two lines on the board's filesystem that start `arm` |
| `app/www/` | the iPad page (gzipped) |
| `firmware/modules/repeater/` | C module: uplink, NAT, DNS hand-out, `gtac.local` responder |
| `firmware/board/LEGODISCO/` | MicroPython board definition and speed settings |
| `firmware/board/XIAO_S3_TEST/` | same app on a XIAO ESP32S3, hub + sensor simulated |
| `SPIKE code/pollinator-spike.py` | the hub program |
| `tools/provision.py` | flash and name a set of boards |
| `tools/make_www.py` | packs `app/www` into the firmware |
| `tools/mock_board.py` | the page on your computer with a pretend board |
| `newsite/roboarm_mini/` | the website: index, robot instructions, code your controller, the 3D pollinator |

## Testing the site on a spare XIAO ESP32S3

You can try the whole site — hotspot, web pages, `gtac.local`, internet
sharing — on a XIAO ESP32S3 with no arm attached. A build of the same app for
that chip is committed at `firmware/dist/legopollinator-xiao-test.bin`; it sets
`SIMULATE = True`, which swaps in `app/simhub.py`: a fake LEGO hub (motors C,
D and E, and a pretend battery). Driving on the page moves the position
readouts; drive, turn, go-to and home move by an angle.

```bash
python tools/provision.py --chip esp32s3 --simulate \
    --firmware firmware/dist/legopollinator-xiao-test.bin --number 99
```

(The XIAO's firmware flashes at offset `0x0`, which `--chip esp32s3` selects.)
Then join its hotspot and open `http://gtac.local`. Leave `--uplink` empty
when asked to test the captive-portal path, or give it a network to test
internet sharing.

What this covers: the networking, the web UI and the command protocol between
page and board. What it can't cover: the real hub's UART timing and the real
board's exact Wi-Fi performance. The committed
test image can lag behind; rebuild it with `firmware/build.sh xiao-test`.

## Diagnostics: /stats

On the hotspot, **http://gtac.local/stats** (or `http://10.10.10.10/stats`)
shows the board's diagnostics, refreshed every 3 s:

- the uplink network, signal, radio, the board's address on it, throughput;
- **Hub link** (connected or not) and **Hub battery** (percent, volts, how long
  ago; "charge soon" under 20 %);
- the hotspot, its clients, chip temperature, uptime, and free RAM now and
  lowest;
- a **Scan for Wi-Fi** button (pauses the internet for a moment).

`gtac.local` resolves on iPads and Macs; on Android, which doesn't resolve
`.local`, use `http://10.10.10.10/stats`. The uplink network can only be
changed by re-provisioning (`provision.py --ask`).

### If a robot stops responding

Open `/stats` before resetting anything:

- **Hub link not connected**: check the cable in port A, and that the hub is
  on and running program 0.
- **Hub battery low**: charge the hub; motors weaken below about 7 V.
- **Lowest free RAM** under about 20 KB: the board is short of memory.

Over USB (Thonny or a serial monitor), a healthy start prints:

```
Wi-Fi on: ROBOT 7 -> http://10.10.10.10 or http://gtac.local, internet via <uplink>
Sensor pins: rx=8, tx=7        (18/19 on a v1 board)
Hub connected                   (a "did not answer" or two first is normal)
Internet via <uplink>: up, -NN dBm
```

## Design notes

**The two board versions.** The v2's ESP32-PICO-V3-02 has its flash on
different pins from the v1's WROVER, which frees GPIO 7/8 for the LEGO port
(18/19 on the v1). `lump.py` reads the chip's flash-pin eFuse to choose.
Flash runs in dual (DIO) mode: in quad mode one of the v2's flash data lines
is GPIO 18, and setting that pin up resets the board in a loop.

**No PSRAM.** The boards' PSRAM (8 MB on the v1's WROVER, 2 MB on the v2) is
deliberately unused:

- On the original ESP32, PSRAM needs a compiler workaround for a chip bug that
  adds instructions throughout the code (slower everywhere) and makes the
  firmware too big for IRAM, so MicroPython's PSRAM build turns off the Wi-Fi
  fast paths and compiles for size.
- MicroPython would put the whole Python heap in PSRAM, which is reached
  through the same small cache as the program. The muscle-sensor maths
  allocates a heap object for every float, so the arm loop and garbage
  collection slow down.
- What PSRAM buys is memory headroom, and dropping Bluetooth plus freezing
  the app into flash leaves enough internal RAM for Python, the Wi-Fi buffers
  and the NAT table.

The boot log prints free memory (`Python heap free ... system RAM free ...
(lowest ...)`). If the lowest system RAM falls under about 20 KB while an
iPad is browsing, there is a fallback build that uses PSRAM without the
workaround (rev 3 chips only). It gives up the Wi-Fi receive fast path to fit,
so it is slower on the network side, and it hasn't been tried on the v2:

```bash
firmware/build.sh PSRAM     # -> firmware/dist/legopollinator-psram.bin
python tools/provision.py --firmware firmware/dist/legopollinator-psram.bin
```

**Speed settings** (`firmware/board/LEGODISCO/sdkconfig.board` and
`firmware/board/sdkconfig.fast`):

- CPU at 240 MHz (MicroPython's default is 160 MHz).
- Flash at 80 MHz, since Python runs from flash.
- Wi-Fi and lwIP forwarding paths in IRAM.
- Bigger Wi-Fi aggregation windows, more Wi-Fi buffers and a 32 KB TCP window
  for faster browsing, kept within a safe RAM margin.
- 1 ms scheduler tick.
- Wi-Fi power saving off; 40 MHz channels where the router allows (20 MHz
  otherwise).
- IPv4 only.

**Smaller and faster to boot:** Bluetooth is removed, MicroPython's own mDNS
is replaced by a tiny responder that answers IPv6 lookups with "none" (which
avoids a 2–5 s stall on the iPad's first lookup), and the app is frozen into
flash.

## Credits

`lump.py`'s connect sequence follows `lpf2.py` from Anton Vanhoucke's
PUPRemote project (GPL). The `gtac.local` responder and repeater logic come
from the tinywifi XIAO repeater.
