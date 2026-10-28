# The Pollination Problem: SPIKE Prime hub program (official SPIKE App 3, Python)
#
# The LMS-ESP32 board is plugged into PORT A and looks like a Distance Sensor. The iPad remote
# (or a Blockly program on the iPad) sends motor commands through it.
#   Motors: C = right wheel, D = left wheel (mounted mirrored), E = the pollination arm.
# This program also tells the board to turn its Wi-Fi on, and reports motor positions, home
# positions and the hub's battery back to it, using the Distance Sensor's lights. See the README.
#
# Hub buttons: left shows the battery (scrolls across the lights, and prints in the console).
# Hold BOTH for 1 second: Wi-Fi on / off.

from hub import port, button, light_matrix
import distance_sensor
import device
import motor
import runloop
import time

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
SENSOR_PORT = port.A          # where the board is plugged in
START_WIFI = True             # turn the board's Wi-Fi on when this program starts

# Use -1 to swap forward and back for motors B, C, D, E, F. D is the left wheel, mounted
# mirrored, so -1 makes "forward" roll the robot forward on both wheels. If UP drives the
# robot backwards, flip C and D; if it spins on the spot, flip just one of them.
DIRECTIONS = (1, 1, -1, 1, 1)
DRIVE = (1, 2)                # the wheel motors: C (right) and D (left)
ARM_SPEEDS = (60, 150, 300)   # slow, medium, fast (degrees per second): motors B, E, F
DRIVE_SPEEDS = (100, 200, 400)  # slow, medium, fast for the wheels C and D (200 = about 15 cm/s)

BATTERY_EVERY_MS = 20000      # how often the battery level goes to the board (/stats)
REHOME_DEG = 8                # a still arm motor moved by hand more than this...
REHOME_STILL_MS = 1000        # ...and then held still this long = its new home position
LOST_AFTER_MS = 600           # no good reading for this long = stop every motor
IDLE_STOP_MS = 1500           # the iPad page closed (the board idles) this long = stop every motor
# ---------------------------------------------------------------------------

MOTOR_PORTS = (port.B, port.C, port.D, port.E, port.F)
NAMES = "BCDEF"
MOTOR_IDS = (48, 49, 65, 75, 76)          # medium, large, small, medium angular, large angular

# Board -> hub commands (must match the board's arm.py)
CMD_MM, CMD_STEP = 1100, 5
STOP_ALL, HOME, REBASE, DRIVE_HEAD, GO_HEAD, GO_ANGLE, TURN_HEAD = 35, 36, 37, 38, 43, 88, 160
LAST_CODE = TURN_HEAD + 14
GO_DIRECTIONS = (motor.SHORTEST_PATH, motor.CLOCKWISE, motor.COUNTERCLOCKWISE)
# Drive patterns: (C, D) for forward, back, left (only C drives), right (only D drives)
PATTERNS = ((1, 1), (-1, -1), (1, 0), (0, 1))

negative_range = False                    # True once a motor reports positions below 0 (-180..179)


def speeds(i):
    return DRIVE_SPEEDS if i in DRIVE else ARM_SPEEDS


def decode_command(mm):
    """Distance in mm -> command code, or None."""
    offset = mm - CMD_MM
    code = round(offset / CMD_STEP)
    if 0 <= code <= LAST_CODE and abs(offset - code * CMD_STEP) <= 2:
        return code
    return None


def read_board():
    """The board's reading, or -1 while there is no Distance Sensor on the port
    (board unplugged, or still starting up: it needs a few seconds after power-up)."""
    try:
        return distance_sensor.distance(SENSOR_PORT)
    except OSError:
        return -1


def fitted():
    """Motor numbers 0-4 that have a motor plugged in."""
    found = []
    for i in range(5):
        try:
            if device.id(MOTOR_PORTS[i]) in MOTOR_IDS:
                found.append(i)
        except Exception:
            pass
    return found


def position(i):
    """Motor i's position, 0..359, or -1 if there is no motor."""
    global negative_range
    try:
        p = motor.absolute_position(MOTOR_PORTS[i])
    except Exception:
        return -1
    if p < 0:
        negative_range = True
    return p % 360


def to_motor(angle):
    """0..359 -> the range this hub's motors use."""
    angle %= 360
    if negative_range and angle > 179:
        return angle - 360
    return angle


def go(i, angle, speed, direction=motor.SHORTEST_PATH):
    try:
        motor.run_to_absolute_position(MOTOR_PORTS[i], to_motor(angle), speed, direction=direction)
    except Exception:
        pass


