"""A small, dependency-free Bilibili UID lookup app. Python 3.10+."""
from __future__ import annotations

import argparse
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
API = "https://api.bilibili.com/x/web-interface/card?mid="
CACHE_TTL = 300
CACHE_LIMIT = 128
cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
lookup_lock = threading.Lock()
last_request = 0.0


class LookupFailure(Exception):
    def __init__(self, message: str, status: int = 502, code: str = "upstream_error"):
        super().__init__(message)
        self.status, self.code = status, code


def parse_uid(value: str) -> str:
    value = value.strip()
    if len(value) > 2048:
        raise LookupFailure("输入内容过长，请输入 UID 或个人空间链接。", 400, "invalid_uid")
    if not re.fullmatch(r"[0-9]+", value):
        candidate = value
        if candidate.startswith("space.bilibili.com/"):
            candidate = "https://" + candidate
        try:
            parts = urlsplit(candidate)
            if (parts.scheme not in ("http", "https")
                    or parts.netloc.lower() != "space.bilibili.com"):
                raise ValueError()
            match = re.fullmatch(r"/([0-9]+)(?:/[A-Za-z0-9_/-]*)?", parts.path)
            if not match:
                raise ValueError()
            value = match.group(1)
        except ValueError:
            raise LookupFailure("请输入纯数字 UID，或 space.bilibili.com 开头的个人空间链接。", 400, "invalid_uid")
    if len(value) > 20 or not 0 < int(value) <= 9223372036854775807:
        raise LookupFailure("UID 应是大于 0 的整数，且不能超过 9223372036854775807。", 400, "invalid_uid")
    return str(int(value))


def safe_avatar(value: str) -> str:
    if value.startswith("//"):
        value = "https:" + value
    parts = urlsplit(value)
    if parts.scheme in ("http", "https") and (parts.hostname or "").endswith(".hdslb.com"):
        return "https://" + parts.netloc + parts.path
    return ""


def fetch_profile(uid: str) -> dict:
    request = Request(API + uid, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise LookupFailure("哔哩哔哩返回的数据过大，请稍后重试。")
        payload = json.loads(raw)
    except HTTPError as error:
        if error.code in (403, 412, 429):
            raise LookupFailure("哔哩哔哩暂时限制了查询，请稍后再试，或打开个人空间查看。", 503, "rate_limited")
        raise LookupFailure("哔哩哔哩接口暂时不可用，请稍后重试。")
    except (TimeoutError, socket.timeout):
        raise LookupFailure("查询超时，请检查网络后重试。", 504, "timeout")
    except URLError:
        raise LookupFailure("无法连接哔哩哔哩，请检查网络或代理设置。", 502, "network_error")
    except (ValueError, UnicodeError):
        raise LookupFailure("哔哩哔哩返回了无法识别的数据，请稍后重试。")

    if not isinstance(payload, dict):
        raise LookupFailure("哔哩哔哩返回的数据格式有变化，请稍后重试。")
    code = payload.get("code")
    if code != 0:
        if code in (-404, 62002, 53013):
            raise LookupFailure("未找到这个用户，账号可能不存在或已注销。", 404, "not_found")
        if code in (-352, -412, -403, -101, -799):
            raise LookupFailure("哔哩哔哩暂时限制了查询，请稍后再试，或打开个人空间查看。", 503, "rate_limited")
        raise LookupFailure(f"哔哩哔哩未能完成查询（错误码 {code}），请稍后重试。")
    data = payload.get("data") or {}
    card = data.get("card") or {}
    if not card.get("name") or str(card.get("mid")) != uid:
        raise LookupFailure("未找到这个用户的昵称，账号可能不存在或已注销。", 404, "not_found")
    official = card.get("official_verify") or {}
    return {
        "uid": uid,
        "nickname": str(card["name"]),
        "avatar": safe_avatar(str(card.get("face") or "")),
        "sign": str(card.get("sign") or ""),
        "official": str(official.get("desc") or ""),
        "level": (card.get("level_info") or {}).get("current_level"),
        "followers": data.get("follower", card.get("fans")),
        "space_url": "https://space.bilibili.com/" + uid,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "哔哩哔哩用户名片",
    }


def lookup(value: str) -> dict:
    global last_request
    uid = parse_uid(value)
    # Serialize upstream requests and share fresh results between tabs.
    with lookup_lock:
        now = time.monotonic()
        entry = cache.get(uid)
        if entry and now - entry[0] < CACHE_TTL:
            cache.move_to_end(uid)
            return {**entry[1], "cached": True}
        delay = 0.8 - (now - last_request)
        if delay > 0:
            time.sleep(delay)
        last_request = time.monotonic()
        result = fetch_profile(uid)
        cache[uid] = (time.monotonic(), result)
        cache.move_to_end(uid)
        while len(cache) > CACHE_LIMIT:
            cache.popitem(last=False)
        return {**result, "cached": False}


class LocalHTTPServer(ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR can let two processes bind the same port.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version = "BiliUID/1.1.0"

    def send_content(self, content: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://*.hdslb.com; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, value: dict, status: int = 200):
        self.send_content(json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def do_GET(self):
        # Bind only to loopback and reject foreign Host headers.
        host = self.headers.get("Host", "").lower()
        if host not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
            self.send_json({"error": "仅支持本机访问。"}, 403)
            return
        path = urlsplit(self.path)
        if path.path == "/api/health":
            self.send_json({"app": "bilibili-uid-lookup", "version": "1.1.0"})
        elif path.path == "/api/user":
            try:
                value = parse_qs(path.query).get("uid", [""])[0]
                self.send_json({"data": lookup(value)})
            except LookupFailure as error:
                self.send_json({"error": str(error), "code": error.code}, error.status)
            except Exception:
                self.send_json({"error": "查询遇到异常，请稍后重试。", "code": "internal_error"}, 500)
        elif path.path in ("/", "/index.html", "/app.js", "/style.css", "/favicon.svg"):
            name = "index.html" if path.path == "/" else path.path[1:]
            types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}
            file = ROOT / "web" / name
            self.send_content(file.read_bytes(), types[file.suffix] + "; charset=utf-8")
        else:
            self.send_json({"error": "页面不存在。"}, 404)

    def log_message(self, format, *args):
        # Avoid storing queried IDs or user input in a log.
        pass


def main():
    parser = argparse.ArgumentParser(description="Bilibili UID nickname lookup")
    parser.add_argument("--port", type=int, default=18763)
    parser.add_argument("--open", action="store_true", help="Open the app in your browser")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    try:
        server = LocalHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        # A second double-click should reopen the existing app.
        try:
            with urlopen(url + "/api/health", timeout=2) as response:
                existing = json.load(response)
            if existing.get("app") == "bilibili-uid-lookup":
                if args.open:
                    webbrowser.open(url)
                return
        except Exception:
            pass
        raise SystemExit(f"Port {args.port} is occupied. Try --port 18764.")
    print(f"Bilibili UID lookup: {url}\nClose this window or press Ctrl+C to stop.", flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
