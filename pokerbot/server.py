"""Stdlib-only web server.

  GET  /              the page (web/)
  GET  /api/book      the last 10,000 book lines
  GET  /api/stats     per-bot numbers so far
  GET  /api/stream    server-sent events: book, stats
"""

import json
import multiprocessing as mp
import os
import queue
import threading
import time
from collections import deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from .sim import worker
from .stats import Stats

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
BOOK_MAX = 10000
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json"}


class Hub:
    def __init__(self):
        self.subs = set()
        self.lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=5000)
        with self.lock:
            self.subs.add(q)
        return q

    def drop(self, q):
        with self.lock:
            self.subs.discard(q)

    def publish(self, event, data):
        msg = f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()
        with self.lock:
            subs = list(self.subs)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass  # slow tab, it'll catch up from the next batch


class App:
    def __init__(self, workers=2, rate=40):
        self.hub = Hub()
        self.stats = Stats()
        self.book = deque(maxlen=BOOK_MAX)
        self.book_lock = threading.Lock()
        self.hand_no = 0
        self.hps = 0.0
        self.n_workers = workers
        self.rate = rate
        self.procs = []

    def start(self):
        ctx = mp.get_context("spawn")  # fork + threads is asking for trouble
        self.q = ctx.Queue(maxsize=20000)
        self.stop = ctx.Event()
        for i in range(self.n_workers):
            p = ctx.Process(target=worker, args=(self.q, self.stop, 1000 + i, self.rate), daemon=True)
            p.start()
            self.procs.append(p)
        threading.Thread(target=self.collect, daemon=True, name="collect").start()

    def shutdown(self):
        self.stop.set()
        for p in self.procs:
            p.join(timeout=2)

    def collect(self):
        fresh = []
        last_book = last_stats = time.monotonic()
        window = deque()  # arrival times, for hands/sec
        while True:
            try:
                seats, ln = self.q.get(timeout=0.1)
            except queue.Empty:
                seats = None
            now = time.monotonic()
            if seats:
                self.stats.add_ring(seats)
                self.hand_no += 1
                ln["n"] = self.hand_no
                with self.book_lock:
                    self.book.append(ln)
                fresh.append(ln)
                window.append(now)

            while window and now - window[0] > 5:
                window.popleft()
            if now - last_book >= 0.25:
                self.hps = len(window) / 5
                if fresh:
                    self.hub.publish("book", {"lines": fresh, "hps": round(self.hps, 1)})
                    fresh = []
                last_book = now
            if now - last_stats >= 1.0:
                self.hub.publish("stats", self.stats_json())
                last_stats = now

    def stats_json(self):
        return dict(self.stats.snapshot(), hps=round(self.hps, 1))


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass  # too chatty with the stream open

        def send_json(self, obj, code=200):
            body = json.dumps(obj, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/stats":
                return self.send_json(app.stats_json())
            if path == "/api/book":
                with app.book_lock:
                    lines = list(app.book)
                return self.send_json({"lines": lines, "hps": round(app.hps, 1)})
            if path == "/api/stream":
                return self.stream()
            return self.static(path)

        def stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = app.hub.subscribe()
            try:
                self.wfile.write(b"retry: 2000\n\n")
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=15)
                    except queue.Empty:
                        msg = b": ping\n\n"
                    self.wfile.write(msg)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                app.hub.drop(q)
                self.close_connection = True

        def static(self, path):
            if path == "/":
                path = "/index.html"
            full = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
            if not full.startswith(WEB + os.sep) or not os.path.isfile(full):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            with open(full, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(host="127.0.0.1", port=8000, workers=2, rate=40):
    app = App(workers=workers, rate=rate)
    app.start()
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    print(f"pokerbot on http://{host}:{port}  ({workers} sim workers, {rate or 'max'} hands/s each)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        app.shutdown()
        httpd.server_close()
