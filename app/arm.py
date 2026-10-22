# The Pollination Problem: LMS-ESP32 firmware for the robot pollinator. main.py on the board
# runs it at power-up (the module keeps the name arm.py, so boards set up for the robot arm
# start it unchanged).
#
# At power-up the board is a plain LEGO Distance Sensor that reads "idle", and its Wi-Fi hotspot
# comes up with internet shared from the uplink network. The iPad stays on the hotspot: it can
# browse, or open the remote to drive the pollinator and run Blockly programs.
# How the board, hub and page talk: README.md.
#
# This module, lump.py, web.py and the page files (www_data.py) are frozen into the firmware;
# the board's filesystem only holds main.py and config.py.

import utime
import machine
import gc
import esp32
import repeater
from lump import Lump, LIGHT

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
DEBUG = False           # True prints every message from the hub
try:
    from config import SIMULATE   # True on a test board: fake the hub
except ImportError:
    SIMULATE = False
# ---------------------------------------------------------------------------

MOTORS = "BCDEF"
IDLE_MM = 50                        # the reading while nobody is driving: "I'm here"
CMD_MM, CMD_STEP = 1100, 5          # commands: mm = 1100 + 5 x code
STOP_ALL, HOME, REBASE, DRIVE_HEAD, GO_HEAD, GO_ANGLE, TURN_HEAD = 35, 36, 37, 38, 43, 88, 160
DRIVES = "fblr"                     # drive patterns: forward, back, left, right (pivot turns)
FRAME_MS = 30                       # remote: each motor's state is repeated in turn this often
HOLD_MS = 15                        # shortest hold of a command, so the hub reads it twice
IDLE_MS = 20                        # idle reading update rate
STATUS_MS = 1000                    # uplink status check interval (printed when it changes)
IDLE_POLL_MS = 20                   # web server check interval while the remote page is closed


