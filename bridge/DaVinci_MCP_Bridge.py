"""DaVinci Resolve ICHIDA ishlaydigan ko'prik (bepul versiya uchun).

Resolve ning bepul versiyasida tashqi skripting ("External scripting using")
yo'q, lekin Workspace > Scripts menyusidan ishga tushirilgan skriptlar Resolve
API dan foydalana oladi. Bu skript Resolve ichida 127.0.0.1 da kichik HTTP
server ochadi va MCP server Resolve ni shu orqali boshqaradi.

O'rnatish: faylni Resolve ning Scripts/Utility papkasiga nusxalang
(o'rnatuvchi skript buni o'zi qiladi), so'ng Resolve da:
    Workspace > Scripts > DaVinci_MCP_Bridge

Faqat standart kutubxona ishlatiladi, Python 3.6+ bilan mos.
"""

import json
import os
import sys
import traceback

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:  # pragma: no cover
    sys.exit("Python 3 kerak")

HOST = "127.0.0.1"
PORT = int(os.environ.get("DAVINCI_BRIDGE_PORT", "8765"))
HEADER = "X-Resolve-Bridge"  # brauzerdan keladigan so'rovlarni to'sadi
PRIMITIVES = (type(None), bool, int, float, str)


class Registry(object):
    def __init__(self, root):
        self.objects = {0: root}
        self.ids = {}
        self.next_id = 1

    def add(self, obj):
        key = id(obj)
        oid = self.ids.get(key)
        if oid is not None and self.objects.get(oid) is obj:
            return oid
        oid = self.next_id
        self.next_id += 1
        self.objects[oid] = obj
        self.ids[key] = oid
        return oid

    def encode(self, value):
        if isinstance(value, PRIMITIVES):
            return value
        if isinstance(value, (list, tuple)):
            return [self.encode(v) for v in value]
        if isinstance(value, dict):
            return {"__dict__": [[self.encode(k), self.encode(v)] for k, v in value.items()]}
        return {"__obj__": self.add(value), "__type__": type(value).__name__}

    def decode(self, value):
        if isinstance(value, list):
            return [self.decode(v) for v in value]
        if isinstance(value, dict):
            if "__obj__" in value:
                return self.objects[value["__obj__"]]
            if "__dict__" in value:
                return dict((self.decode(k), self.decode(v)) for k, v in value["__dict__"])
            return dict((k, self.decode(v)) for k, v in value.items())
        return value

    def handle(self, req):
        op = req.get("op")
        if op == "ping":
            return "pong"
        if op == "reset":
            root = self.objects[0]
            self.__init__(root)
            return True
        obj = self.objects[req["obj"]]
        attr = getattr(obj, req["name"])
        if op == "getattr":
            return {"__callable__": True} if callable(attr) else self.encode(attr)
        if op == "call":
            args = self.decode(req.get("args", []))
            return self.encode(attr(*args))
        raise ValueError("noma'lum op: %r" % op)


def make_server(resolve, port=PORT):
    registry = Registry(resolve)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.headers.get(HEADER) != "1":
                self.send_error(403)
                return
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                out = {"ok": True, "result": registry.handle(json.loads(body.decode("utf-8")))}
            except Exception as exc:
                out = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
                       "trace": traceback.format_exc(limit=3)}
            data = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return HTTPServer((HOST, port), Handler)


def _find_resolve():
    g = globals()
    if g.get("resolve") is not None:
        return g["resolve"]
    for getter in (
        lambda: g["bmd"].scriptapp("Resolve"),
        lambda: g["fusion"].GetResolve(),
        lambda: g["app"].GetResolve(),
        lambda: __import__("DaVinciResolveScript").scriptapp("Resolve"),
    ):
        try:
            r = getter()
            if r is not None:
                return r
        except Exception:
            pass
    return None


def main():
    resolve = _find_resolve()
    if resolve is None:
        print("[MCP Bridge] Resolve obyekti topilmadi. Skriptni Workspace > Scripts menyusidan ishga tushiring.")
        return
    try:
        server = make_server(resolve)
    except OSError:
        print("[MCP Bridge] %d-port band — ko'prik allaqachon ishlayotgan bo'lishi mumkin." % PORT)
        return
    print("[MCP Bridge] Ishga tushdi: http://%s:%d  — endi Claude dan buyruq bering." % (HOST, PORT))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if not os.environ.get("DAVINCI_BRIDGE_TEST"):
    main()
