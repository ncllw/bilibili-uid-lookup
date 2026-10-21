"""Build the Windows x64 onedir distribution and a ZIP, with no UPX."""
from __future__ import annotations

import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

PROJECT = Path(__file__).resolve().parent
VERSION = "1.2.0"
NAME = "BiliUidLookup"


def main():
    if sys.platform != "win32" or platform.architecture()[0] != "64bit":
        raise SystemExit("Build this release using 64-bit Python on Windows.")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--console", "--noupx", "--name", NAME,
        "--distpath", str(PROJECT / "dist"),
        "--workpath", str(PROJECT / "build" / "pyinstaller"),
        "--specpath", str(PROJECT / "build"),
        "--add-data", f"{PROJECT / 'web'};web",
        "--version-file", str(PROJECT / "windows-version.txt"),
        str(PROJECT / "portable.py"),
    ], cwd=PROJECT, check=True)
    folder = PROJECT / "dist" / NAME
    shutil.copy2(PROJECT / "PORTABLE-README.txt", folder / "使用说明.txt")
    subprocess.run([str(folder / (NAME + ".exe")), "--self-test"], check=True)
    archive = PROJECT / "dist" / f"bilibili-uid-lookup-v{VERSION}-windows-x64-portable.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                package.write(file, file.relative_to(folder.parent))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Portable ZIP: {archive}\nSHA256: {digest}", flush=True)


if __name__ == "__main__":
    main()