class Arm:
    def __init__(self):
        self.sensor = None
        self.web = None
        self.states = [0] * 5           # remote run state of motors B..F
        self.queue = []                 # command codes waiting to go to the hub
        self.rotate = 0
        self.remote = False             # the remote page is open
        self.battery = None             # (percent, millivolts, when) from the hub, if its program reports it
        self.positions = [-1] * 5
        self.baselines = [-1] * 5
        self.hub = "h 1 B 0"
        self.last_send = utime.ticks_ms()
        self.last_mm = 0                # the hub only notices a change, so never send the same command twice in a row

    # ---------- messages from the hub (its distance sensor lights)
    def hub_wrote(self, mode, data):
        if mode != LIGHT or len(data) < 4:
            return
        kind, a, b, c = data[0], data[1], data[2], data[3]
        # kind 1 (Wi-Fi on/off) is ignored: the hotspot stays on, since the iPad's internet
        # depends on it, and a hub program ending must not cut it off.
        if kind in (2, 3) and a < 5:
            angle = b * 100 + c
            (self.positions if kind == 2 else self.baselines)[a] = angle
            self.tell("%s %s %d" % ("p" if kind == 2 else "b", MOTORS[a], angle))
        elif kind == 5:                 # battery: percent, then volts as two 2-digit halves (8.05 V = 80, 50)
            self.battery = (a, b * 100 + c, utime.ticks_ms())
        elif kind == 4:
            self.hub = "h %d %s %d" % (a, MOTORS[b] if b < 5 else "B", c)
            self.tell(self.hub)

    def hub_status(self):
        """For the /stats page: is the hub talking, and its battery (None if never reported)."""
        s = self.sensor
        battery = None
        if self.battery:
            pct, mv, when = self.battery
            battery = (pct, mv, utime.ticks_diff(utime.ticks_ms(), when) // 1000)
        return {"connected": bool(s and getattr(s, "connected", True)), "battery": battery}

    def tell(self, line):
        if self.web:
            self.web.broadcast(line)

    # ---------- messages from the page
    def page(self, p):
        if "m" in p and len(p["m"]) == 5:
            for i in range(5):
                s = ord(p["m"][i]) - 48
                if 0 <= s <= 6 and s != self.states[i]:
                    self.states[i] = s
                    if i not in self.queue:
                        self.queue.append(i)       # a motor index: its state goes out next
        c = p.get("c")
        if c == "stop":
            self.release()
        elif c == "home":
            self.release()
            self.queue.append(HOME)
        elif c == "base":
            self.queue.append(REBASE)
        elif c == "go" and p.get("k", "") in MOTORS:
            try:
                m = MOTORS.index(p["k"])
                angle = int(p.get("a", "0")) % 360
                d = min(2, max(0, int(p.get("d", "0"))))
                v = min(2, max(0, int(p.get("v", "1"))))
            except ValueError:
                return ""
            self.states[m] = 0
            self.queue.append(GO_HEAD + m * 9 + d * 3 + v)
            self.queue.append(GO_ANGLE + (angle + 2) // 5 % 72)
        elif c == "turn" and p.get("k", "") in MOTORS:
            try:
                m = MOTORS.index(p["k"])
                deg = int(p.get("g", "0"))
                v = min(2, max(0, int(p.get("v", "1"))))
            except ValueError:
                return ""
            steps = min(35 * 72 + 71, (abs(deg) + 2) // 5)       # 5-degree steps, up to 12,955 degrees
            if steps:
                self.states[m] = 0
                self.queue.append(TURN_HEAD + m * 3 + v)
                self.queue.append(GO_ANGLE + (36 if deg < 0 else 0) + steps // 72)   # direction and full turns
                self.queue.append(GO_ANGLE + steps % 72)                              # the rest
        elif c == "drive" and p.get("w", "") in DRIVES and p.get("w"):
            try:                       # both wheels together: w = f, b, l, r; g = wheel degrees
                way = DRIVES.index(p["w"])
                deg = abs(int(p.get("g", "0")))
                v = min(2, max(0, int(p.get("v", "1"))))
            except ValueError:
                return ""
            steps = min(17 * 72 + 71, (deg + 2) // 5)            # 5-degree steps, up to 6,475 degrees
            if steps:
                self.states[1] = self.states[2] = 0
                self.queue.append(DRIVE_HEAD + v)
                self.queue.append(GO_ANGLE + way * 18 + steps // 72)     # pattern and full turns
                self.queue.append(GO_ANGLE + steps % 72)                 # the rest
        lines = [self.hub]
        for i in range(5):
            if self.positions[i] >= 0:
                lines.append("p %s %d" % (MOTORS[i], self.positions[i]))
            if self.baselines[i] >= 0:
                lines.append("b %s %d" % (MOTORS[i], self.baselines[i]))
        return "\n".join(lines)

    def release(self):
        """Stop every motor: the safety rule for every change of mode."""
        self.states = [0] * 5
        self.queue = [q for q in self.queue if q == REBASE]      # drop moves and turns not yet sent
        self.queue.insert(0, STOP_ALL)

    # ---------- the main loop's work
    def code_mm(self, code):
        if code < 5:                       # a motor index: send its current run state
            code = code * 7 + self.states[code]
        return CMD_MM + CMD_STEP * code

    def tick(self):
        remote = bool(self.web) and self.web.page_open()
        if remote != self.remote:
            self.remote = remote
            self.release()
            if remote:
                self.queue.append(REBASE)      # page opened: the hub reads fresh homes
            print("Remote:", "open" if remote else "closed")

        now = utime.ticks_ms()
        held = utime.ticks_diff(now, self.last_send)
        mm = None
        if self.queue:
            if held >= HOLD_MS and self.code_mm(self.queue[0]) != self.last_mm:
                mm = self.code_mm(self.queue.pop(0))
            elif held >= HOLD_MS and not remote:
                mm = IDLE_MM               # the same command again: a different reading goes out in between
            # else (remote): the next motor's state goes out in between
        if mm is not None:
            pass
        elif remote and held >= (HOLD_MS if self.queue else FRAME_MS):
            mm = self.code_mm(self.rotate)
            self.rotate = (self.rotate + 1) % 5
        elif not remote and held >= IDLE_MS:
            mm = IDLE_MM
        if mm is not None:
            self.last_send = now
            self.last_mm = mm
            s = self.sensor
            s.set(0, mm)                    # DISTL: what distance_sensor.distance() reads
            s.set(1, min(mm, 320))
            s.set(2, mm)
            s.set(4, int(mm * 5.83))
            s.set(7, mm)


def memory():
    """Free memory, to tell whether the PSRAM build is ever needed (see README)."""
    gc.collect()
    total = free = least = 0
    for size, f, largest, min_free in esp32.idf_heap_info(esp32.HEAP_DATA):
        total += size
        free += f
        least += min_free
    return "Python heap free %d KB; system RAM free %d of %d KB (lowest %d KB)" % (
        gc.mem_free() // 1024, free // 1024, total // 1024, least // 1024)


def main():
    import web
    import network
    import ubinascii
    # The address the uplink network sees for this board (all its iPad's traffic is
    # NATed to it), so it is the one to authorise. Printed for tools/provision.py.
    print("STA-MAC", ubinascii.hexlify(network.WLAN(network.STA_IF).config("mac"), ":").decode())
    arm = Arm()
    try:
        arm.web = web.Web(arm.page)
        arm.web.hub_status = arm.hub_status
    except ValueError as e:          # not set up yet: the hub link still works
        print(e)
    print(memory())
    if SIMULATE:
        from simhub import FakeHub   # only frozen into the test board's firmware
        arm.sensor = FakeHub(on_write=arm.hub_wrote, debug=DEBUG)
    else:
        arm.sensor = Lump(on_write=arm.hub_wrote, debug=DEBUG)
    last_poll = last_status = utime.ticks_ms()
    shown = None
    while True:
        arm.sensor.poll()
        now = utime.ticks_ms()
        # Every loop while the remote is open; otherwise now and then, which is plenty to
        # notice a page opening and leaves more of the network stack to the iPad's browsing.
        if arm.web and (arm.web.page_open() or utime.ticks_diff(now, last_poll) >= IDLE_POLL_MS):
            last_poll = now
            arm.web.poll()
        if web.UPLINK_NAME and utime.ticks_diff(now, last_status) >= STATUS_MS:
            last_status = now
            up, rssi, failures, held = repeater.status()
            if up != shown:
                shown = up
                print("Internet via %s: %s" % (web.UPLINK_NAME, "up, %d dBm" % rssi if up else "down"))
                print(memory())
        arm.tick()
        if not (arm.web and arm.web.page_open()):
            utime.sleep_ms(2)          # nothing else to do: don't spin (the muscle sensor used to pace this)


def run():
    try:
        main()
    except KeyboardInterrupt:
        raise                      # Stop in Thonny still works
    except Exception as error:
        print("Error:", error)
        utime.sleep_ms(3000)
        machine.reset()
