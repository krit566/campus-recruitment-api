"""Observability: a request id on every response, one structured JSON log line per request, and in-memory metrics.

Metrics are per process (fine for one instance); with several instances they would go to Prometheus or similar.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import Counter, defaultdict, deque

from fastapi import Request

log = logging.getLogger("recruitment.access")
_LOCK = threading.Lock()
_COUNTS: Counter = Counter()  # (route, status) -> requests
_LATENCY: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))  # route -> recent latencies (ms)


def _route(request: Request) -> str:
    r = request.scope.get("route")
    return getattr(r, "path", request.url.path)  # "/students/{sid}", not "/students/42": bounded label set


async def middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    route = _route(request)
    with _LOCK:
        _COUNTS[(route, response.status_code)] += 1
        _LATENCY[route].append(ms)
    response.headers["X-Request-ID"] = rid
    log.info(json.dumps({"rid": rid, "method": request.method, "route": route, "status": response.status_code, "ms": round(ms, 1)}))
    return response


def _p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 1)


def snapshot() -> dict:
    with _LOCK:
        routes = {}
        for (route, status), n in _COUNTS.items():
            r = routes.setdefault(route, {"requests": 0, "errors_5xx": 0, "by_status": {}})
            r["requests"] += n
            r["by_status"][str(status)] = n
            if status >= 500:
                r["errors_5xx"] += n
        for route, lat in _LATENCY.items():
            vals = list(lat)
            routes.setdefault(route, {})["latency_ms"] = {"p50": _p(vals, 0.5), "p95": _p(vals, 0.95)}
    return {"routes": routes}


def reset() -> None:
    with _LOCK:
        _COUNTS.clear()
        _LATENCY.clear()
