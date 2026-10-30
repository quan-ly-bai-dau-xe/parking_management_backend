"""
HTTP Recognition Benchmark over 322 Vietnamese License Plate Dataset Images.
Evaluates the full pipeline (/api/v1/parking/plate-scans/) in Docker container.
Runs cleanly with `python -I` outside/inside the repo.
Evaluates Tuning Split (161 even-indexed rows) and Test Split (161 odd-indexed rows).
Reports:
- Exact match
- Character accuracy
- AUTO coverage
- Wrong in AUTO
- Per-reason counts (MODEL_DISAGREEMENT, LOW_CHAR_CONFIDENCE, INVALID_FORMAT, NO_DETECTION_RETRY)
- Latency p50 / p95
"""

import argparse
import hashlib
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXPECTED_PARQUET_SHA256 = (
    "843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b"
)


def resolve_dataset_parquet_path(
    cli_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
) -> Path:
    """
    Dynamically resolves the 322 Vietnamese license plate Parquet dataset path:
    1. Explicit CLI argument (--parquet-path or --dataset-dir)
    2. Environment variables: PARQUET_PATH, PARKING_DATASET_PATH, DATASET_PATH
    3. HuggingFace environment variables: HUGGINGFACE_HUB_CACHE, HF_HOME
    4. Fallback default: Path.home() / ".cache" / "huggingface" / "hub"
    5. Discovers snapshot parquet via glob search inside datasets--sonnetechnology--license-plate-text-recognition-full
    """
    if cli_path:
        p = Path(cli_path).resolve()
        if p.is_file():
            return p
        if p.is_dir():
            candidates = list(p.glob("**/test-*.parquet")) or list(
                p.glob("**/*.parquet")
            )
            if candidates:
                return candidates[0]
        raise FileNotFoundError(f"Provided dataset path not found: {cli_path}")

    for env_var in ("PARQUET_PATH", "PARKING_DATASET_PATH", "DATASET_PATH"):
        val = os.getenv(env_var)
        if val:
            p = Path(val).resolve()
            if p.is_file():
                return p
            if p.is_dir():
                candidates = list(p.glob("**/test-*.parquet")) or list(
                    p.glob("**/*.parquet")
                )
                if candidates:
                    return candidates[0]
            raise FileNotFoundError(f"Dataset path from {env_var}={val} not found.")

    hub_root: Path | None = None
    if cache_dir:
        hub_root = Path(cache_dir).resolve()
    elif os.getenv("HUGGINGFACE_HUB_CACHE"):
        hub_root = Path(os.environ["HUGGINGFACE_HUB_CACHE"]).resolve()
    elif os.getenv("HF_HOME"):
        hub_root = Path(os.environ["HF_HOME"]).resolve() / "hub"
    else:
        hub_root = Path.home() / ".cache" / "huggingface" / "hub"

    dataset_repo_dir = (
        hub_root / "datasets--sonnetechnology--license-plate-text-recognition-full"
    )
    if dataset_repo_dir.is_dir():
        candidates = list(dataset_repo_dir.glob("snapshots/**/data/*.parquet")) or list(
            dataset_repo_dir.glob("**/*.parquet")
        )
        if candidates:
            return candidates[0]

    raise FileNotFoundError(
        f"322-plate dataset Parquet not found in {dataset_repo_dir}.\n"
        "Please provide --parquet-path /path/to/test-*.parquet or set PARQUET_PATH environment variable.\n"
        "To download the dataset outside repository without committing data:\n"
        '  python -c "from huggingface_hub import snapshot_download; '
        "snapshot_download('sonnetechnology/license-plate-text-recognition-full', repo_type='dataset')\""
    )


def normalize_plate(text: str | None) -> str:
    """Normalizes plate text: removes separators and uppercase."""
    if not text:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", text).upper()


def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between s1 and s2."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            deletions = curr[j] + 1
            subs = prev[j] + (c1 != c2)
            curr.append(min(ins, deletions, subs))
        prev = curr
    return prev[-1]


def compute_percentile(data: list[float], pct: float) -> float:
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


@dataclass
class ScanEvaluationResult:
    row_index: int
    split: str  # "tuning" or "test"
    gt_raw: str
    gt_norm: str
    pred_norm: str
    is_exact_match: bool
    edit_distance: int
    max_len: int
    review_status: str
    review_reasons: list[str] = field(default_factory=list)
    corrections: list[dict[str, Any]] = field(default_factory=list)
    min_char_confidence: float | None = None
    confidence: float | None = None
    latency_ms: float = 0.0
    http_status: int = 200
    error: str | None = None


