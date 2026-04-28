from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0
DEFAULT_TIMEOUT_SECONDS = 45

CSS_IMPORT_RE = re.compile(r"@import\s+url\(\s*[\"']?([^\"')]+)[\"']?\s*\)", re.IGNORECASE)
STATIC_JS_IMPORT_RE = re.compile(
    r"(?:import|export)\s+(?:[^\"']*?\s+from\s+)?[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
DYNAMIC_JS_IMPORT_RE = re.compile(r"import\(\s*[\"']([^\"']+)[\"']\s*\)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test the static frontend asset graph served by FastAPI.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind. Use 0 to choose a free port.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args()


def fetch_text(url: str, timeout: int = 10) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "verbatim-smoke-test"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return body, response.geturl()
    except Exception as error:
        raise RuntimeError(f"Failed to fetch {url}: {error}") from error


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(parsed._replace(query="", fragment=""))


def resolve_url(base_url: str, reference: str) -> str:
    return normalize_url(urllib.parse.urljoin(base_url, reference))


def choose_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def wait_for_health(base_url: str, process: subprocess.Popen[str], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("FastAPI server exited before /health became available.")
        try:
            body, _ = fetch_text(f"{base_url}/health", timeout=2)
            if "ok" in body.lower():
                return
        except (RuntimeError, urllib.error.URLError, TimeoutError) as error:
            last_error = error
        time.sleep(0.5)

    raise RuntimeError(f"Timed out waiting for /health. Last error: {last_error}")


def collect_css_assets(base_url: str) -> set[str]:
    root_url = f"{base_url}/static/styles.css"
    visited: set[str] = set()

    def visit(url: str) -> None:
        url = normalize_url(url)
        if url in visited:
            return
        visited.add(url)
        css, _ = fetch_text(url)
        for reference in CSS_IMPORT_RE.findall(css):
            visit(resolve_url(url, reference.strip()))

    visit(root_url)
    return visited


def collect_js_modules(base_url: str) -> set[str]:
    entrypoints = [
        f"{base_url}/static/login.js",
        f"{base_url}/static/upload.js",
        f"{base_url}/static/results.js",
    ]
    visited: set[str] = set()

    def visit(url: str) -> None:
        url = normalize_url(url)
        if url in visited:
            return
        visited.add(url)
        source, _ = fetch_text(url)
        references = STATIC_JS_IMPORT_RE.findall(source) + DYNAMIC_JS_IMPORT_RE.findall(source)
        for reference in references:
            reference = reference.strip()
            if reference.startswith("."):
                visit(resolve_url(url, reference))

    for entrypoint in entrypoints:
        visit(entrypoint)
    return visited


def start_server(host: str, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.setdefault("APP_ENV", "development")
    env.setdefault("SESSION_SECRET", "local-smoke-test-secret")
    env.setdefault("SESSION_HTTPS_ONLY", "false")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=8)


def main() -> int:
    args = parse_args()
    port = args.port or choose_free_port(args.host)
    base_url = f"http://{args.host}:{port}"
    process = start_server(args.host, port)
    try:
        wait_for_health(base_url, process, args.timeout)

        login_html, login_url = fetch_text(f"{base_url}/login")
        if "Verbatim" not in login_html or "/static/styles.css" not in login_html:
            raise RuntimeError("/login did not return the expected frontend shell.")

        _, redirected_url = fetch_text(f"{base_url}/")
        if not normalize_url(redirected_url).endswith("/login"):
            raise RuntimeError(f"/ should redirect to /login for anonymous users, got {redirected_url}")

        css_assets = collect_css_assets(base_url)
        js_modules = collect_js_modules(base_url)
    finally:
        stop_server(process)

    print(
        "smoke ok: "
        f"login={login_url} "
        f"css_assets={len(css_assets)} "
        f"js_modules={len(js_modules)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