def set_home(i):
    """This motor's home (baseline) is where it is now: relative position 0."""
    try:
        motor.reset_relative_position(MOTOR_PORTS[i], 0)
    except Exception:
        pass


def go_from_home(i, offset, speed):
    """Move to `offset` degrees from home. Never wraps, so it never swings the long way round."""
    try:
        motor.run_to_relative_position(MOTOR_PORTS[i], int(offset), speed)
    except Exception:
        pass


def turn(i, degrees, speed):
    """Turn motor i by `degrees` (negative: back) from where it is now."""
    try:
        motor.run_for_degrees(MOTOR_PORTS[i], int(degrees) * DIRECTIONS[i], speed)
    except Exception:
        pass


def run_state(i, state):
    try:
        if state == 0:
            motor.stop(MOTOR_PORTS[i])
        elif state <= 3:
            motor.run(MOTOR_PORTS[i], DIRECTIONS[i] * speeds(i)[state - 1])
        else:
            motor.run(MOTOR_PORTS[i], -DIRECTIONS[i] * speeds(i)[state - 4])
    except Exception:
        pass


def _reading(f, low, high):
    """f() if it gives a number in low..high, else None."""
    try:
        v = f()
    except Exception:
        return None
    return v if isinstance(v, (int, float)) and low <= v <= high else None


def find_battery():
    """A function giving (percent, millivolts), or None if this hub can't say. The SPIKE App 3
    Python docs have no battery call, so look for the ones hub software versions have had.
    Nothing here can stop the program: the board just shows "not reported" in /stats."""
    import hub
    places = [("hub", hub)] + [("hub." + n, getattr(hub, n)) for n in ("battery", "power") if hasattr(hub, n)]
    volts = level = None
    for where, obj in places:
        for name in ("battery_voltage", "voltage"):
            f = getattr(obj, name, None)
            if volts is None and callable(f) and _reading(f, 5000, 9500) is not None:
                volts = (where + "." + name, f)
        for name in ("battery_level", "capacity_left", "capacity", "level"):
            f = getattr(obj, name, None)
            if level is None and callable(f) and _reading(f, 0, 100) is not None:
                level = (where + "." + name, f)
    if volts is None and level is None:
        print("Battery: this hub doesn't report it")
        return None
    print("Battery: from", " and ".join(x[0] + "()" for x in (level, volts) if x))

    def read():
        mv = _reading(volts[1], 5000, 9500) if volts else None
        pct = _reading(level[1], 0, 100) if level else None
        if pct is None and mv is not None:          # about 7.0 V empty .. 8.3 V full
            pct = (mv - 7000) * 100 // 1300
        if pct is None:
            return None
        return int(max(0, min(100, pct))), int(mv or 0)
    return read