@dataclass
class SplitMetrics:
    split_name: str
    total_images: int
    exact_matches: int
    exact_match_pct: float
    total_edit_distance: int
    total_characters: int
    char_accuracy_pct: float
    auto_count: int
    auto_coverage_pct: float
    wrong_in_auto: int
    wrong_in_auto_pct: float
    needs_review_count: int
    reason_counts: dict[str, int]
    latency_p50_ms: float
    latency_p95_ms: float
    latency_avg_ms: float


def generate_csrf_pair() -> tuple[str, str]:
    """Generates a valid Django CSRF secret and masked token pair."""
    import random
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


def send_multipart_image(
    url: str,
    image_bytes: bytes,
    filename: str = "plate.jpg",
    session_id: str = "",
    csrf_token: str = "",
    timeout_s: float = 20.0,
) -> tuple[int, dict[str, Any], float]:
    """Sends multipart/form-data POST request using standard library urllib."""
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = io.BytesIO()

    # Part: image file
    body.write(f"--{boundary}\r\n".encode())
    body.write(
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode()
    )
    body.write(b"Content-Type: image/jpeg\r\n\r\n")
    body.write(image_bytes)
    body.write(b"\r\n")

    # Closing boundary
    body.write(f"--{boundary}--\r\n".encode())
    payload = body.getvalue()

    csrf_cookie, csrf_header = generate_csrf_pair()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(payload)))
    req.add_header("Accept", "application/json")
    if session_id:
        req.add_header("Cookie", f"sessionid={session_id}; csrftoken={csrf_cookie}")
        req.add_header("X-CSRFToken", csrf_header)

    t0 = time.perf_counter()
    status_code = 200
    resp_dict: dict[str, Any] = {}

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            status_code = response.getcode()
            resp_body = response.read().decode("utf-8")
            resp_dict = json.loads(resp_body)
    except urllib.error.HTTPError as http_err:
        status_code = http_err.code
        try:
            err_body = http_err.read().decode("utf-8")
            resp_dict = json.loads(err_body)
        except Exception:
            resp_dict = {"raw_error": str(http_err)}
    except Exception as exc:
        status_code = 0
        resp_dict = {"error": str(exc)}

    latency_ms = (time.perf_counter() - t0) * 1000.0
    return status_code, resp_dict, latency_ms


def evaluate_split_metrics(
    results: list[ScanEvaluationResult], split_name: str
) -> SplitMetrics:
    """Calculates aggregate benchmark metrics for a specific subset."""
    total = len(results)
    if total == 0:
        return SplitMetrics(
            split_name=split_name,
            total_images=0,
            exact_matches=0,
            exact_match_pct=0.0,
            total_edit_distance=0,
            total_characters=0,
            char_accuracy_pct=0.0,
            auto_count=0,
            auto_coverage_pct=0.0,
            wrong_in_auto=0,
            wrong_in_auto_pct=0.0,
            needs_review_count=0,
            reason_counts={},
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            latency_avg_ms=0.0,
        )

    exact_matches = sum(1 for r in results if r.is_exact_match)
    total_dist = sum(r.edit_distance for r in results)
    total_chars = sum(r.max_len for r in results)
    char_acc = (1.0 - (total_dist / total_chars)) * 100.0 if total_chars > 0 else 0.0

    auto_results = [r for r in results if r.review_status == "AUTO"]
    auto_count = len(auto_results)
    auto_coverage = (auto_count / total) * 100.0

    wrong_in_auto = sum(1 for r in auto_results if not r.is_exact_match)
    wrong_in_auto_pct = (wrong_in_auto / auto_count) * 100.0 if auto_count > 0 else 0.0

    needs_review = [r for r in results if r.review_status != "AUTO"]
    reason_counts: dict[str, int] = {}
    for r in results:
        for reason in r.review_reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    latencies = sorted([r.latency_ms for r in results])
    p50 = compute_percentile(latencies, 50.0)
    p95 = compute_percentile(latencies, 95.0)
    avg_lat = sum(latencies) / len(latencies)

    return SplitMetrics(
        split_name=split_name,
        total_images=total,
        exact_matches=exact_matches,
        exact_match_pct=(exact_matches / total) * 100.0,
        total_edit_distance=total_dist,
        total_characters=total_chars,
        char_accuracy_pct=char_acc,
        auto_count=auto_count,
        auto_coverage_pct=auto_coverage,
        wrong_in_auto=wrong_in_auto,
        wrong_in_auto_pct=wrong_in_auto_pct,
        needs_review_count=len(needs_review),
        reason_counts=reason_counts,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_avg_ms=avg_lat,
    )


