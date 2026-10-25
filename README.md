# legopollinator: The Pollination Problem

Firmware for the GTAC **robot pollinator**'s LMS-ESP32 board, the SPIKE hub
program, and the activity's website (`newsite/`). The iPad stays on the
school's Wi-Fi, opens the remote from the website in the **Bluefy** app, and
connects to the robot over **Bluetooth**; the board passes the remote's
commands to the SPIKE hub through port A.

(Branch `main` has the Wi-Fi version, where each board runs its own hotspot
that the iPad joins. This branch removes all of that: the board's Wi-Fi is
never turned on.)

| Port | Motor |
|---|---|
| A | the GTAC board |
| C | right wheel (as seen from behind the robot) |
| D | left wheel (mounted mirrored) |
| E | the pollination arm |

| Part | Where | Runs on |
|---|---|---|
| The remote: d-pad, slider, code blocks | `newsite/roboarm_mini/remote/` | the iPad, in Bluefy (from GitHub Pages) |
| Firmware: Bluetooth link, the "distance sensor" | `app/`, `firmware/` | the LMS-ESP32 board |
| Hub program | `SPIKE code/pollinator-spike.py` | the SPIKE Prime hub, program slot 0 |
| Provisioning | `tools/provision.py` | the computer that flashes the boards |

## For students

1. Start program 0 on the hub (03/05 in the robot instructions).
2. On the iPad, open the **Bluefy** app and go to the remote
   (`…/newsite/roboarm_mini/remote/` on the website, or **Open the remote** on
   robot instructions 04/05).
3. Tap **Connect your robot**, choose the robot's name (e.g. **ROBOT 7**),
   and tap **Pair**. The button turns green: **Connected: ROBOT 7**.

Safari can't use Bluetooth from a web page; Bluefy (free on the App Store)
can. Only one iPad can connect to a robot at a time. If the link drops (out
of range, the board restarted), the remote reconnects by itself; the motors
stop as soon as the iPad goes.

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

The hub shows **P** when the board is connected and **?** while it waits.

### If the robot drives the wrong way

At the top of `SPIKE code/pollinator-spike.py`, `DIRECTIONS = (1, 1, -1, 1, 1)`
sets forward for B, C, D, E, F. If UP drives backwards, flip the signs of both
C and D; if UP spins the robot on the spot, flip just one of them. Wheel speeds
are `DRIVE_SPEEDS` (slow, medium, fast in degrees per second); the page's
blocks use the same numbers (`DRIVE_DPS` in the blocks) to time their moves.

## How the remote, board and hub talk

**Remote ↔ board (Bluetooth, `app/ble.py`).** The board advertises a GATT
service `8f3a0001-5e0b-4c8e-9a1d-7c2b3e4f5a60` under its name (from its
`config.py`). The page writes lines to RX (`…0002`, write without response)
and gets lines back as notifications on TX (`…0003`):

- page → board, every 0.5 s and on every change: `x=1&m=<five run states>`,
  plus commands: `c=drive&w=f|b|l|r&g=<wheel degrees>&v=<speed 0-2>`,
  `c=turn&k=<motor>&g=<degrees>&v=…`, `c=go&k=…&a=<angle>&d=<direction>&v=…`,
  `c=home`, `c=stop`. Run states: 0 stop, 1–3 forward slow / medium / fast,
  4–6 back, for motors B–F.
- board → page: `h 1 B <fitted-motors mask>` (at most once a second, in reply),
  `p <motor> <angle>` positions and `b <motor> <angle>` homes as they change.

The page is "connected" while it has had a line from the board in the last
2.5 s. If the board hears nothing for 3 s, or the iPad disconnects, every
motor stops.

