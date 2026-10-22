#!/usr/bin/env python3
"""The robot pollinator (mega.pollinator.ldr) as a glTF model for pollinator-3d.html.

    python gen_pollinator.py        -> build/pollinator.glb (git-ignored), then render_pollinator.py

Needs an LDraw library with BrickLink Studio's extra parts (the SPIKE motors and hub are not in the
official library): Studio's own, C:\\Program Files\\Studio 2.0\\ldraw, is used if it is there, or set
LDRAWDIR. Parts the model uses are copied into ../ldraw/ so later runs need neither.

Each top-level part goes into a group, so the page can highlight it: the wheel motors (C on the robot's
right, D on its left, with the arm at the front), the arm motor (E) and its gear rack, the hub, the wheels, and everything
else (body). Materials are named <group>_<LDraw colour>. Output frame: millimetres / 1000 (metres), y up,
the arm towards +z, so the robot's left is +x.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import glb      # noqa: E402
import ldraw    # noqa: E402

STUDIO = r"C:\Program Files\Studio 2.0\ldraw"
LIB = os.environ.get("LDRAWDIR") or (STUDIO if os.path.isdir(STUDIO) else None)
CACHE = ldraw.CACHE
MODEL = os.path.join(HERE, "mega.pollinator.ldr")
OUT = os.path.join(HERE, "build", "pollinator.glb")     # big (35 MB): not published; the step player shows rendered frames


def fetch(name):
    """Like ldraw.fetch, but also looks in Studio's UnOfficial folders."""
    name = name.lower().replace("\\", "/")
    for sub in ("parts/", "p/"):
        path = os.path.join(CACHE, sub, name)
        if os.path.exists(path):
            return path
    # Some of Studio's parts name a high-resolution primitive without its 48/ folder
    for sub in ("parts/", "p/", "UnOfficial/parts/", "UnOfficial/p/", "p/48/", "UnOfficial/p/48/") if LIB else ():
        src = os.path.join(LIB, sub, name)
        if os.path.exists(src):
            dest = os.path.join(CACHE, "p/" if sub.endswith("p/") and "parts" not in sub else "parts/", name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(src, "rb") as a, open(dest, "wb") as b:
                b.write(a.read())
            return dest
    raise SystemExit(f"LDraw file not found: {name} (set LDRAWDIR to an LDraw library with Studio's parts)")


ldraw.fetch = fetch


# Studio's hub has no port letters: draw LDraw's 45601 instead, which has them, in the same place (as the arm's
# model does); its main colour is white
SWAP = {"bb1142c01.dat": ("45601.dat", 15)}


def group(part, x):
    """Which highlight group a top-level part belongs to."""
    if part == "54675.dat":          # LDraw is right-handed with -y up: facing the arm (-z), right is -x
        return "motorC" if x < -650 else "motorD"
    return {"54696.dat": "motorE", "87761.dat": "rack", "45601.dat": "hub", "49295c01.dat": "wheels"}.get(part, "body")


def colours():
    """LDraw colour code -> sRGB, from Studio's LDConfig.ldr (it has Studio's extra colours) if there."""
    path = os.path.join(LIB, "LDConfig.ldr") if LIB else None
    if not path or not os.path.exists(path):
        return ldraw.colours()
    out = {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        t = line.split()
        if len(t) > 2 and t[1] == "!COLOUR":
            kv = {t[i]: t[i + 1] for i in range(2, len(t) - 1)}
            v = kv["VALUE"].lstrip("#")
            out[int(kv["CODE"])] = (int(v[0:2], 16) / 255, int(v[2:4], 16) / 255, int(v[4:6], 16) / 255,
                                    int(kv.get("ALPHA", "255")) / 255)
    return out


def main():
    palette = colours()
    tris = {}
    for line in open(MODEL, encoding="utf-8"):
        t = line.split()
        if len(t) < 15 or t[0] != "1":
            continue
        c, v, part = int(t[1]), list(map(float, t[2:14])), t[14].lower()
        if part in SWAP:
            part, c = SWAP[part]
        m = ([v[3:6], v[6:9], v[9:12]], v[0:3])
        out = []
        ldraw.flatten(part, m, c, out)
        tris.setdefault(group(part, v[0]), []).extend(out)
    # Centre the model on its wheels' axle, standing on y = 0 (metres, y up, as ldraw.write_glb)
    allp = [p for ts in tris.values() for _, tri in ts for p in tri]
    cx = (min(p[0] for p in allp) + max(p[0] for p in allp)) / 2
    cz = (min(p[2] for p in allp) + max(p[2] for p in allp)) / 2
    floor = max(p[1] for p in allp)                       # LDraw y points down
    L = ldraw.LDU
    groups = []
    for g, ts in sorted(tris.items()):
        by_colour = {}
        for c, tri in ts:
            by_colour.setdefault(c, []).append(tuple(((x - cx) * L, (floor - y) * L, -(z - cz) * L) for x, y, z in tri))
        for c, items in sorted(by_colour.items()):
            groups.append((f"{g}_{c}", palette.get(c, (0.5, 0.5, 0.5, 1)), items))
        pts = [q for _, tri in ts for q in tri]
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        mm = lambda a, k: round(((a - (cx if k == 0 else floor if k == 1 else cz)) * (-1 if k else 1)) * L * 1000, 1)
        print(f"{g:7s} {len(ts):6d} triangles  x {mm(lo[0], 0)}..{mm(hi[0], 0)}  y {mm(hi[1], 1)}..{mm(lo[1], 1)}  z {mm(hi[2], 2)}..{mm(lo[2], 2)} mm")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    glb.write_glb(OUT, groups, "pollinator gen_pollinator.py")
    print("wrote", os.path.relpath(OUT, HERE), os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
