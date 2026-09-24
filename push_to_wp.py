#!/usr/bin/env python3
"""Deliver validated AndroidGuides data to the same-origin SiteGround copy.

The authenticated WordPress REST endpoint remains the primary path. If
SiteGround intercepts it with its explicit ``/.well-known/sgcaptcha/`` page,
the script falls back to certificate-verified FTPS. The FTPS account must be
restricted to ``wp-content/uploads/androidguide`` in SiteGround.

The fallback stages and hashes both files before changing either live name,
proves that the server supports atomic rename-overwrite, and attempts to
restore the previous bytes if promotion fails.
"""

from __future__ import annotations

import argparse
import base64
import ftplib
import hashlib
import io
import json
import os
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

WP_BASE = "https://androidguides.com"
ENDPOINT = WP_BASE + "/wp-json/androidguide/v1/push"
FILES = ["devices.json", "devices-static.html"]
HERE = Path(__file__).parent

PUSH_ATTEMPTS = 3
RETRY_WAIT = 60
FTPS_TIMEOUT = 30

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36 AndroidGuidesPipe/1.0")
SGCAPTCHA_MARKER = "/.well-known/sgcaptcha/"


@dataclass(frozen=True)
class AttemptResult:
    ok: bool
    retryable: bool
    reason: str
    message: str


