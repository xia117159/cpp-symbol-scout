from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any


class ServiceClientError(RuntimeError):
    pass


def request(project: str, payload: dict[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    host, port = endpoint_for_project(project)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect((host, port))
        send_framed(conn, payload)
        response = recv_framed(conn)
    if not isinstance(response, dict):
        raise ServiceClientError("service returned invalid response")
    if not response.get("ok", False):
        raise ServiceClientError(str(response.get("error") or "service request failed"))
    return response


def endpoint_for_project(project: str) -> tuple[str, int]:
    import hashlib

    project_root = Path(project).expanduser().resolve()
    project_id = hashlib.sha1(str(project_root).encode("utf-8")).hexdigest()[:20]
    return "127.0.0.1", 56000 + (int(project_id[:8], 16) % 8000)


def send_framed(conn: socket.socket, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    conn.sendall(len(body).to_bytes(4, "big") + body)


def recv_framed(conn: socket.socket) -> dict[str, Any]:
    size = int.from_bytes(recv_exact(conn, 4), "big")
    return json.loads(recv_exact(conn, size).decode("utf-8"))


def recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = conn.recv(remaining)
        if not chunk:
            raise ServiceClientError("connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
