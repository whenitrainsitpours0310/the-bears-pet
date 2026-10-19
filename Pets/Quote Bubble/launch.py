"""Start the quote bubble without keeping a console window open."""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
pythonw = Path(sys.executable).with_name("pythonw.exe")
if not pythonw.is_file():
    raise SystemExit("pythonw.exe was not found beside the current Python interpreter.")


def desktop_ready() -> bool:
    point = (ctypes.c_long * 2)()
    return bool(ctypes.windll.user32.GetCursorPos(ctypes.byref(point)))


def chatgpt_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq ChatGPT.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and '"chatgpt.exe"' in result.stdout.casefold()


def wait_for_login() -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if desktop_ready() and chatgpt_running():
            time.sleep(5)  # Give ChatGPT time to register its pet shortcut and UI.
            return
        time.sleep(2)


parser = argparse.ArgumentParser()
parser.add_argument("--login-startup", action="store_true")
args, run_args = parser.parse_known_args()
if args.login_startup:
    wait_for_login()

def start_bubble(supervised: bool) -> int:
    with (ROOT / "runtime.log").open("a", encoding="utf-8") as log:
        log.write("\n--- Starting quote bubble" + (" after login" if supervised else "")
                  + f" at {datetime.now().astimezone().isoformat(timespec='seconds')} ---\n")
        log.flush()
        try:
            process = subprocess.Popen(
                [str(pythonw), str(ROOT / "run.py"), *run_args],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=(subprocess.CREATE_NO_WINDOW if supervised else
                               subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS),
            )
        except OSError as exc:
            log.write(f"Quote bubble launch failed: {exc}\n")
            return 1
        if not supervised:
            if sys.stdout is not None:
                print(f"Quote bubble launch requested (PID {process.pid}).")
            return 0
        exit_code = process.wait()
        log.write(f"Quote bubble exited with code {exit_code}.\n")
        return exit_code


if args.login_startup:
    failures = 0
    while True:
        exit_code = start_bubble(supervised=True)
        if exit_code == 0:
            break  # Manual stop is a normal exit.
        failures += 1
        delay = min(60, 5 * 2 ** min(failures - 1, 4))
        with (ROOT / "runtime.log").open("a", encoding="utf-8") as log:
            log.write(f"Retrying quote bubble in {delay} seconds.\n")
        time.sleep(delay)
else:
    raise SystemExit(start_bubble(supervised=False))
