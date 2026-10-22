# Fake LEGO hub, so the whole site can be tested on a board with no robot
# attached (e.g. a spare XIAO ESP32S3). Drop-in for the real Lump: the app,
# web server and page run unchanged.
#
# FakeHub models five motors (B-F) the way the real hub + SPIKE program would,
# reading the "distance" values arm.py sends (README.md) and feeding back
# motor positions, baselines and status. Drive a motor on the page and its
# position readout moves; go-to, turn, drive and home move by an angle.
#
# What it does NOT test: the real hub UART timing.

import utime

LIGHT = 5                      # the sensor "mode" the hub writes its lights with
FITTED = (1, 2, 3)             # motors present: C, D (wheels) and E (arm), as on the pollinator
FITTED_MASK = sum(1 << m for m in FITTED)
SPEED_DPS = (0, 45, 120, 300)  # degrees/second for speed levels 0..3 (0 unused)
DRIVE = (1, 2)                 # the wheel motors, C and D: home leaves them where they are
PATTERNS = ((1, 1), (-1, -1), (1, 0), (0, 1))   # drive: forward, back, left, right (C, D)
EMIT_MS = 120                  # how often a moving motor's position is reported


class FakeHub:
    def __init__(self, on_write=None, debug=False):
        self.on_write = on_write
        self.debug = debug
        self.pos = [0.0] * 5           # current angle
        self.base = [0] * 5            # baseline (home)
        self.state = [0] * 5           # run state 0..6 (0 stopped)
        self.remain = [None] * 5       # signed degrees left for a go-to/turn (else None)
        self.speed = [1] * 5           # speed level for the current go-to/turn
        self.mode = 1                  # always remote
        self.last_mm = None
        self.pending = None            # multi-value command being assembled
        self.started = False
        self.last_tick = utime.ticks_ms()
        self.last_emit = [0] * 5
        self.shown = [-1] * 5
        print("Simulated hub: motors", "".join("BCDEF"[m] for m in FITTED), "fitted")

    # ---------- looks like Lump to arm.py
    def set(self, mode, value):
        if mode != 0 or value == self.last_mm:   # mode 0 (DISTL) carries the command
            return
        self.last_mm = value
        if 1100 <= value <= 1999:
            self._command(int(round((value - 1100) / 5)))

    def poll(self):
        if not self.started:
            self.started = True
            self._emit(4, self.mode, 0, FITTED_MASK)
            self._emit(5, 87, 82, 0)             # battery 87 %, 8.20 V (a real hub program reports its own)
            for m in FITTED:
                self._emit(3, m, self.base[m] // 100, self.base[m] % 100)
                self._report(m, force=True)
            return
        now = utime.ticks_ms()
        dt = utime.ticks_diff(now, self.last_tick) / 1000
        self.last_tick = now
        for m in range(5):
            self._move(m, dt, now)

    # ---------- interpreting the commands arm.py would send the hub
    def _command(self, code):
        if self.pending is not None:
            if 88 <= code <= 159:
                self._pending_angle(code)
                return
            self.pending = None          # unexpected: drop the half-built command
        if 0 <= code <= 34:
            m, s = code // 7, code % 7
            if s != self.state[m]:       # like the hub: only a change counts (the board repeats each state)
                self.state[m], self.remain[m] = s, None
        elif code == 35:                 # stop all
            for m in range(5):
                self.state[m], self.remain[m] = 0, None
        elif code == 36:                 # home: the arm only, the wheels stay put
            for m in range(5):
                self.state[m] = 0
                if m in DRIVE:
                    self.remain[m] = None
                    continue
                self.speed[m] = 2
                self.remain[m] = self._delta(int(self.pos[m]) % 360, self.base[m], 0)
        elif code == 37:                 # rebase
            for m in FITTED:
                self.base[m] = int(self.pos[m]) % 360
                self._emit(3, m, self.base[m] // 100, self.base[m] % 100)
        elif 38 <= code <= 40:           # drive header (both wheels), two values follow
            self.pending = ("drive", code - 38, [])
        elif 43 <= code <= 87:           # go-to header, angle follows
            c = code - 43
            self.pending = ("go", c // 9, (c % 9) // 3, c % 3)
        elif 160 <= code <= 174:         # turn header, two angle values follow
            c = code - 160
            self.pending = ("turn", c // 3, c % 3, [])

    def _pending_angle(self, code):
        kind = self.pending[0]
        if kind == "go":
            _, m, direction, speed = self.pending
            self.pending = None
            self.state[m] = 0
            self.speed[m] = speed
            self.remain[m] = self._delta(int(self.pos[m]) % 360, (code - 88) * 5 % 360, direction)
        elif kind == "drive":
            _, speed, parts = self.pending
            parts.append(code - 88)
            if len(parts) == 2:
                self.pending = None
                degrees = ((parts[0] % 18) * 72 + parts[1]) * 5
                for m, way in zip(DRIVE, PATTERNS[min(3, parts[0] // 18)]):
                    self.state[m] = 0
                    self.speed[m] = speed
                    self.remain[m] = way * degrees if way else None
        else:
            _, m, speed, parts = self.pending
            parts.append(code - 88)
            if len(parts) == 2:
                self.pending = None
                back = parts[0] >= 36
                turns = parts[0] - 36 if back else parts[0]
                degrees = (turns * 72 + parts[1]) * 5
                self.state[m] = 0
                self.speed[m] = speed
                self.remain[m] = -degrees if back else degrees

    # ---------- the motor model
    @staticmethod
    def _delta(frm, to, direction):
        """Signed degrees from `frm` to `to`. direction 0 shortest path,
        1 clockwise (increasing), 2 counter-clockwise."""
        d = (to - frm) % 360
        if direction == 0:
            return d - 360 if d > 180 else d
        if direction == 2:
            return d - 360 if d else 0
        return d

    def _move(self, m, dt, now):
        if self.state[m]:                                   # continuous run
            level = self.state[m] if self.state[m] <= 3 else self.state[m] - 3
            step = SPEED_DPS[level] * dt * (1 if self.state[m] <= 3 else -1)
            self.pos[m] = (self.pos[m] + step) % 360
            self._report(m, now=now)
        elif self.remain[m] is not None:                    # go-to / turn / home
            step = SPEED_DPS[self.speed[m] + 1] * dt
            if step >= abs(self.remain[m]):
                self.pos[m] = (self.pos[m] + self.remain[m]) % 360
                self.remain[m] = None
                self._report(m, force=True)
            else:
                move = step if self.remain[m] > 0 else -step
                self.pos[m] = (self.pos[m] + move) % 360
                self.remain[m] -= move
                self._report(m, now=now)

    def _report(self, m, now=None, force=False):
        if m not in FITTED:
            return
        if not force:
            if now is None:
                now = utime.ticks_ms()
            if utime.ticks_diff(now, self.last_emit[m]) < EMIT_MS:
                return
            self.last_emit[m] = now
        angle = int(self.pos[m]) % 360
        if angle != self.shown[m] or force:
            self.shown[m] = angle
            self._emit(2, m, angle // 100, angle % 100)

    def _emit(self, kind, a, b, c):
        if self.on_write:
            self.on_write(LIGHT, (kind, a, b, c))

