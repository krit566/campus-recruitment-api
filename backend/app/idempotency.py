"""Idempotency keys (the technique payment APIs use so a retried request is not charged twice).

A client sends `Idempotency-Key: <unique id>` with a POST/PATCH. The first successful response for that
(caller, key) is stored; a retry with the same key and the same body gets the stored response back
(header `Idempotent-Replayed: true`) without running the action again. The same key with a different body is
a client bug and gets 422.

How simultaneous first attempts are handled: the key is RESERVED (inserted) in the same transaction as the action.
If two requests with the same key arrive together, Postgres makes the second INSERT wait on the first one's
uncommitted row. When the first commits, the second sees the key and replays the stored response; if the first
fails and rolls back, the reservation disappears with it and the second runs normally. The action never runs twice.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg import Connection
from psycopg.types.json import Jsonb

from .db import transaction
from .services import ApiError


def _body_hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def run_idempotent(
    c: Connection, request: Request, principal: str, key: str | None, body: dict, status_code: int, action: Callable[[], object]
) -> JSONResponse:
    if not key:
        return JSONResponse(jsonable_encoder(action()), status_code=status_code)
    if len(key) > 100:
        raise ApiError(422, "Idempotency-Key is too long (max 100 characters)")
    h = _body_hash(body)
    with transaction(c):
        reserved = c.execute(
            "INSERT INTO idempotency (principal, key, method, path, body_hash) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (principal, key) DO NOTHING RETURNING key",
            (principal, key, request.method, request.url.path, h),
        ).fetchone()
        if not reserved:  # this key was used before (and that request committed)
            row = c.execute(
                "SELECT method, path, body_hash, status_code, response FROM idempotency WHERE principal = %s AND key = %s",
                (principal, key),
            ).fetchone()
            if (row["method"], row["path"], row["body_hash"]) != (request.method, request.url.path, h):
                raise ApiError(422, "this Idempotency-Key was already used for a different request")
            return JSONResponse(row["response"], status_code=row["status_code"], headers={"Idempotent-Replayed": "true"})
        # errors raised here roll back the reservation too, so a failed request is not stored and can be retried
        result = jsonable_encoder(action())
        c.execute(
            "UPDATE idempotency SET status_code = %s, response = %s WHERE principal = %s AND key = %s",
            (status_code, Jsonb(result), principal, key),
        )
    return JSONResponse(result, status_code=status_code)
