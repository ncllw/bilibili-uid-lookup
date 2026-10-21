"""Entry point for the Windows portable bundle."""
from __future__ import annotations

import json
import platform
import ssl
import sys

import server


def self_test() -> None:
    assets = ["index.html", "app.js", "batch.js", "style.css", "favicon.svg"]
    for asset in assets:
        file = server.ROOT / "web" / asset
        if not file.is_file() or not file.stat().st_size:
            raise RuntimeError(f"Missing bundled asset: {asset}")
    if server.parse_uid("https://space.bilibili.com/306936843") != "306936843":
        raise RuntimeError("UID parsing failed")
    ssl.create_default_context()
    print(json.dumps({
        "status": "ok",
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "bundled_assets": assets,
        "https_available": True,
    }), flush=True)


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return
    if "--no-browser" in sys.argv:
        sys.argv.remove("--no-browser")
    elif "--open" not in sys.argv:
        sys.argv.append("--open")
    server.main()


if __name__ == "__main__":
    main()