def print_metrics_report(
    tuning: SplitMetrics, test: SplitMetrics, overall: SplitMetrics
) -> None:
    """Prints comprehensive benchmark summary table."""
    print("\n" + "=" * 80)
    print("       322 VIETNAMESE LICENSE PLATE HTTP OCR BENCHMARK REPORT")
    print("=" * 80)

    print(
        f"{'Metric':<32} | {'Tuning (161)':<14} | {'Test (161)':<14} | {'Overall (322)':<14}"
    )
    print("-" * 80)
    print(
        f"{'Exact Match':<32} | {tuning.exact_matches:>3}/{tuning.total_images} ({tuning.exact_match_pct:5.2f}%) | {test.exact_matches:>3}/{test.total_images} ({test.exact_match_pct:5.2f}%) | {overall.exact_matches:>3}/{overall.total_images} ({overall.exact_match_pct:5.2f}%)"
    )
    print(
        f"{'Character Accuracy':<32} | {tuning.char_accuracy_pct:13.2f}% | {test.char_accuracy_pct:13.2f}% | {overall.char_accuracy_pct:13.2f}%"
    )
    print(
        f"{'AUTO Coverage':<32} | {tuning.auto_count:>3}/{tuning.total_images} ({tuning.auto_coverage_pct:5.2f}%) | {test.auto_count:>3}/{test.total_images} ({test.auto_coverage_pct:5.2f}%) | {overall.auto_count:>3}/{overall.total_images} ({overall.auto_coverage_pct:5.2f}%)"
    )
    print(
        f"{'Wrong in AUTO':<32} | {tuning.wrong_in_auto:>3}/{tuning.auto_count} ({tuning.wrong_in_auto_pct:5.2f}%) | {test.wrong_in_auto:>3}/{test.auto_count} ({test.wrong_in_auto_pct:5.2f}%) | {overall.wrong_in_auto:>3}/{overall.auto_count} ({overall.wrong_in_auto_pct:5.2f}%)"
    )
    print(
        f"{'NEEDS_REVIEW Count':<32} | {tuning.needs_review_count:>14} | {test.needs_review_count:>14} | {overall.needs_review_count:>14}"
    )
    print(
        f"{'Latency p50 (ms)':<32} | {tuning.latency_p50_ms:12.1f} ms | {test.latency_p50_ms:12.1f} ms | {overall.latency_p50_ms:12.1f} ms"
    )
    print(
        f"{'Latency p95 (ms)':<32} | {tuning.latency_p95_ms:12.1f} ms | {test.latency_p95_ms:12.1f} ms | {overall.latency_p95_ms:12.1f} ms"
    )
    print(
        f"{'Latency Avg (ms)':<32} | {tuning.latency_avg_ms:12.1f} ms | {test.latency_avg_ms:12.1f} ms | {overall.latency_avg_ms:12.1f} ms"
    )
    print("-" * 80)
    print("Review Reasons Breakdown (Counts):")
    all_reasons = sorted(
        set(
            list(tuning.reason_counts.keys())
            + list(test.reason_counts.keys())
            + list(overall.reason_counts.keys())
        )
    )
    for r in all_reasons:
        t_c = tuning.reason_counts.get(r, 0)
        te_c = test.reason_counts.get(r, 0)
        o_c = overall.reason_counts.get(r, 0)
        print(f"  - {r:<30}: Tuning={t_c:<3} | Test={te_c:<3} | Total={o_c:<3}")
    print("=" * 80 + "\n")


