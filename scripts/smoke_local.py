from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    kind: str
    target: str


CHECKS = [
    Check("api", "http", "http://localhost:8000/health"),
    Check("qdrant", "http", "http://localhost:6333/collections"),
    Check("elasticsearch", "http", "http://localhost:9200/_cluster/health"),
    Check("postgres", "tcp", "localhost:5432"),
    Check("redis", "tcp", "localhost:6379"),
    Check("redpanda-kafka", "tcp", "localhost:9092"),
    Check("redpanda-admin", "http", "http://localhost:9644/v1/status/ready"),
]


def main() -> int:
    failures: list[str] = []
    for check in CHECKS:
        ok, detail = run_check(check)
        status = "ok" if ok else "failed"
        print(f"{check.name:18} {status:7} {detail}")
        if not ok:
            failures.append(check.name)

    if failures:
        print("")
        print("Smoke check failed: " + ", ".join(failures))
        return 1
    return 0


def run_check(check: Check) -> tuple[bool, str]:
    if check.kind == "tcp":
        host, raw_port = check.target.split(":", 1)
        return check_tcp(host, int(raw_port))
    return check_http(check.target)


def check_tcp(host: str, port: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True, f"{host}:{port}"
    except OSError as exc:
        return False, str(exc)


def check_http(url: str) -> tuple[bool, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as response:
            body = response.read(512)
            if response.status >= 400:
                return False, f"HTTP {response.status}"
            return True, summarize_body(body)
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except OSError as exc:
        return False, str(exc)


def summarize_body(body: bytes) -> str:
    if not body:
        return "empty response"
    try:
        parsed = json.loads(body.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body[:80].decode(errors="replace")
    if isinstance(parsed, dict):
        for key in ("status", "message", "version"):
            if key in parsed:
                return f"{key}={parsed[key]}"
    return "json response"


if __name__ == "__main__":
    raise SystemExit(main())
