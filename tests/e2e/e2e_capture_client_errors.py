#!/usr/bin/env python3
import argparse
import subprocess
import sys
import time
from urllib.request import urlopen


def wait_http_ok(url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as r:
                if 200 <= r.status < 400:
                    return
        except Exception as e:
            last_err = e
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}. Last error: {last_err}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8552)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--observe", type=float, default=20.0, help="Seconds to keep the page open collecting console/page errors.")
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--auto-open-local", type=str, default="", help="Pass through to main.py (auto-open local CBZ).")
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    cmd = [sys.executable, "main.py", "--web", "--host", args.host, "--port", str(args.port), "--debug", "1"]
    if args.auto_open_local:
        cmd += ["--auto-open-local", args.auto_open_local]

    proc = subprocess.Popen(
        cmd,
        cwd=".",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        wait_http_ok(base_url + "/", timeout_s=args.timeout)

        from playwright.sync_api import sync_playwright

        console_lines: list[str] = []
        page_errors: list[str] = []

        def on_console(msg):
            try:
                console_lines.append(f"[console:{msg.type}] {msg.text}")
            except Exception:
                pass

        def on_pageerror(err):
            try:
                page_errors.append(f"[pageerror] {err}")
            except Exception:
                pass

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless)
            ctx = browser.new_context(locale="en-US")
            page = ctx.new_page()
            page.on("console", on_console)
            page.on("pageerror", on_pageerror)
            page.goto(base_url, wait_until="domcontentloaded")
            page.wait_for_timeout(int(args.observe * 1000))
            page.screenshot(path="/tmp/comiccatcher_client_errors.png", full_page=True)
            ctx.close()
            browser.close()

        # Stop the app before reading its output to avoid blocking forever on stdout.
        out = ""
        try:
            proc.terminate()
            try:
                out, _ = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, _ = proc.communicate(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                out, _ = proc.communicate(timeout=5)
            except Exception:
                out = ""

        print("=== App Output (tail) ===")
        if out:
            lines = out.splitlines()[-200:]
            for line in lines:
                print(line)

        print("=== Browser Console (tail) ===")
        for line in console_lines[-200:]:
            print(line)

        print("=== Browser Page Errors (tail) ===")
        for line in page_errors[-200:]:
            print(line)

        try:
            with open("/tmp/comiccatcher_pageerrors.txt", "w", encoding="utf-8") as f:
                for line in page_errors:
                    f.write(line)
                    if not line.endswith("\n"):
                        f.write("\n")
        except Exception:
            pass

        return 0
    finally:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
