"""
Reproducible Load-Test Suite and Benchmarking Module for Parking Management Backend.
Covers:
- Scenarios: gates, lookup, search, sessions list, check-in+check-out cycle,
             scan 640x480, scan 1080p, scan 12 MP.
- Concurrency levels: 1, 8, 32, 64 (10s each + 60s at c=64).
- Reports: rps, p50, p95, p99, max latency (ms), and error breakdown.
- Session minting via documented shell one-liner (zero hardcoded secrets).
- Skipped by default in pytest unless RUN_PERF_TESTS="1".
"""

import argparse
import contextlib
import http.client
import io
import json
import math
import os
import random
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import pytest
from PIL import Image, ImageDraw, ImageFont

# Skipped by default in pytest unless RUN_PERF_TESTS == "1"
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PERF_TESTS") != "1",
    reason="Perf tests run only when RUN_PERF_TESTS=1",
)


@dataclass
class RequestResult:
    status_code: int
    latency_ms: float
    error: str | None = None


@dataclass
class ScenarioStats:
    scenario_name: str
    concurrency: int
    duration_s: float
    total_requests: int
    successful_requests: int
    rps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    status_counts: dict[str, int] = field(default_factory=dict)
    errors_count: int = 0


def mint_session_id_from_django() -> str:
    """
    Mints an authenticated sessionid for an active EMPLOYEE or MANAGER account
    without printing or exposing credentials.
    Follows README Section 3 Step 8.
    """
    try:
        from importlib import import_module
        from pathlib import Path

        repo_root = str(Path(__file__).resolve().parents[2])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        import django
        from django.conf import settings
        from django.contrib.auth import (
            BACKEND_SESSION_KEY,
            HASH_SESSION_KEY,
            SESSION_KEY,
        )

        if not settings.configured:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
            django.setup()

        from apps.accounts.models import Account

        session_store = import_module(settings.SESSION_ENGINE).SessionStore()
        user = Account.objects.filter(
            role__in=["MANAGER", "EMPLOYEE"], is_active=True
        ).first()
        if not user:
            raise RuntimeError(
                "No active MANAGER or EMPLOYEE account found to mint session."
            )

        session_store[SESSION_KEY] = str(user.pk)
        session_store[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session_store[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session_store.save()
        return str(session_store.session_key)
    except Exception as exc:
        # Fallback to env var or fail
        env_session = os.getenv("SESSIONID") or os.getenv("SESSION_KEY")
        if env_session:
            return env_session
        raise RuntimeError(f"Unable to mint authenticated session key: {exc}") from exc


def generate_synthetic_plate_image(
    width: int, height: int, plate_text: str | None = None
) -> bytes:
    """
    Creates an in-memory JPEG image with a synthetic Vietnamese license plate using Pillow.
    Fully autonomous at runtime (H9a): zero dependency on .agents/sample_real_plate.jpg.
    Supports multi-plate generation across 640x480, 1920x1080 (1080p), and 4000x3000 (12MP).
    """
    if not plate_text:
        sample_plates = [
            "30A-123.45",
            "51K-992.14",
            "43A-567.89",
            "29B-888.88",
            "60A-359.37",
            "98A-234.56",
            "36A-789.01",
            "14A-456.78",
        ]
        plate_text = random.choice(sample_plates)

    # Base car bumper / environment canvas (neutral light tone)
    img = Image.new("RGB", (width, height), color=(215, 220, 225))
    draw = ImageDraw.Draw(img)

    # Compute plate bounding box centered in canvas
    plate_w = int(width * 0.45)
    plate_h = int(plate_w * 0.28)
    if plate_h > int(height * 0.35):
        plate_h = int(height * 0.35)
        plate_w = int(plate_h / 0.28)

    px1 = (width - plate_w) // 2
    py1 = (height - plate_h) // 2
    px2 = px1 + plate_w
    py2 = py1 + plate_h

    # Draw white plate with black border
    border_width = max(2, int(plate_h * 0.04))
    corner_radius = max(2, int(plate_h * 0.08))
    draw.rounded_rectangle(
        [px1, py1, px2, py2],
        radius=corner_radius,
        fill=(255, 255, 255),
        outline=(15, 15, 15),
        width=border_width,
    )

    # Render license plate text
    font_size = max(12, int(plate_h * 0.52))
    try:
        font = ImageFont.load_default(size=font_size)
    except TypeError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), plate_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = px1 + (plate_w - tw) // 2
    ty = py1 + (plate_h - th) // 2
    draw.text((tx, ty), plate_text, fill=(10, 10, 10), font=font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def generate_csrf_pair() -> tuple[str, str]:
    """Generates a valid Django CSRF secret and masked token pair."""
    import string

    chars = string.ascii_letters + string.digits
    secret = "".join(random.choices(chars, k=32))
    mask = "".join(random.choices(chars, k=32))
    pairs = zip(
        (chars.index(x) for x in secret),
        (chars.index(x) for x in mask),
        strict=True,
    )
    cipher = "".join(chars[(x + y) % len(chars)] for x, y in pairs)
    token = mask + cipher
    return secret, token


class LoadTestClient:
    """Manages HTTP requests, session cookies, CSRF tokens, and payloads using stdlib http.client."""

    def __init__(self, base_url: str, session_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlparse(self.base_url)
        self._host = parsed.hostname or "127.0.0.1"
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.session_id = session_id or os.getenv("SESSIONID") or ""
        self._cached_images: dict[str, bytes] = {}
        self._cached_multipart_pools: dict[str, list[tuple[bytes, str]]] = {}
        self._pools_lock = threading.Lock()
        self._gates_cache: list[dict[str, Any]] = []
        self._thread_local = threading.local()
        self._csrf_pair = generate_csrf_pair()

    def warmup_payloads(self, size_labels: list[str] | None = None) -> None:
        """Pre-generate synthetic multipart image payloads in memory before benchmark begins."""
        targets = size_labels or ["640x480", "1080p", "12mp"]
        for size in targets:
            self._get_multipart_scan(size)

    def _get_conn(self, reset: bool = False) -> http.client.HTTPConnection:
        if reset or not hasattr(self._thread_local, "conn"):
            old = getattr(self._thread_local, "conn", None)
            if old is not None:
                with contextlib.suppress(Exception):
                    old.close()
            self._thread_local.conn = http.client.HTTPConnection(
                self._host, self._port, timeout=20.0
            )
        return self._thread_local.conn

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = "application/json",
    ) -> tuple[int, bytes]:
        headers = self._headers(content_type=content_type)
        if body is not None:
            headers["Content-Length"] = str(len(body))
        for attempt in range(2):
            conn = self._get_conn(reset=(attempt > 0))
            try:
                conn.request(method, path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
                return resp.status, data
            except http.client.HTTPException, OSError:
                if attempt == 1:
                    raise
        raise RuntimeError("Unreachable")

    def ensure_session(self) -> None:
        if not self.session_id:
            self.session_id = mint_session_id_from_django()

    def get_image(self, size_label: str) -> bytes:
        if size_label not in self._cached_images:
            if size_label == "640x480":
                self._cached_images[size_label] = generate_synthetic_plate_image(
                    640, 480
                )
            elif size_label == "1080p":
                self._cached_images[size_label] = generate_synthetic_plate_image(
                    1920, 1080
                )
            elif size_label == "12mp":
                self._cached_images[size_label] = generate_synthetic_plate_image(
                    4000, 3000
                )
            else:
                self._cached_images[size_label] = generate_synthetic_plate_image(
                    640, 480
                )
        return self._cached_images[size_label]

    def _get_multipart_scan(self, size_label: str) -> tuple[bytes, str]:
        if size_label not in self._cached_multipart_pools:
            with self._pools_lock:
                if size_label not in self._cached_multipart_pools:
                    pool: list[tuple[bytes, str]] = []
                    sample_plates = [
                        "30A-123.45",
                        "51K-992.14",
                        "43A-567.89",
                        "29B-888.88",
                        "60A-359.37",
                        "98A-234.56",
                    ]
                    w, h = 640, 480
                    if size_label == "1080p":
                        w, h = 1920, 1080
                    elif size_label == "12mp":
                        w, h = 4000, 3000

                    for idx, plate in enumerate(sample_plates):
                        img_bytes = generate_synthetic_plate_image(
                            w, h, plate_text=plate
                        )
                        boundary = f"----ParkingLoadTestBoundary{random.randint(100000, 999999)}"
                        header = (
                            f"--{boundary}\r\n"
                            f'Content-Disposition: form-data; name="image"; filename="test_{size_label}_{idx}.jpg"\r\n'
                            f"Content-Type: image/jpeg\r\n\r\n"
                        ).encode()
                        footer = f"\r\n--{boundary}--\r\n".encode()
                        body = header + img_bytes + footer
                        content_type = f"multipart/form-data; boundary={boundary}"
                        pool.append((body, content_type))
                    self._cached_multipart_pools[size_label] = pool

        return random.choice(self._cached_multipart_pools[size_label])

    def _headers(self, content_type: str | None = "application/json") -> dict[str, str]:
        csrf_cookie, csrf_header = self._csrf_pair
        headers = {
            "Cookie": f"sessionid={self.session_id}; csrftoken={csrf_cookie}",
            "X-CSRFToken": csrf_header,
            "Accept": "application/json",
            "Connection": "keep-alive",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def test_gates(self) -> RequestResult:
        t0 = time.perf_counter()
        try:
            status_code, raw_data = self._request("GET", "/api/v1/parking/gates/")
            latency = (time.perf_counter() - t0) * 1000.0
            if status_code == 200 and not self._gates_cache:
                try:
                    data = json.loads(raw_data)
                    self._gates_cache = (
                        data
                        if isinstance(data, list)
                        else data.get("data", []) or data.get("results", []) or []
                    )
                except Exception:
                    pass
            return RequestResult(status_code=status_code, latency_ms=latency)
        except Exception as exc:
            return RequestResult(
                status_code=0,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )

    def test_lookup(self) -> RequestResult:
        t0 = time.perf_counter()
        try:
            status_code, _ = self._request(
                "GET", "/api/v1/parking/vehicle-lookup/?license_plate=43K-860.50"
            )
            return RequestResult(
                status_code=status_code,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )
        except Exception as exc:
            return RequestResult(
                status_code=0,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )

    def test_search(self) -> RequestResult:
        t0 = time.perf_counter()
        try:
            status_code, _ = self._request(
                "GET", "/api/v1/parking/vehicle-search/?q=43K"
            )
            return RequestResult(
                status_code=status_code,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )
        except Exception as exc:
            return RequestResult(
                status_code=0,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )

    def test_sessions_list(self) -> RequestResult:
        t0 = time.perf_counter()
        try:
            status_code, _ = self._request(
                "GET", "/api/v1/parking/sessions/?page=1&page_size=20"
            )
            return RequestResult(
                status_code=status_code,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
            )
        except Exception as exc:
            return RequestResult(
                status_code=0,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )

    def _ensure_gates(self) -> None:
        if not self._gates_cache:
            with contextlib.suppress(Exception):
                status_code, raw_data = self._request("GET", "/api/v1/parking/gates/")
                if status_code == 200:
                    data = json.loads(raw_data)
                    self._gates_cache = (
                        data
                        if isinstance(data, list)
                        else data.get("data", []) or data.get("results", []) or []
                    )

    def test_cycle(self) -> RequestResult:
        """Full check-in + check-out cycle."""
        t0 = time.perf_counter()
        try:
            self._ensure_gates()
            in_gate_id = 1
            out_gate_id = 3
            if self._gates_cache:
                for g in self._gates_cache:
                    if g.get("direction") == "IN" and g.get("is_active", True):
                        in_gate_id = g["id"]
                    elif g.get("direction") == "OUT" and g.get("is_active", True):
                        out_gate_id = g["id"]

            rand_id = random.randint(1000000, 9999999)
            plate = f"51A-{rand_id // 10000:03d}.{rand_id % 10000:04d}"

            # 1. Check-in
            checkin_body = json.dumps(
                {
                    "license_plate": plate,
                    "entry_gate_id": in_gate_id,
                    "recognition_source": "MANUAL",
                }
            ).encode()
            status_in, raw_in = self._request(
                "POST", "/api/v1/parking/sessions/check-in/", body=checkin_body
            )
            if status_in != 201:
                return RequestResult(
                    status_code=status_in,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    error=f"Check-in failed with status {status_in}",
                )

            data_in = json.loads(raw_in)
            session_data = data_in.get("data") or data_in.get("session") or data_in
            session_code = (
                session_data.get("session_code")
                if isinstance(session_data, dict)
                else None
            )

            # 2. Check-out
            checkout_payload: dict[str, Any] = {
                "exit_gate_id": out_gate_id,
                "payment_method": "CASH",
            }
            if session_code:
                checkout_payload["session_code"] = session_code
            else:
                checkout_payload["license_plate"] = plate

            status_out, _ = self._request(
                "POST",
                "/api/v1/parking/sessions/check-out/",
                body=json.dumps(checkout_payload).encode(),
            )
            latency = (time.perf_counter() - t0) * 1000.0
            return RequestResult(status_code=status_out, latency_ms=latency)
        except Exception as exc:
            return RequestResult(
                status_code=0,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )

    def test_scan(self, size_label: str) -> RequestResult:
        """POST /api/v1/parking/plate-scans/ with in-memory JPEG."""
        body, content_type = self._get_multipart_scan(size_label)
        t0 = time.perf_counter()
        try:
            status_code, _ = self._request(
                "POST",
                "/api/v1/parking/plate-scans/",
                body=body,
                content_type=content_type,
            )
            latency = (time.perf_counter() - t0) * 1000.0
            return RequestResult(status_code=status_code, latency_ms=latency)
        except Exception as exc:
            return RequestResult(
                status_code=0,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )


def percentile(data: list[float], pct: float) -> float:
    """Calculates percentile from sorted float list."""
    if not data:
        return 0.0
    k = (len(data) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return data[int(k)]
    d0 = data[int(f)] * (c - k)
    d1 = data[int(c)] * (k - f)
    return d0 + d1


def run_scenario_concurrency(
    client: LoadTestClient,
    action_fn: Callable[[], RequestResult],
    scenario_name: str,
    concurrency: int,
    duration_s: float,
) -> ScenarioStats:
    """Runs a single scenario under specific concurrency for specified duration."""
    results: list[RequestResult] = []
    stop_time = time.perf_counter() + duration_s
    start_time = time.perf_counter()

    def worker_loop() -> list[RequestResult]:
        worker_results: list[RequestResult] = []
        while time.perf_counter() < stop_time:
            res = action_fn()
            worker_results.append(res)
        return worker_results

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker_loop) for _ in range(concurrency)]
        for fut in as_completed(futures):
            results.extend(fut.result())

    actual_duration = time.perf_counter() - start_time
    request_count = len(results)
    if request_count == 0:
        return ScenarioStats(
            scenario_name=scenario_name,
            concurrency=concurrency,
            duration_s=actual_duration,
            total_requests=0,
            successful_requests=0,
            rps=0.0,
            p50_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            max_ms=0.0,
        )

    latencies = sorted([r.latency_ms for r in results])
    status_counts: dict[str, int] = {}
    successful = 0
    errors = 0

    for r in results:
        code_str = str(r.status_code) if r.status_code > 0 else "ERROR"
        status_counts[code_str] = status_counts.get(code_str, 0) + 1
        if 200 <= r.status_code < 400:
            successful += 1
        else:
            errors += 1

    rps = request_count / actual_duration if actual_duration > 0 else 0.0

    return ScenarioStats(
        scenario_name=scenario_name,
        concurrency=concurrency,
        duration_s=actual_duration,
        total_requests=request_count,
        successful_requests=successful,
        rps=rps,
        p50_ms=percentile(latencies, 50.0),
        p95_ms=percentile(latencies, 95.0),
        p99_ms=percentile(latencies, 99.0),
        max_ms=latencies[-1] if latencies else 0.0,
        status_counts=status_counts,
        errors_count=errors,
    )


def print_stats_table(stats_list: list[ScenarioStats]) -> None:
    """Formats and prints load test statistics into a markdown-compatible table."""
    headers = [
        "Scenario",
        "c",
        "Dur(s)",
        "Total",
        "RPS",
        "p50(ms)",
        "p95(ms)",
        "p99(ms)",
        "Max(ms)",
        "Status Breakdown",
    ]
    fmt = "| {:<20} | {:>3} | {:>6} | {:>6} | {:>8} | {:>8} | {:>8} | {:>8} | {:>8} | {:<22} |"
    sep = (
        "|-"
        + "-|-".join(
            [
                "-" * 20,
                "-" * 3,
                "-" * 6,
                "-" * 6,
                "-" * 8,
                "-" * 8,
                "-" * 8,
                "-" * 8,
                "-" * 8,
                "-" * 22,
            ]
        )
        + "-|"
    )
    print(sep)
    print(fmt.format(*headers))
    print(sep)
    for s in stats_list:
        status_str = " ".join([f"{k}:{v}" for k, v in sorted(s.status_counts.items())])
        print(
            fmt.format(
                s.scenario_name,
                s.concurrency,
                f"{s.duration_s:.1f}",
                s.total_requests,
                f"{s.rps:.1f}",
                f"{s.p50_ms:.1f}",
                f"{s.p95_ms:.1f}",
                f"{s.p99_ms:.1f}",
                f"{s.max_ms:.1f}",
                status_str[:22],
            )
        )
    print(sep)


def run_full_suite(
    base_url: str = "http://127.0.0.1:8000",
    session_id: str | None = None,
    concurrency_levels: list[int] | None = None,
    duration_per_level: float = 10.0,
    include_extended_64: bool = True,
    selected_scenarios: list[str] | None = None,
    warmup: bool = False,
    warmup_duration: float = 3.0,
) -> list[ScenarioStats]:
    """Runs all load testing scenarios and returns collected statistics."""
    if concurrency_levels is None:
        concurrency_levels = [1, 8, 32, 64]

    client = LoadTestClient(base_url=base_url, session_id=session_id)
    client.ensure_session()

    # Pre-generate multipart payloads to avoid client-side GIL/CPU generation contention
    client.warmup_payloads(["640x480", "1080p", "12mp"])

    # Pre-warm gates cache
    client.test_gates()

    scenario_registry: dict[str, tuple[str, Callable[[], RequestResult]]] = {
        "gates": ("gates", client.test_gates),
        "lookup": ("lookup", client.test_lookup),
        "search": ("search", client.test_search),
        "sessions": ("sessions list", client.test_sessions_list),
        "cycle": ("check-in+out cycle", client.test_cycle),
        "scan_640": ("scan 640x480", lambda: client.test_scan("640x480")),
        "scan_1080p": ("scan 1080p", lambda: client.test_scan("1080p")),
        "scan_12mp": ("scan 12 MP", lambda: client.test_scan("12mp")),
    }

    scenarios_to_run = (
        [s for s in selected_scenarios if s in scenario_registry]
        if selected_scenarios
        else list(scenario_registry.keys())
    )

    cold_stats: list[ScenarioStats] = []
    warm_stats: list[ScenarioStats] = []

    print(f"\n==================== LOAD TEST SUITE ({base_url}) ====================")
    print(f"Scenarios: {scenarios_to_run}")
    print(f"Levels: {concurrency_levels} (duration: {duration_per_level}s)")
    if warmup:
        print(f"Warmup: ENABLED (duration: {warmup_duration}s per scenario)")

    for sc_key in scenarios_to_run:
        sc_name, sc_fn = scenario_registry[sc_key]

        # Optional warmup phase (cold run metrics)
        if warmup:
            print(f"\n---> [WARMUP PHASE] Warming scenario: {sc_name}")
            init_c = concurrency_levels[0] if concurrency_levels else 1
            w_stats = run_scenario_concurrency(
                client=client,
                action_fn=sc_fn,
                scenario_name=f"{sc_name} (Cold-Warmup)",
                concurrency=init_c,
                duration_s=warmup_duration,
            )
            cold_stats.append(w_stats)
            print(
                f"   [Warmup c={init_c:>2}] RPS={w_stats.rps:>6.1f} | p50={w_stats.p50_ms:>5.1f}ms | p95={w_stats.p95_ms:>5.1f}ms | errors={w_stats.errors_count}"
            )

        print(f"\n---> Running scenario: {sc_name}")
        for c in concurrency_levels:
            stats = run_scenario_concurrency(
                client=client,
                action_fn=sc_fn,
                scenario_name=sc_name,
                concurrency=c,
                duration_s=duration_per_level,
            )
            warm_stats.append(stats)
            print(
                f"   [c={c:>2}] RPS={stats.rps:>6.1f} | p50={stats.p50_ms:>5.1f}ms | p95={stats.p95_ms:>5.1f}ms | errors={stats.errors_count}"
            )

        if include_extended_64 and 64 in concurrency_levels:
            print("   [c=64 EXTENDED 60s] Running endurance run...")
            stats_60s = run_scenario_concurrency(
                client=client,
                action_fn=sc_fn,
                scenario_name=f"{sc_name} (60s)",
                concurrency=64,
                duration_s=60.0,
            )
            warm_stats.append(stats_60s)
            print(
                f"   [c=64 (60s)] RPS={stats_60s.rps:>6.1f} | p50={stats_60s.p50_ms:>5.1f}ms | p95={stats_60s.p95_ms:>5.1f}ms | errors={stats_60s.errors_count}"
            )

    if warmup and cold_stats:
        print("\n\n==================== COLD RUN METRICS (WARMUP) ====================")
        print_stats_table(cold_stats)
        print(
            "\n==================== WARM RUN METRICS (STEADY STATE) ===================="
        )
        print_stats_table(warm_stats)
    else:
        print("\n\n==================== FINAL LOAD TEST SUMMARY ====================")
        print_stats_table(warm_stats)

    return warm_stats


def parse_allow_status(allow_status_str: str) -> set[int | str]:
    """
    Parses comma-separated allowed status codes or patterns.
    Supports exact integer codes (e.g. 200, 201, 503, 400) and xx wildcards (2xx, 3xx, 4xx, 5xx).
    Default: '2xx,503'
    """
    allowed: set[int | str] = set()
    for token in allow_status_str.split(","):
        token = token.strip().lower()
        if not token:
            continue
        if token.endswith("xx") and len(token) == 3 and token[0].isdigit():
            allowed.add(token)
        else:
            try:
                allowed.add(int(token))
            except ValueError:
                allowed.add(token)
    return allowed


def is_status_allowed(code: int, allowed: set[int | str]) -> bool:
    """Checks whether an integer HTTP status code satisfies the allowed set."""
    if code in allowed:
        return True
    century = f"{code // 100}xx"
    return century in allowed


def count_fatal_errors(
    stats_list: list[ScenarioStats],
    allow_status: set[int | str] | None = None,
) -> int:
    """
    Counts fatal errors across all executed scenarios per H8c:
    Any non-allowed status (defaults to 2xx responses and 503 Service Unavailable)
    or connection/protocol errors.
    """
    if allow_status is None:
        allow_status = {"2xx", 503}

    fatal = 0
    for s in stats_list:
        for code_str, count in s.status_counts.items():
            if code_str in ("ERR", "0", "None"):
                fatal += count
            else:
                try:
                    code_int = int(code_str)
                    if not is_status_allowed(code_int, allow_status):
                        fatal += count
                except ValueError:
                    fatal += count
    return fatal


def purge_test_scans() -> None:
    """
    No-op under ADR-0010 (Cloudinary Exclusive Storage).
    Scan images are streamed directly to Cloudinary; no local cleanup is required.
    """
    print("\n[CLEANUP] Cloudinary exclusive backend: direct cloud streaming.")


# Pytest entrypoint (executed when RUN_PERF_TESTS="1")
def test_perf_load_suite() -> None:
    """Automated integration assertion for load test suite."""
    target_url = os.getenv("PERF_TARGET_URL", "http://127.0.0.1:8000")
    # Quick sanity run during pytest
    stats = run_full_suite(
        base_url=target_url,
        concurrency_levels=[1, 4],
        duration_per_level=2.0,
        include_extended_64=False,
        selected_scenarios=["gates", "lookup"],
    )
    assert len(stats) >= 2
    for s in stats:
        assert s.total_requests > 0
    fatal_errors = count_fatal_errors(stats)
    assert fatal_errors == 0, f"Detected {fatal_errors} fatal request errors"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parking Management Backend Load Test Suite"
    )
    parser.add_argument(
        "--target-url", default="http://127.0.0.1:8000", help="Base backend URL"
    )
    parser.add_argument("--session-id", default=None, help="Explicit sessionid cookie")
    parser.add_argument(
        "--concurrency", default="1,8,32,64", help="Comma-separated concurrency levels"
    )
    parser.add_argument(
        "--duration", type=float, default=10.0, help="Duration in seconds per level"
    )
    parser.add_argument("--scenario", default="all", help="Specific scenario or 'all'")
    parser.add_argument(
        "--no-extended-64", action="store_true", help="Skip 60s test at concurrency 64"
    )
    parser.add_argument(
        "--allow-status",
        default="2xx,503",
        help="Comma-separated allowed HTTP status codes or patterns (default: '2xx,503')",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Enable pre-warmup phase and report both cold and warm metrics",
    )
    parser.add_argument(
        "--warmup-duration",
        type=float,
        default=3.0,
        help="Duration in seconds for warmup phase (default: 3.0s)",
    )
    parser.add_argument(
        "--purge-scans",
        action="store_true",
        help="No-op compatibility flag under ADR-0010 (Cloudinary Exclusive Storage)",
    )
    args = parser.parse_args()

    levels = [int(x.strip()) for x in args.concurrency.split(",") if x.strip()]
    scenarios = (
        None
        if args.scenario == "all"
        else [x.strip() for x in args.scenario.split(",")]
    )

    all_stats = run_full_suite(
        base_url=args.target_url,
        session_id=args.session_id,
        concurrency_levels=levels,
        duration_per_level=args.duration,
        include_extended_64=not args.no_extended_64,
        selected_scenarios=scenarios,
        warmup=args.warmup,
        warmup_duration=args.warmup_duration,
    )

    if args.purge_scans:
        purge_test_scans()

    allowed_set = parse_allow_status(args.allow_status)
    fatal_errors = count_fatal_errors(all_stats, allow_status=allowed_set)
    if fatal_errors > 0:
        print(
            f"\n[FATAL] Load test detected {fatal_errors} unexpected status codes (outside --allow-status={args.allow_status}) or connection errors!",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n[SUCCESS] Load test completed with 0 fatal errors.")