def run_benchmark(
    parquet_path: Path,
    target_url: str = "http://127.0.0.1:8000/api/v1/parking/plate-scans/",
    session_id: str = "",
    csrf_token: str = "csrftoken_benchmark_token_32chars",
    limit: int | None = None,
) -> tuple[SplitMetrics, SplitMetrics, SplitMetrics]:
    """Executes the full 322 dataset benchmark over HTTP."""
    import pyarrow.parquet as pq

    # Verify SHA-256
    print(f"Verifying SHA-256 of Parquet file: {parquet_path}")
    hasher = hashlib.sha256()
    with open(parquet_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    actual_sha256 = hasher.hexdigest()
    assert actual_sha256 == EXPECTED_PARQUET_SHA256, (
        f"SHA-256 mismatch! Expected {EXPECTED_PARQUET_SHA256}, got {actual_sha256}"
    )
    print(f"SHA-256 verified successfully: {actual_sha256}")

    table = pq.read_table(str(parquet_path))
    print(f"Total rows in Parquet table: {len(table)}")

    # Filter Vietnamese plates matching 2-digit province code + series letter
    vn_plate_indices: list[int] = []
    for i in range(len(table)):
        target_val = table["target"][i].as_py()
        if target_val and len(target_val) > 0:
            raw_text = target_val[0]
            if re.match(r"^\d{2}[A-Z]", raw_text):
                vn_plate_indices.append(i)

    print(
        f"Extracted {len(vn_plate_indices)} Vietnamese plate rows from Parquet table."
    )
    if len(vn_plate_indices) > 322:
        vn_plate_indices = vn_plate_indices[:322]
    assert len(vn_plate_indices) == 322, (
        f"Expected exactly 322 Vietnamese rows, got {len(vn_plate_indices)}"
    )

    if limit is not None:
        vn_plate_indices = vn_plate_indices[:limit]

    eval_results: list[ScanEvaluationResult] = []

    print(
        f"\nStarting HTTP benchmark against {target_url} (Session ID provided: {bool(session_id)})..."
    )

    for idx, table_idx in enumerate(vn_plate_indices):
        split = "tuning" if (idx % 2 == 0) else "test"
        gt_raw = table["target"][table_idx].as_py()[0]
        gt_norm = normalize_plate(gt_raw)
        img_bytes = table["image"][table_idx].as_py()["bytes"]

        status, resp_data, latency_ms = send_multipart_image(
            url=target_url,
            image_bytes=img_bytes,
            filename=f"plate_{idx}_{gt_norm}.jpg",
            session_id=session_id,
            csrf_token=csrf_token,
        )

        data = resp_data.get("data", resp_data)
        review_status = data.get("review_status", "NEEDS_REVIEW")
        review_reasons = data.get("review_reasons", [])
        corrections = data.get("corrections", [])

        candidates = data.get("candidates", [])
        best_cand = candidates[0] if candidates else {}
        pred_norm = best_cand.get("plate_normalized", "")
        min_char_conf = best_cand.get("min_char_confidence")
        conf = best_cand.get("confidence")

        is_exact = pred_norm == gt_norm
        dist = levenshtein_distance(gt_norm, pred_norm)
        max_l = max(len(gt_norm), len(pred_norm))

        res = ScanEvaluationResult(
            row_index=idx,
            split=split,
            gt_raw=gt_raw,
            gt_norm=gt_norm,
            pred_norm=pred_norm,
            is_exact_match=is_exact,
            edit_distance=dist,
            max_len=max_l,
            review_status=review_status,
            review_reasons=review_reasons,
            corrections=corrections,
            min_char_confidence=min_char_conf,
            confidence=conf,
            latency_ms=latency_ms,
            http_status=status,
        )
        eval_results.append(res)

        if (idx + 1) % 50 == 0 or (idx + 1) == len(vn_plate_indices):
            print(
                f"Processed {idx + 1:>3}/{len(vn_plate_indices)} images | Last: GT={gt_norm:<8} PRED={pred_norm:<8} MATCH={is_exact} STATUS={review_status:<12} LAT={latency_ms:5.1f}ms"
            )

    tuning_results = [r for r in eval_results if r.split == "tuning"]
    test_results = [r for r in eval_results if r.split == "test"]

    tuning_metrics = evaluate_split_metrics(tuning_results, "Tuning (161)")
    test_metrics = evaluate_split_metrics(test_results, "Test (161)")
    overall_metrics = evaluate_split_metrics(eval_results, "Overall (322)")

    print_metrics_report(tuning_metrics, test_metrics, overall_metrics)
    return tuning_metrics, test_metrics, overall_metrics


def purge_benchmark_scans() -> None:
    """
    No-op under ADR-0010 (Cloudinary Exclusive Storage).
    Scan images are streamed directly to Cloudinary; no local cleanup is required.
    """
    print("\n[CLEANUP] Cloudinary exclusive backend: direct cloud streaming.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Benchmark 322 Vietnamese Plate Images via HTTP"
    )
    parser.add_argument(
        "--parquet-path",
        default=None,
        help="Path to dataset Parquet file (defaults to dynamic resolution via HF cache or PARQUET_PATH)",
    )
    parser.add_argument(
        "--target-url",
        default="http://127.0.0.1:8000/api/v1/parking/plate-scans/",
        help="HTTP endpoint URL for plate scan",
    )
    parser.add_argument(
        "--session-id",
        default="",
        help="Session ID cookie for authentication",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of images to benchmark (for dry-run)",
    )
    parser.add_argument(
        "--purge-scans",
        action="store_true",
        help="No-op compatibility flag under ADR-0010 (Cloudinary Exclusive Storage)",
    )
    args = parser.parse_args()

    resolved_path = resolve_dataset_parquet_path(args.parquet_path)
    run_benchmark(
        parquet_path=resolved_path,
        target_url=args.target_url,
        session_id=args.session_id,
        limit=args.limit,
    )

    if args.purge_scans:
        purge_benchmark_scans()