class Board:
    """Messages to the board through the Distance Sensor's lights (at most 20 a second)."""

    def __init__(self):
        self.queue = []
        self.last = 0

    def send(self, kind, a=0, b=0, c=0, first=False):
        msg = [kind, a, b, c]
        same_motor = kind in (2, 3)                 # positions: one per motor; others: one per kind
        self.queue = [m for m in self.queue if not (m[0] == kind and (not same_motor or m[1] == a))]
        if first:
            self.queue.insert(0, msg)
        else:
            self.queue.append(msg)

    def angle(self, kind, i, angle):
        self.send(kind, i, angle // 100, angle % 100)

    def tick(self, now):
        if self.queue and time.ticks_diff(now, self.last) >= 50:
            self.last = now
            try:
                distance_sensor.show(SENSOR_PORT, self.queue.pop(0))
            except Exception:
                pass


async def main():
    board = Board()
    motors = fitted()
    mask = sum(1 << i for i in motors)
    baseline = [position(i) for i in range(5)]
    rest = list(baseline)                 # where each motor should be resting (None: learn it once settled)
    busy_until = [0] * 5                  # commanded motors are not checked for re-homing
    candidate = [-1] * 5
    candidate_since = [0] * 5
    reported = [-1] * 5

    battery = find_battery()
    last_battery = time.ticks_ms()
    last_error = None
    applied = [0] * 5                     # remote run state of each motor
    go_head = None                        # a go-to header waiting for its angle
    turn_head = None                      # a turn header: [motor, speed, direction and full turns, time]
    drive_head = None                     # a drive header: [speed, pattern and full turns, time]
    last_code = None                      # the board's commands count once, when the reading changes
    previous = -1
    last_good = time.ticks_ms()
    last_command = time.ticks_ms()
    lost = True
    wifi = START_WIFI
    both_since = None
    left_was = False                      # left button: pressed and let go on its own = show the battery
    left_alone = False
    restore_at = None                     # when the battery text has scrolled past: the usual letter again
    last_status = 0
    last_report = 0
    report_next = 0
    rebase_at = None                      # re-read the homes once the motors have settled
    for i in motors:
        set_home(i)

    def letter():
        return "?" if lost else ("P" if motors else "X")

    def send_battery():
        b = battery() if battery else None
        if b:
            pct, mv = b
            board.send(5, pct, mv // 100, mv % 100)

    def send_hello():
        board.send(1, 1 if wifi else 0, first=True)
        for i in motors:
            board.angle(3, i, baseline[i])
        board.send(4, 1, 0, mask)
        send_battery()

    def rebase():
        for i in motors:
            baseline[i] = rest[i] = position(i)
            set_home(i)
            board.angle(3, i, baseline[i])

    def commanded(i, ms, expect=None):
        """Motor i was told to move: skip re-homing checks for `ms`, then expect it at `expect`
        (None: learn where it settles, e.g. after a plain stop)."""
        busy_until[i] = time.ticks_add(time.ticks_ms(), ms)
        rest[i] = None if expect is None else expect % 360

    def stop_all():
        for i in range(5):
            run_state(i, 0)
            applied[i] = 0

    def stopped():
        return all(a == 0 for a in applied)

    light_matrix.write("?")                  # until the board answers on port A
    print("Waiting for the board on port A...")

    while True:
        try:
            now = time.ticks_ms()
            mm = read_board()
            steady = mm == previous
            previous = mm
            code = decode_command(mm) if steady and mm >= 1100 else None
            idle = steady and 0 < mm <= 1050      # the board is there, but nobody is driving

            if code is not None or idle:
                if lost:                      # the board (re)connected: introduce ourselves
                    lost = False
                    send_hello()
                    light_matrix.write(letter())
                    print("Board found on port A")
                last_good = now

            if idle:
                last_code = None
                if time.ticks_diff(now, last_command) > IDLE_STOP_MS and not stopped():
                    stop_all()                # the iPad page closed while a motor was running
            fresh = code is not None and code != last_code
            if fresh:
                last_code = code
                last_command = now
                if code < 35:
                    i, state = code // 7, code % 7
                    if applied[i] != state:
                        applied[i] = state
                        run_state(i, state)
                        commanded(i, 100000 if state else 1500)
                elif code == STOP_ALL:
                    stop_all()
                elif code == HOME:                            # the arm goes home; the wheels stay put
                    stop_all()
                    for i in motors:
                        if i not in DRIVE:
                            go_from_home(i, 0, ARM_SPEEDS[1])
                            commanded(i, 3000, baseline[i])
                elif code == REBASE:
                    rebase_at = time.ticks_add(now, 800)   # after the stop has settled
                elif code < GO_HEAD:                          # drive header
                    if code - DRIVE_HEAD < 3:
                        drive_head = [code - DRIVE_HEAD, None, now]
                        go_head = turn_head = None
                elif code >= TURN_HEAD:                       # turn header
                    h = code - TURN_HEAD
                    turn_head = [h // 3, h % 3, None, now]
                    go_head = drive_head = None
                elif code < GO_ANGLE:                         # go-to header
                    h = code - GO_HEAD
                    go_head = (h // 9, (h // 3) % 3, h % 3, now)
                    turn_head = drive_head = None
                elif drive_head is not None and time.ticks_diff(now, drive_head[2]) < 300:
                    if drive_head[1] is None:                 # 1st value: pattern and full turns
                        drive_head[1] = code - GO_ANGLE
                        drive_head[2] = now
                    else:                                     # 2nd value: the rest, in 5-degree steps
                        v, a, _ = drive_head
                        drive_head = None
                        pattern = PATTERNS[min(3, a // 18)]
                        degrees = ((a % 18) * 72 + code - GO_ANGLE) * 5
                        for i, way in zip(DRIVE, pattern):
                            applied[i] = 0
                            if way:
                                turn(i, way * degrees, DRIVE_SPEEDS[v])
                            else:
                                run_state(i, 0)
                            commanded(i, int(degrees * 1000 / DRIVE_SPEEDS[v]) + 1000)
                elif turn_head is not None and time.ticks_diff(now, turn_head[3]) < 300:
                    if turn_head[2] is None:                  # 1st value: direction and full turns
                        turn_head[2] = code - GO_ANGLE
                        turn_head[3] = now
                    else:                                     # 2nd value: the rest, in 5-degree steps
                        i, v, a, _ = turn_head
                        turn_head = None
                        degrees = ((a % 36) * 72 + code - GO_ANGLE) * 5
                        if a >= 36:
                            degrees = -degrees
                        applied[i] = 0
                        turn(i, degrees, speeds(i)[v])
                        commanded(i, int(abs(degrees) * 1000 / speeds(i)[v]) + 1000)
                elif go_head is not None and time.ticks_diff(now, go_head[3]) < 300:
                    i, d, v, _ = go_head
                    go_head = None
                    angle = (code - GO_ANGLE) * 5
                    applied[i] = 0
                    go(i, angle, speeds(i)[v], GO_DIRECTIONS[d])
                    commanded(i, 3000, angle)

            elif code is None and not idle and time.ticks_diff(now, last_good) > LOST_AFTER_MS:
                if not lost:
                    lost = True
                    stop_all()
                    light_matrix.write("?")
                    print("Waiting for the board on port A...")

            # Hub buttons: left shows the battery; both for 1 s: Wi-Fi
            left = button.pressed(button.LEFT) > 0
            right = button.pressed(button.RIGHT) > 0
            if left and right:
                left_alone = False                # part of a both-buttons hold, not a battery check
                if both_since is None:
                    both_since = now
                elif time.ticks_diff(now, both_since) > 1000:
                    both_since = time.ticks_add(now, 100000)   # once per hold
                    wifi = not wifi
                    board.send(1, 1 if wifi else 0, first=True)
                    light_matrix.write("W" if wifi else "-")
                    restore_at = time.ticks_add(now, 1500)
            else:
                both_since = None
                if left and not left_was:
                    left_alone = True
                if left_was and not left and left_alone:
                    left_alone = False
                    b = battery() if battery else None
                    text = "%d%%" % b[0] if b else "NO BATTERY INFO"
                    print("Battery:", text + (" (%.2f V)" % (b[1] / 1000) if b and b[1] else ""))
                    light_matrix.write(text)          # scrolls; the program carries on meanwhile
                    restore_at = time.ticks_add(now, 600 * len(text) + 500)
                    send_battery()

            left_was = left
            if restore_at is not None and time.ticks_diff(now, restore_at) > 0:
                restore_at = None
                light_matrix.write(letter())

            # Positions for the iPad, and re-homing: a still arm motor moved by hand gets a new home
            if motors and time.ticks_diff(now, last_report) >= 100:
                last_report = now
                i = motors[report_next % len(motors)]
                report_next += 1
                p = position(i)
                if p >= 0:
                    if abs(p - reported[i]) >= 2:
                        reported[i] = p
                        board.angle(2, i, p)
                    still = time.ticks_diff(now, busy_until[i]) > 0 and applied[i] == 0
                    if still and rest[i] is None:
                        rest[i] = p                           # settled after a command: that is where it rests
                    moved = 0 if rest[i] is None else min(abs(p - rest[i]), 360 - abs(p - rest[i]))
                    if still and moved > REHOME_DEG and i not in DRIVE:
                        if candidate[i] < 0 or min(abs(p - candidate[i]), 360 - abs(p - candidate[i])) > 2:
                            candidate[i] = p
                            candidate_since[i] = now
                        elif time.ticks_diff(now, candidate_since[i]) > REHOME_STILL_MS:
                            baseline[i] = rest[i] = p
                            set_home(i)
                            candidate[i] = -1
                            board.angle(3, i, p)
                    else:
                        candidate[i] = -1

            if rebase_at is not None and time.ticks_diff(now, rebase_at) > 0:
                rebase_at = None
                rebase()

            if time.ticks_diff(now, last_status) > 2000:
                last_status = now
                board.send(4, 1, 0, mask)

            if time.ticks_diff(now, last_battery) > BATTERY_EVERY_MS:
                last_battery = now
                send_battery()

            board.tick(now)
            await runloop.sleep_ms(5)

        except Exception as e:            # one bad moment must not stop the robot for the lesson
            if str(e) != last_error:
                last_error = str(e)
                print("Error (carrying on):", last_error)
            await runloop.sleep_ms(50)

runloop.run(main())