**Board → hub.** The board pretends to be a LEGO Distance Sensor on hub
**port A**.

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
- **Hub → board**: the sensor's four lights. `1, on` the Wi-Fi message (ignored); `2, motor, angle÷100,
  angle%100` a position; `3, …` a home position; `4, 1, 0, fitted-motors mask`
  status; `5, percent, mV÷100, mV%100` battery (8050 mV is sent as 80, 50).


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

The first time, it asks for the name before each board's number (e.g.
`ROBOT`, so boards become ROBOT 1, ROBOT 2, ...) and keeps it in
`tools/site.json` (ignored by git). Then, for each board, it asks you to plug
it in, and:

1. reads its MAC address and picks its number: the next free one, or the
   same as last time if this board has been flashed before;
2. wipes it and flashes `firmware/dist/legopollinator.bin`;
3. writes `config.py` (its name) and `main.py`;
4. watches it boot and checks Bluetooth comes on under its name;
5. tells you the name to put on the label, and asks for the next board.

Numbers are remembered in `tools/boards.csv`. Each board takes about 30 s.

```bash
python tools/provision.py --start 12      # new boards from 12
python tools/provision.py --number 7      # one board as number 7 (a replacement)
python tools/provision.py --port COM8     # use this port instead of waiting for a new board
python tools/provision.py --ask           # a different name prefix
```

### Updating boards that are already set up

A new release is just a new `firmware/dist/legopollinator.bin`. Flash it
without erasing, which keeps the board's name:

```bash
python -m esptool --port COM8 write-flash -z 0x1000 firmware/dist/legopollinator.bin
```

Boards set up with the Wi-Fi firmware keep their name too: the Bluetooth
firmware reads `WIFI_NAME` from their `config.py` when there is no
`ROBOT_NAME`. To go back to Wi-Fi, flash `main`'s `legopollinator.bin` the
same way.

### The hub program

Load `SPIKE code/pollinator-spike.py` onto each hub: in the SPIKE App, a new
Python project, paste the file in, and download it to program slot **0**.

### On Windows (PowerShell)

Provisioning only needs Python and the committed firmware, not the build
toolchain. Install Python 3 from python.org (tick **Add python.exe to
PATH**), then:

```powershell
py -m pip install esptool mpremote
py tools\provision.py
```

If a plugged-in board doesn't appear as a **COM** port in Device Manager,
install the driver for its USB chip (WCH CH340/CH9102 or Silicon Labs
CP210x). Close Thonny first: it holds the COM port.

## Building the firmware

```bash
firmware/build.sh               # -> firmware/dist/legopollinator.bin
firmware/build.sh xiao-test     # -> firmware/dist/legopollinator-xiao-test.bin
```

MicroPython v1.29.0 with its Bluetooth (NimBLE) stack, and the app frozen
in. The first run downloads MicroPython and ESP-IDF v5.5.2 and installs the
Xtensa toolchain (about 3 GB, into `~/esp/legodisco-deps`, shared with
legodisco, and `~/.espressif`).

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

## The remote (the website)

The remote is plain files in `newsite/roboarm_mini/remote/`, served by GitHub
Pages over HTTPS (Web Bluetooth needs HTTPS): `index.html`, `app.js` (the
remote, the Bluetooth link), `blockly.js` (Blockly, with the pollinator's
blocks at the end), `style.css`. Edit them and push; nothing is built.

To try the remote on this computer with a pretend board:

```bash
python tools/mock_board.py        # then open http://localhost:8765
```

On `localhost` the page talks to the pretend board over HTTP instead of
Bluetooth. `http://localhost:8765/log` shows what the page sent;
`/shot` and `/shot?code` are for screenshots (see the top of
`tools/mock_board.py`).

| Path | What |
|---|---|
| `app/arm.py` | the pollinator program (keeps the arm's file name, so boards' `main.py` is unchanged): hub commands, the remote's messages |
| `app/ble.py` | the Bluetooth link to the remote |
| `app/lump.py` | the Distance Sensor that the hub sees (LEGO's LUMP protocol); picks the board's LEGO port pins |
| `app/simhub.py` | fake hub for the test board (see below) |
| `app/main.py` | two lines on the board's filesystem that start `arm` |
| `app/config.py` | not in the repo: the board's name, written by `tools/provision.py` |
| `firmware/board/LEGODISCO/` | MicroPython board definition: Bluetooth on, the app frozen in |
| `firmware/board/XIAO_S3_TEST/` | same app on a XIAO ESP32S3, hub simulated |
| `SPIKE code/pollinator-spike.py` | the hub program |
| `tools/provision.py` | flash and name a set of boards |
| `tools/mock_board.py` | the remote on your computer with a pretend board |
| `newsite/roboarm_mini/` | the website: index, robot instructions, code your controller, the remote, the 3D pollinator |

## Testing on a spare XIAO ESP32S3

`firmware/dist/legopollinator-xiao-test.bin` is the same firmware for a XIAO
ESP32S3 with `SIMULATE = True`, which swaps in `app/simhub.py`: a fake hub
(motors C, D and E). Connect to it from the remote like a real robot.

```bash
python tools/provision.py --chip esp32s3 --simulate \
    --firmware firmware/dist/legopollinator-xiao-test.bin --number 99
```

## If a robot doesn't connect

Over USB (Thonny or a serial monitor), a healthy start prints:

```
STA-MAC 14:2b:2f:b3:55:10
Bluetooth on: ROBOT 7
Python heap free 123 KB; system RAM free 79 of 249 KB (lowest 79 KB)
Sensor pins: rx=8, tx=7        (18/19 on a v1 board)
Hub connected                   (a "did not answer" or two first is normal)
```

- Not in Bluefy's list: is another iPad connected to it? Is the board on
  (the hub powers it through port A, so the hub must be on)?
- Connected but the motors don't move: check the cable in port A, and that
  the hub is running program 0 (it shows **P**).

## Design notes

**The two board versions.** The v2's ESP32-PICO-V3-02 has its flash on
different pins from the v1's WROVER, which frees GPIO 7/8 for the LEGO port
(18/19 on the v1). `lump.py` reads the chip's flash-pin eFuse to choose.
Flash runs in dual (DIO) mode: in quad mode one of the v2's flash data lines
is GPIO 18, and setting that pin up resets the board in a loop.

**No PSRAM, no Wi-Fi.** The Wi-Fi radio is never started, so its buffers are
set to the minimum and their RAM goes to Python and Bluetooth; PSRAM isn't
needed. CPU at 240 MHz, flash at 80 MHz, 1 ms scheduler tick.

## Credits

`lump.py`'s connect sequence follows `lpf2.py` from Anton Vanhoucke's
PUPRemote project (GPL).
