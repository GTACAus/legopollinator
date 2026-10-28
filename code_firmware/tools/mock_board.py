"""Try the iPad page on this computer, with a pretend board behind it.

    python tools/mock_board.py            then open http://localhost:8765

Serves app/www the way the board does (gzipped files, the same addresses) and
answers the page's messages (/s?...) like a board with a hub attached: motors
C, D (wheels) and E (arm) fitted, positions that follow the remote, drive and
turn commands. There is
no WebSocket, so the page uses its fallback and shows "Connected (slow)".
/log shows the last messages the page sent, to check what it asks the board.
/shot (Basic) and /shot?code (the code canvas open) are for screenshots:
    chrome --headless=new --window-size=1349,848 --virtual-time-budget=8000 --screenshot=code.png http://localhost:8765/shot?code
"""
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WWW = os.path.join(ROOT, "app", "www")
PORT = 8765
FILES = {"/": ("index.html.gz", "text/html"), "/app.js": ("app.js.gz", "application/javascript"),
         "/style.css": ("style.css.gz", "text/css"), "/blockly.js": ("blockly.js.gz", "application/javascript"),
         "/figtree.woff2": ("figtree.woff2", "font/woff2"), "/logo.png": ("logo.png", "image/png")}
log = []
pos = [0, 90, 180, 270, 45]
FITTED = 0b01110                       # C, D and E
DRIVE = {"f": (1, 1), "b": (-1, -1), "l": (1, 0), "r": (0, 1)}   # wheel C, wheel D


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/s":
            log.append(time.strftime("%H:%M:%S ") + query)
            del log[:-40]
            fields = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            for i, d in enumerate(fields.get("m", "00000")[:5]):
                if d != "0":
                    pos[i] = (pos[i] + (5 if d in "123" else -5)) % 360
            g = int(fields.get("g", "0") or 0)
            if fields.get("c") == "drive" and fields.get("w") in DRIVE:
                for i, way in zip((1, 2), DRIVE[fields["w"]]):
                    pos[i] = (pos[i] + way * g) % 360
            elif fields.get("c") == "turn" and fields.get("k", "") in "BCDEF" and fields.get("k"):
                i = "BCDEF".index(fields["k"])
                pos[i] = (pos[i] + g) % 360
            lines = ["h 1 B %d" % FITTED]
            lines += ["p %s %d" % ("BCDEF"[i], p) for i, p in enumerate(pos)]
            return self.reply("\n".join(lines).encode(), "text/plain")
        if path == "/shot":
            # The remote in a frame, for screenshots of screens that need a tap to reach: /shot (Basic),
            # /shot?code (Advanced, code canvas open). The link pill shows a real board's green "Connected"
            # (this pretend board has no live link, so the page would say "Connected (slow)"), and toasts are hidden.
            code = query == "code"
            script = ("const d=this.contentDocument;d.getElementById('status').style.display='none';"
                      "setInterval(()=>{const p=d.getElementById('link');p.textContent='Connected';p.className='pill'},50);"
                      + ("setTimeout(()=>d.getElementById('sAdvanced').click(),400);"
                         "setTimeout(()=>d.getElementById('codeBtn').click(),1200);" if code else ""))
            page = ("<!doctype html><style>html,body{margin:0;height:100%%}iframe{border:0;width:100%%;height:100%%}</style>"
                    "<iframe src=/ onload=\"%s\"></iframe>") % script
            return self.reply(page.encode(), "text/html")
        if path == "/log":
            return self.reply("\n".join(log).encode(), "text/plain")
        if path.startswith("/media/") and path.endswith(".svg"):
            name, kind = "media/" + path[7:] + ".gz", "image/svg+xml"
        elif path in FILES:
            name, kind = FILES[path]
        else:
            self.send_response(404)
            self.end_headers()
            return
        with open(os.path.join(WWW, name), "rb") as f:
            self.reply(f.read(), kind, gz=name.endswith(".gz"))

    def reply(self, body, kind, gz=False):
        self.send_response(200)
        self.send_header("Content-Type", kind)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("Pretend board: http://localhost:%d  (Ctrl+C to stop)" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
