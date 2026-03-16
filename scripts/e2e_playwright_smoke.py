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
    ap.add_argument("--port", type=int, default=8550)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--headless", action="store_true", default=False)
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # Start the app in web server mode (no external browser).
    proc = subprocess.Popen(
        [sys.executable, "main.py", "--web", "--host", args.host, "--port", str(args.port)],
        cwd=".",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        wait_http_ok(base_url + "/", timeout_s=args.timeout)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless)
            page = browser.new_page()
            page.goto(base_url, wait_until="domcontentloaded")
            # Flet/Flutter takes time to boot; wait a bit for something recognizable.
            page.wait_for_timeout(3000)

            # Very light smoke assertions. These selectors may need tuning depending on Flutter web semantics.
            page.screenshot(path="/tmp/comiccatcher_smoke.png", full_page=True)

            # Best-effort: try selecting the Codex profile by double-clicking its title.
            try:
                page.get_by_text("Codex", exact=True).dblclick(timeout=5000)
                page.wait_for_timeout(2000)
                page.screenshot(path="/tmp/comiccatcher_after_codex.png", full_page=True)
            except Exception:
                pass

            browser.close()

        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

