"""Idempotency keys (the technique payment APIs use so a retried request is not charged twice).

A client sends `Idempotency-Key: <unique id>` with a POST/PATCH. The first successful response for that
(caller, key) is stored; a retry with the same key and the same body gets the stored response back
(header `Idempotent-Replayed: true`) without running the action again. The same key with a different body is
a client bug and gets 422.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .services import ApiError


def _body_hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def run_idempotent(
    c: sqlite3.Connection, request: Request, principal: str, key: str | None, body: dict, status_code: int, action: Callable[[], object]
) -> JSONResponse:
    if not key:
        return JSONResponse(jsonable_encoder(action()), status_code=status_code)
    if len(key) > 100:
        raise ApiError(422, "Idempotency-Key is too long (max 100 characters)")
    h = _body_hash(body)
    row = c.execute("SELECT method, path, body_hash, status_code, response FROM idempotency WHERE principal = ? AND key = ?", (principal, key)).fetchone()
    if row:
        if (row["method"], row["path"], row["body_hash"]) != (request.method, request.url.path, h):
            raise ApiError(422, "this Idempotency-Key was already used for a different request")
        return JSONResponse(json.loads(row["response"]), status_code=row["status_code"], headers={"Idempotent-Replayed": "true"})
    result = jsonable_encoder(action())  # errors propagate and are NOT stored, so the client can fix and retry
    c.execute(
        "INSERT OR IGNORE INTO idempotency (principal, key, method, path, body_hash, status_code, response) VALUES (?,?,?,?,?,?,?)",
        (principal, key, request.method, request.url.path, h, status_code, json.dumps(result)),
    )
    return JSONResponse(result, status_code=status_code)
