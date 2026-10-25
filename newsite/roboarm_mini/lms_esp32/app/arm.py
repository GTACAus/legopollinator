# The Pollination Problem: LMS-ESP32 firmware for the robot pollinator. main.py on the board
# runs it at power-up (the module keeps the name arm.py, so boards set up for the robot arm
# start it unchanged).
#
# At power-up the board is a plain LEGO Distance Sensor that reads "idle", and it turns Bluetooth
# on under its name (e.g. ROBOT 7). The iPad stays on the school's Wi-Fi, opens the remote from the
# website in Bluefy and connects to the board over Bluetooth (ble.py); the board passes the remote's
# commands to the hub and the hub's news back. How the board, hub and page talk: README.md.
#
# This module, lump.py and ble.py are frozen into the firmware; the board's filesystem only holds
# main.py and config.py (its name).

import utime
import machine
import gc
import esp32
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
IDLE_POLL_MS = 20                   # Bluetooth check interval while the remote is not connected


class Arm:
    def __init__(self):
        self.sensor = None
        self.link = None
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
        # kind 1 (the hub's old Wi-Fi on/off message) is ignored: there is no Wi-Fi; Bluetooth stays on
        if kind in (2, 3) and a < 5:
            angle = b * 100 + c
            (self.positions if kind == 2 else self.baselines)[a] = angle
            self.tell("%s %s %d" % ("p" if kind == 2 else "b", MOTORS[a], angle))
        elif kind == 5:                 # battery: percent, then volts as two 2-digit halves (8.05 V = 80, 50)
            self.battery = (a, b * 100 + c, utime.ticks_ms())
        elif kind == 4:
            self.hub = "h %d %s %d" % (a, MOTORS[b] if b < 5 else "B", c)
            self.tell(self.hub)

    def tell(self, line):
        if self.link:
            self.link.broadcast(line)

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
        remote = bool(self.link) and self.link.page_open()
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


def robot_name():
    """The board's name, from config.py (written by tools/provision.py). Boards first set up with the
    robot arm's Wi-Fi firmware have WIFI_NAME instead, which is the same name."""
    try:
        import config
    except ImportError:
        return "GTAC robot"
    return getattr(config, "ROBOT_NAME", None) or getattr(config, "WIFI_NAME", None) or "GTAC robot"


def main():
    import ble
    import ubinascii
    # The chip's MAC address, for tools/provision.py's list of boards
    print("STA-MAC", ubinascii.hexlify(machine.unique_id(), ":").decode())
    arm = Arm()
    arm.link = ble.Ble(arm.page, robot_name())
    print(memory())
    if SIMULATE:
        from simhub import FakeHub   # only frozen into the test board's firmware
        arm.sensor = FakeHub(on_write=arm.hub_wrote, debug=DEBUG)
    else:
        arm.sensor = Lump(on_write=arm.hub_wrote, debug=DEBUG)
    last_poll = utime.ticks_ms()
    while True:
        arm.sensor.poll()
        now = utime.ticks_ms()
        # Every loop while the remote is connected; otherwise now and then, to notice it connecting
        if arm.link.page_open() or utime.ticks_diff(now, last_poll) >= IDLE_POLL_MS:
            last_poll = now
            arm.link.poll()
        arm.tick()
        if not (arm.link and arm.link.page_open()):
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