def push_once(name: str, body: bytes, auth: str) -> AttemptResult:
    """Make one authenticated REST attempt."""
    req = urllib.request.Request(ENDPOINT, data=body, method="POST")
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", UA)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status = response.status
            final_url = response.geturl()
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        retryable = exc.code >= 500 or exc.code == 429
        return AttemptResult(False, retryable, "http", f"HTTP {exc.code} — {detail!r}")
    except Exception as exc:
        return AttemptResult(False, True, "network", str(exc))

    if SGCAPTCHA_MARKER in raw:
        return AttemptResult(
            False,
            True,
            "sgcaptcha",
            f"HTTP {status} at {final_url} — SiteGround sgcaptcha challenge",
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return AttemptResult(
            False,
            True,
            "non_json",
            f"HTTP {status} at {final_url} — response was not JSON. "
            f"First 400 chars: {raw[:400]!r}",
        )

    if not (isinstance(payload, dict) and payload.get("ok")):
        return AttemptResult(False, False, "endpoint", f"endpoint returned {payload}")

    return AttemptResult(
        True,
        False,
        "ok",
        f"-> {payload.get('url')} ({payload.get('bytes')} bytes)",
    )


def push_file(name: str, body: bytes, auth: str) -> AttemptResult:
    """Push one file over REST, retrying transient failures."""
    last_result = AttemptResult(False, False, "internal", "no attempt made")
    for attempt in range(1, PUSH_ATTEMPTS + 1):
        last_result = push_once(name, body, auth)
        if last_result.ok:
            note = "" if attempt == 1 else f" (succeeded on attempt {attempt})"
            print(f"[OK] pushed {name} {last_result.message}{note}")
            return last_result

        if not last_result.retryable:
            print(f"[FAIL] {name}: {last_result.message}")
            print(f"[FAIL] {name}: not a transient error — not retrying")
            return last_result

        if attempt >= PUSH_ATTEMPTS:
            print(f"[FAIL] {name}: {last_result.message}")
            print(f"[FAIL] {name}: still failing after {PUSH_ATTEMPTS} attempts")
            return last_result

        print(
            f"[WARN] {name}: attempt {attempt}/{PUSH_ATTEMPTS} failed — "
            f"{last_result.message}"
        )
        print(f"[WARN] {name}: retrying in {RETRY_WAIT}s")
        time.sleep(RETRY_WAIT)

    return last_result


def _required_env(name: str, *, preserve_whitespace: bool = False) -> str:
    raw = os.environ.get(name, "")
    if not raw.strip():
        raise RuntimeError(f"{name} is not set")
    return raw if preserve_whitespace else raw.strip()


def _ftps_settings() -> tuple[str, int, str, str]:
    host = _required_env("SG_FTPS_HOST")
    user = _required_env("SG_FTPS_USER")
    password = _required_env("SG_FTPS_PASSWORD", preserve_whitespace=True)
    try:
        port = int(os.environ.get("SG_FTPS_PORT", "").strip() or "21")
    except ValueError as exc:
        raise RuntimeError("SG_FTPS_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("SG_FTPS_PORT must be between 1 and 65535")
    return host, port, user, password


def _connect_ftps(
    factory: Callable[..., ftplib.FTP_TLS] = ftplib.FTP_TLS,
) -> ftplib.FTP_TLS:
    host, port, user, password = _ftps_settings()
    client = factory(context=ssl.create_default_context(), timeout=FTPS_TIMEOUT)
    client.connect(host, port)
    client.login(user, password)
    client.prot_p()
    return client


def _download(client: ftplib.FTP_TLS, name: str) -> bytes:
    chunks: list[bytes] = []
    client.retrbinary(f"RETR {name}", chunks.append)
    return b"".join(chunks)


def _upload(client: ftplib.FTP_TLS, name: str, data: bytes) -> None:
    client.storbinary(f"STOR {name}", io.BytesIO(data))


def _delete_quietly(client: ftplib.FTP_TLS, name: str) -> None:
    try:
        client.delete(name)
    except ftplib.all_errors:
        pass


def _assert_atomic_replace(client: ftplib.FTP_TLS, token: str) -> None:
    """Prove RNFR/RNTO can replace a file before touching live names."""
    target = f".agd-replace-{token}.target"
    source = f".agd-replace-{token}.source"
    try:
        _upload(client, target, b"old")
        _upload(client, source, b"new")
        client.rename(source, target)
        if _download(client, target) != b"new":
            raise RuntimeError("FTPS rename-overwrite probe returned the wrong bytes")
    finally:
        _delete_quietly(client, source)
        _delete_quietly(client, target)


def ftps_preflight(
    factory: Callable[..., ftplib.FTP_TLS] = ftplib.FTP_TLS,
) -> None:
    """Test TLS login and atomic replacement with disposable hidden files."""
    client = _connect_ftps(factory)
    try:
        # A directory-scoped account should see the existing live pair at its
        # root. Reading both catches a wrong home directory without changing it.
        for name in FILES:
            _download(client, name)
        _assert_atomic_replace(client, secrets.token_hex(8))
    finally:
        try:
            client.quit()
        except ftplib.all_errors:
            client.close()


def publish_via_ftps(
    files: dict[str, bytes],
    factory: Callable[..., ftplib.FTP_TLS] = ftplib.FTP_TLS,
) -> None:
    """Publish a verified pair, restoring old bytes on failed promotion."""
    token = secrets.token_hex(8)
    temp_names = {name: f".{name}.{token}.tmp" for name in files}
    old_bytes: dict[str, bytes] = {}
    promoted: list[str] = []
    client = _connect_ftps(factory)

    try:
        _assert_atomic_replace(client, token)

        # The restricted account must already see the live pair. This catches
        # a wrong home directory before any production name changes.
        for name in files:
            old_bytes[name] = _download(client, name)

        # Stage and hash every file before either live name changes.
        for name, data in files.items():
            temp = temp_names[name]
            _upload(client, temp, data)
            staged = _download(client, temp)
            if hashlib.sha256(staged).digest() != hashlib.sha256(data).digest():
                raise RuntimeError(f"FTPS verification failed for staged {name}")

        try:
            for name in files:
                client.rename(temp_names[name], name)
                promoted.append(name)

            for name, data in files.items():
                live = _download(client, name)
                if hashlib.sha256(live).digest() != hashlib.sha256(data).digest():
                    raise RuntimeError(f"FTPS verification failed for live {name}")
        except Exception as publish_error:
            rollback_errors: list[str] = []
            for name in reversed(promoted):
                rollback = f".{name}.{token}.rollback"
                try:
                    _upload(client, rollback, old_bytes[name])
                    client.rename(rollback, name)
                    if _download(client, name) != old_bytes[name]:
                        raise RuntimeError("restored bytes did not match")
                except Exception as rollback_error:  # pragma: no cover
                    rollback_errors.append(f"{name}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(
                    f"FTPS publish failed ({publish_error}); rollback also failed: "
                    + "; ".join(rollback_errors)
                ) from publish_error
            raise RuntimeError(
                f"FTPS publish failed and previous live bytes were restored: {publish_error}"
            ) from publish_error
    finally:
        for temp in temp_names.values():
            _delete_quietly(client, temp)
        try:
            client.quit()
        except ftplib.all_errors:
            client.close()


def _local_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name in FILES:
        path = HERE / name
        if not path.exists():
            raise RuntimeError(f"{name}: not found in repo")
        files[name] = path.read_bytes()
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ftps-preflight",
        action="store_true",
        help="test FTPS login and atomic replacement without touching live files",
    )
    args = parser.parse_args(argv)

    if args.ftps_preflight:
        try:
            ftps_preflight()
        except Exception as exc:
            print(f"[FAIL] FTPS preflight: {exc}")
            return 1
        print("[OK] FTPS preflight: TLS login and atomic rename-overwrite passed")
        return 0

    try:
        files = _local_files()
        user = _required_env("WP_APP_USER")
        password = _required_env("WP_APP_PASSWORD", preserve_whitespace=True)
    except RuntimeError as exc:
        print(f"[FAIL] {exc}")
        return 1

    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    for name, data in files.items():
        body = json.dumps({
            "name": name,
            "content_b64": base64.b64encode(data).decode(),
        }).encode()
        result = push_file(name, body, auth)
        if result.ok:
            continue
        if result.reason != "sgcaptcha":
            print(f"[FAIL] same-origin delivery stopped: {result.reason}")
            return 1

        print(
            "[WARN] persistent SiteGround sgcaptcha challenge; "
            "switching the complete two-file delivery to folder-scoped FTPS"
        )
        try:
            publish_via_ftps(files)
        except Exception as exc:
            print(f"[FAIL] FTPS fallback: {exc}")
            return 1
        print("[OK] same-origin copies verified and published over FTPS")
        return 0

    print("[OK] same-origin copies pushed to WordPress")
    return 0


if __name__ == "__main__":
    sys.exit(main())
