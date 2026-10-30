"""Three-way label quality triage, human review kit generator, and manifest export converter."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import random
import re
import sys
import types
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

from plate_training.cache import ensure_cache_dir
from plate_training.manifest import ManifestItem, save_manifest
from plate_training.normalization import normalize_plate
from plate_training.pool import CandidateInstance

logger = logging.getLogger("plate_training.triage")

# Fast-plate-ocr Latin vocabulary and padding constant
CCT_XS_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
CCT_XS_PAD_CHAR = "_"

# Vietnamese civilian car plate regex (standard one-line)
CAR_PLATE_STANDARD_REGEX = re.compile(r"^[0-9]{2}[A-Z][0-9]{4,5}$")
MILITARY_PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{4,5}$")

# Authorized civilian car single-letter series: 20 letters (excludes I, J, O, Q, R, W)
CIVILIAN_CAR_SERIES_LETTERS = frozenset(
    {
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "K",
        "L",
        "M",
        "N",
        "P",
        "S",
        "T",
        "U",
        "V",
        "X",
        "Y",
        "Z",
    }
)

# Agency codes excluded from civilian training
AGENCY_CODES = frozenset({"80"})

# Never-issued province codes
NEVER_ISSUED_CODES = frozenset({"13", "42", "44", "45", "46", "87", "91", "96"})

# Valid issued province codes (11..99 excluding never-issued)
VALID_PROVINCE_CODES = frozenset(
    f"{i:02d}" for i in range(11, 100) if f"{i:02d}" not in NEVER_ISSUED_CODES
)


@dataclass
class TriageRecord:
    """Represents a single evaluated instance under 3-way label quality triage."""

    instance_id: str
    source_split: str
    reading_trocr: str
    reading_prod_backend: str
    reading_cct_xs: str
    syntax_verdict: str
    syntax_message: str
    triage_group: str  # "A" | "B" | "C"
    crop_filename: str
    crop_sha256: str
    photo_sha256: str
    group_id: str
    is_quarantined: bool = False
    is_frozen_test: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert triage record to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriageRecord:
        """Construct TriageRecord from dictionary."""
        return cls(
            instance_id=str(data["instance_id"]),
            source_split=str(data["source_split"]),
            reading_trocr=str(data.get("reading_trocr", "")),
            reading_prod_backend=str(data.get("reading_prod_backend", "")),
            reading_cct_xs=str(data.get("reading_cct_xs", "")),
            syntax_verdict=str(data.get("syntax_verdict", "UNKNOWN")),
            syntax_message=str(data.get("syntax_message", "")),
            triage_group=str(data.get("triage_group", "C")),
            crop_filename=str(data.get("crop_filename", "")),
            crop_sha256=str(data.get("crop_sha256", "")),
            photo_sha256=str(data.get("photo_sha256", "")),
            group_id=str(data.get("group_id", "")),
            is_quarantined=bool(data.get("is_quarantined", False)),
            is_frozen_test=bool(data.get("is_frozen_test", False)),
        )


def is_civilian_car_one_line(plate_norm: str) -> bool:
    """
    Validate that normalized plate text conforms to civilian one-line car syntax.

    Statutory rules:
    - Length must be 7 characters (legacy 4-digit) or 8 characters (standard 5-digit).
    - Province code must be in VALID_PROVINCE_CODES and NOT in AGENCY_CODES ('80').
    - Series letter must be in CIVILIAN_CAR_SERIES_LETTERS (20 letters).
    - Tail must be 4 or 5 digits.
    """
    if not plate_norm or not (7 <= len(plate_norm) <= 8):
        return False
    if not CAR_PLATE_STANDARD_REGEX.match(plate_norm):
        return False
    prov = plate_norm[:2]
    if prov in AGENCY_CODES or prov not in VALID_PROVINCE_CODES:
        return False
    series_char = plate_norm[2]
    return series_char in CIVILIAN_CAR_SERIES_LETTERS


def classify_plate_syntax_rules(plate_norm: str) -> tuple[str, str]:
    """
    Classify normalized plate syntax into 'VALID', 'UNKNOWN_PLATE_PATTERN', or 'INVALID_FORMAT'.
    Bridges with apps.parking.data.vn_plate_rules when available.
    """
    try:
        from apps.parking.data.vn_plate_rules import classify_plate_syntax

        return classify_plate_syntax(plate_norm)
    except ImportError:
        # Fallback implementation using statutory constants
        if not plate_norm or not plate_norm.isascii() or not plate_norm.isalnum():
            return "INVALID_FORMAT", "Invalid characters or empty string."
        if MILITARY_PLATE_REGEX.match(plate_norm):
            return "UNKNOWN_PLATE_PATTERN", "Military plate series."
        if not (7 <= len(plate_norm) <= 9):
            return "INVALID_FORMAT", "Length outside 7-9 characters."
        prov = plate_norm[:2]
        if prov in NEVER_ISSUED_CODES:
            return "UNKNOWN_PLATE_PATTERN", f"Province code '{prov}' is never issued."
        if prov not in VALID_PROVINCE_CODES:
            return "UNKNOWN_PLATE_PATTERN", f"Province code '{prov}' is unrecognized."
        if is_civilian_car_one_line(plate_norm):
            return "VALID", "Compliant Vietnamese civilian car plate."
        return "UNKNOWN_PLATE_PATTERN", "Special series or non-standard format."


def triage_readings(
    r1: str,
    r2: str,
    r3: str,
) -> tuple[str, str, str]:
    """
    Perform 3-way triage on three independent readings:
      r1: TrOCR dataset label (normalized)
      r2: Production backend recognizer (normalized)
      r3: Published CCT-XS recognizer (normalized)

    Classification rules:
      Group A: All three readings equal and valid civilian car one-line syntax.
      Group B: Any disagreement among the three readings, where at least one reading
               is valid civilian car syntax or recoverable format.
      Group C: Invalid or out-of-scope format (military, special series LD/NG/etc.,
               agency 80, motorbike, invalid garbage).

    Returns:
      (triage_group, syntax_verdict, syntax_message)
    """
    r1_norm = normalize_plate(r1)
    r2_norm = normalize_plate(r2)
    r3_norm = normalize_plate(r3)

    # 1. Consensus check
    if r1_norm == r2_norm == r3_norm:
        if is_civilian_car_one_line(r1_norm):
            return "A", "VALID", "Compliant civilian car one-line consensus."
        v, msg = classify_plate_syntax_rules(r1_norm)
        return "C", v, f"Out-of-scope or non-civilian plate format: {msg}"

    # 2. Disagreement check: check if any reading is a valid civilian car plate
    has_valid_civilian = (
        is_civilian_car_one_line(r1_norm)
        or is_civilian_car_one_line(r2_norm)
        or is_civilian_car_one_line(r3_norm)
    )
    if has_valid_civilian:
        return (
            "B",
            "DISAGREEMENT",
            "Disagreement among readings; recoverable civilian car plate format.",
        )

    # None of the readings is a valid civilian car plate
    v, msg = classify_plate_syntax_rules(r1_norm)
    return "C", v, f"Out-of-scope or invalid readings across all sources: {msg}"


def setup_zero_orm_backend(threads: int = 4) -> tuple[Any, Any]:
    """
    Initialize FastAlprPlateRecognizer without database or ORM dependencies.
    Configures minimal Django settings if not configured, and stubs apps.parking.services.
    """
    import django
    from django.conf import settings

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    if not settings.configured:
        models_dir = (
            Path.home() / ".cache" / "fast-plate-ocr" / "cct-xs-v2-global-model"
        )
        settings.configure(
            ONNX_INTRA_OP_THREADS=threads,
            ONNX_INTER_OP_THREADS=1,
            ONNX_ALLOW_SPINNING=False,
            PARKING_OCR_MODELS_DIR=str(models_dir),
            PARKING_OCR_CROP_MARGIN=4,
            PARKING_OCR_ADAPTIVE_ENSEMBLE=True,
            PARKING_OCR_ADAPTIVE_THRESHOLD=94.0,
            PARKING_OCR_LEADING_CHAR_THRESHOLD=99.2,
            PARKING_OCR_ADAPTIVE_AVG_THRESHOLD=96.0,
            PARKING_OCR_ENGINE="fast_alpr",
        )
        django.setup()

    if "apps.parking.services" not in sys.modules:
        pkg = types.ModuleType("apps.parking.services")
        pkg.__path__ = [str(repo_root / "apps" / "parking" / "services")]
        sys.modules["apps.parking.services"] = pkg

    from apps.parking.services.ocr import FastAlprPlateRecognizer
    from apps.parking.services.plate_correction import correct_plate_characters

    recognizer = FastAlprPlateRecognizer()
    recognizer.warmup()
    return recognizer, correct_plate_characters


def init_cct_xs_session(
    threads: int = 4,
    onnx_path: str | Path | None = None,
) -> ort.InferenceSession:
    """Initialize standalone CCT-XS ONNX Runtime session."""
    if onnx_path is None:
        onnx_path = (
            Path.home()
            / ".cache"
            / "fast-plate-ocr"
            / "cct-xs-v2-global-model"
            / "cct_xs_v2_global.onnx"
        )
    resolved_path = Path(onnx_path)
    if not resolved_path.is_file():
        raise FileNotFoundError(f"CCT-XS ONNX model not found at {resolved_path}")

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.log_severity_level = 3
    session = ort.InferenceSession(
        str(resolved_path), opts, providers=["CPUExecutionProvider"]
    )
    # Warmup
    dummy = np.zeros((1, 64, 128, 3), dtype=np.uint8)
    session.run(None, {"input": dummy})
    return session


def predict_cct_xs(
    session: ort.InferenceSession,
    image_input: np.ndarray | Image.Image,
) -> str:
    """Run standalone CCT-XS inference on a 64x128 RGB crop."""
    if isinstance(image_input, Image.Image):
        img_rgb = np.asarray(image_input.convert("RGB"))
    else:
        img_rgb = image_input

    if img_rgb.shape[:2] != (64, 128):
        img_rgb = cv2.resize(img_rgb, (128, 64), interpolation=cv2.INTER_LINEAR)

    batch = np.expand_dims(img_rgb, axis=0)  # (1, 64, 128, 3) uint8
    raw_out = session.run(None, {"input": batch})[0]  # (1, 10, 37)
    pred_indices = np.argmax(raw_out[0], axis=-1)
    chars = [CCT_XS_ALPHABET[idx] for idx in pred_indices]
    plate_str = "".join(chars).rstrip(CCT_XS_PAD_CHAR)
    return normalize_plate(plate_str)


def predict_prod_backend(
    recognizer: Any,
    correct_fn: Any,
    image_input: np.ndarray | Image.Image,
) -> str:
    """Run production FastAlprPlateRecognizer + review policy correction on crop or full photo."""
    if isinstance(image_input, np.ndarray):
        pil_img = Image.fromarray(image_input)
    else:
        pil_img = image_input

    scan = recognizer.recognize(pil_img)
    cand = scan.best_candidate
    if cand and cand.plate_normalized:
        corrected, _ = correct_fn(cand.plate_normalized)
        return normalize_plate(corrected)
    return ""


def run_triage(
    cache_dir: str | Path | None = None,
    candidate_pool_path: str | Path | None = None,
    frozen_labels_path: str | Path | None = None,
    output_summary_path: str | Path | None = None,
    output_records_path: str | Path | None = None,
    threads: int = 4,
    force: bool = False,
) -> tuple[list[TriageRecord], dict[str, Any]]:
    """
    Execute 3-way label quality triage on:
    1. Clean candidate pool instances (2,569)
    2. Quarantine instances (257)
    3. Frozen test benchmark instances (322)

    Computes R1 (TrOCR), R2 (FastAlprPlateRecognizer), R3 (CCT-XS) + syntax rules.
    Outputs aggregate summary JSON containing zero plate strings.
    """
    resolved_cache = ensure_cache_dir(cache_dir)
    target_pool = (
        Path(candidate_pool_path)
        if candidate_pool_path
        else resolved_cache / "candidate_pool.json"
    )
    target_bench = (
        Path(frozen_labels_path)
        if frozen_labels_path
        else resolved_cache / "benchmark_322_labels.json"
    )
    target_summary = (
        Path(output_summary_path)
        if output_summary_path
        else resolved_cache / "triage_summary.json"
    )

    if not target_pool.is_file():
        raise FileNotFoundError(f"Candidate pool file not found at {target_pool}")
    if not target_bench.is_file():
        raise FileNotFoundError(
            f"Frozen test benchmark labels not found at {target_bench}"
        )

    # Check cached summary if not force
    if target_summary.is_file() and not force:
        logger.info(
            "Found existing triage summary at %s (use force=True to recompute)",
            target_summary,
        )

    # Initialize engines
    logger.info(
        "Initializing isolated Zero-ORM production recognizer (threads=%d)...", threads
    )
    recognizer, correct_fn = setup_zero_orm_backend(threads=threads)

    logger.info("Initializing standalone CCT-XS session (threads=%d)...", threads)
    cct_session = init_cct_xs_session(threads=threads)

    # 1. Process candidate pool (2,826 instances)
    logger.info("Loading candidate pool from %s...", target_pool)
    with open(target_pool, encoding="utf-8") as f:
        raw_pool = json.load(f)

    pool_instances = [CandidateInstance.from_dict(d) for d in raw_pool]
    crops_dir = resolved_cache / "crops"
    bench_crops_dir = resolved_cache / "crops_322"

    records: list[TriageRecord] = []
    clean_counts = {"A": 0, "B": 0, "C": 0}
    q_counts = {"A": 0, "B": 0, "C": 0}

    logger.info("Evaluating %d candidate pool instances...", len(pool_instances))
    for it in pool_instances:
        r1 = normalize_plate(it.raw_label)
        crop_path = crops_dir / it.crop_filename
        if not crop_path.is_file():
            raise FileNotFoundError(f"Crop image missing: {crop_path}")

        with Image.open(crop_path) as crop_image:
            crop_rgb = crop_image.convert("RGB")
            r3 = predict_cct_xs(cct_session, crop_rgb)
            r2 = predict_prod_backend(recognizer, correct_fn, crop_rgb)

        grp, s_verdict, s_msg = triage_readings(r1, r2, r3)
        rec = TriageRecord(
            instance_id=it.instance_id,
            source_split=it.source_split,
            reading_trocr=r1,
            reading_prod_backend=r2,
            reading_cct_xs=r3,
            syntax_verdict=s_verdict,
            syntax_message=s_msg,
            triage_group=grp,
            crop_filename=it.crop_filename,
            crop_sha256=it.crop_sha256,
            photo_sha256=it.photo_sha256,
            group_id=it.group_id,
            is_quarantined=it.quarantined,
            is_frozen_test=False,
        )
        records.append(rec)

        if it.quarantined:
            q_counts[grp] += 1
        else:
            clean_counts[grp] += 1

    # 2. Process 322 frozen-test benchmark images
    logger.info("Loading frozen test benchmark labels from %s...", target_bench)
    with open(target_bench, encoding="utf-8") as f:
        bench_items = json.load(f)

    # Optional parquet for full-photo reading if available
    parquet_path = resolved_cache / "test-00000-of-00001-a359b6560048e51f.parquet"
    test_table: Any = None
    if parquet_path.is_file():
        import pyarrow.parquet as pq

        test_table = pq.read_table(str(parquet_path))

    bench_counts = {"A": 0, "B": 0, "C": 0}
    prod_disagreements_crop = 0
    prod_disagreements_full = 0

    logger.info("Evaluating %d frozen test benchmark images...", len(bench_items))
    for it in bench_items:
        r1 = normalize_plate(it["plate_text"])
        crop_name = it["crop_filename"]
        crop_path = bench_crops_dir / crop_name

        with Image.open(crop_path) as crop_image:
            crop_rgb = crop_image.convert("RGB")
            r3 = predict_cct_xs(cct_session, crop_rgb)
            r2_crop = predict_prod_backend(recognizer, correct_fn, crop_rgb)

        if r2_crop != r1:
            prod_disagreements_crop += 1

        r2_final = r2_crop
        # Full photo reading if table available
        if test_table is not None:
            t_row = it.get("table_row_index", it.get("row_index"))
            raw_bytes = test_table["image"][t_row].as_py()["bytes"]
            with Image.open(io.BytesIO(raw_bytes)) as full_image:
                r2_full = predict_prod_backend(
                    recognizer, correct_fn, full_image.convert("RGB")
                )
            if r2_full != r1:
                prod_disagreements_full += 1
            # Production baseline on frozen test standard evaluates on full photo
            r2_final = r2_full

        grp, s_verdict, s_msg = triage_readings(r1, r2_final, r3)
        bench_counts[grp] += 1

        rec = TriageRecord(
            instance_id=f"frozen_test_{it['row_index']:03d}",
            source_split="frozen-test",
            reading_trocr=r1,
            reading_prod_backend=r2_final,
            reading_cct_xs=r3,
            syntax_verdict=s_verdict,
            syntax_message=s_msg,
            triage_group=grp,
            crop_filename=crop_name,
            crop_sha256="",
            photo_sha256="",
            group_id=f"frozen_test_{it['row_index']:03d}",
            is_quarantined=False,
            is_frozen_test=True,
        )
        records.append(rec)

    # Compile aggregate summary (0 plate strings)
    total_clean = sum(clean_counts.values())
    total_q = sum(q_counts.values())
    total_bench = sum(bench_counts.values())
    total_all = total_clean + total_q + total_bench

    summary: dict[str, Any] = {
        "total_instances_evaluated": total_all,
        "clean_candidate_pool": {
            "total": total_clean,
            "group_a": {
                "count": clean_counts["A"],
                "pct": round(clean_counts["A"] / total_clean * 100, 2),
            },
            "group_b": {
                "count": clean_counts["B"],
                "pct": round(clean_counts["B"] / total_clean * 100, 2),
            },
            "group_c": {
                "count": clean_counts["C"],
                "pct": round(clean_counts["C"] / total_clean * 100, 2),
            },
        },
        "quarantine_pool": {
            "total": total_q,
            "group_a": {
                "count": q_counts["A"],
                "pct": round(q_counts["A"] / total_q * 100, 2),
            },
            "group_b": {
                "count": q_counts["B"],
                "pct": round(q_counts["B"] / total_q * 100, 2),
            },
            "group_c": {
                "count": q_counts["C"],
                "pct": round(q_counts["C"] / total_q * 100, 2),
            },
        },
        "frozen_test_benchmark": {
            "total": total_bench,
            "group_a": {
                "count": bench_counts["A"],
                "pct": round(bench_counts["A"] / total_bench * 100, 2),
            },
            "group_b": {
                "count": bench_counts["B"],
                "pct": round(bench_counts["B"] / total_bench * 100, 2),
            },
            "group_c": {
                "count": bench_counts["C"],
                "pct": round(bench_counts["C"] / total_bench * 100, 2),
            },
            "r2_disagreements_with_trocr_full_photo": (
                prod_disagreements_full
                if test_table is not None
                else prod_disagreements_crop
            ),
            "r2_disagreements_with_trocr_s3_crop": prod_disagreements_crop,
            "human_review_status": "UNKNOWN_PENDING_HUMAN_REVIEW",
        },
        "overall_totals": {
            "group_a": {
                "count": clean_counts["A"] + q_counts["A"] + bench_counts["A"],
                "pct": round(
                    (clean_counts["A"] + q_counts["A"] + bench_counts["A"])
                    / total_all
                    * 100,
                    2,
                ),
            },
            "group_b": {
                "count": clean_counts["B"] + q_counts["B"] + bench_counts["B"],
                "pct": round(
                    (clean_counts["B"] + q_counts["B"] + bench_counts["B"])
                    / total_all
                    * 100,
                    2,
                ),
            },
            "group_c": {
                "count": clean_counts["C"] + q_counts["C"] + bench_counts["C"],
                "pct": round(
                    (clean_counts["C"] + q_counts["C"] + bench_counts["C"])
                    / total_all
                    * 100,
                    2,
                ),
            },
        },
        "qa_statistical_bounds": {
            "confidence_level": 0.95,
            "z_score": 1.959964,
            "target_residual_error_rate": 0.01,
            "wilson_group_a_sample_size": 381,
            "inter_annotator_cer_target": 0.005,
            "cohens_kappa_target": 0.90,
        },
    }

    # Save summary
    target_summary.parent.mkdir(parents=True, exist_ok=True)
    with open(target_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Optional raw records save
    if output_records_path:
        out_rec_p = Path(output_records_path)
        out_rec_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_rec_p, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in records], f, indent=2)

    logger.info(
        "Triage completed: %d total instances evaluated. Summary saved to %s",
        total_all,
        target_summary,
    )
    return records, summary


def generate_label_studio_tasks(
    triage_records: Sequence[TriageRecord],
    output_path: str | Path | None = None,
    group_a_sample_size: int = 381,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """
    Generate pre-annotated Label Studio import JSON tasks ordered by risk:
    - Batch 0: 322 frozen-test benchmark images as GOLD test set.
    - Batch 1: Group B clean pool instances (disagreements/recoverable).
    - Batch 2: Statistically sized random sample of Group A clean pool instances (n=381).
    """
    batch_0_records = [r for r in triage_records if r.is_frozen_test]
    batch_1_records = [
        r
        for r in triage_records
        if not r.is_frozen_test and not r.is_quarantined and r.triage_group == "B"
    ]
    pool_group_a = [
        r
        for r in triage_records
        if not r.is_frozen_test and not r.is_quarantined and r.triage_group == "A"
    ]

    # Deterministic sampling for Batch 2
    rng = random.Random(seed)
    n_sample = min(group_a_sample_size, len(pool_group_a))
    batch_2_records = sorted(
        rng.sample(pool_group_a, n_sample),
        key=lambda r: r.instance_id,
    )

    tasks: list[dict[str, Any]] = []

    def make_task(
        rec: TriageRecord,
        batch_name: str,
        priority: int,
        crop_subfolder: str,
    ) -> dict[str, Any]:
        # Suggestion policy: consensus if equal, or prod_backend if valid, else cct_xs
        suggestion = rec.reading_trocr
        if rec.reading_prod_backend and is_civilian_car_one_line(
            rec.reading_prod_backend
        ):
            suggestion = rec.reading_prod_backend
        elif rec.reading_cct_xs and is_civilian_car_one_line(rec.reading_cct_xs):
            suggestion = rec.reading_cct_xs

        return {
            "data": {
                "image": f"/data/local-files/?d={crop_subfolder}/{rec.crop_filename}",
                "instance_id": rec.instance_id,
                "reading_trocr": rec.reading_trocr,
                "reading_prod_backend": rec.reading_prod_backend,
                "reading_cct_xs": rec.reading_cct_xs,
                "syntax_verdict": rec.syntax_verdict,
                "triage_group": rec.triage_group,
                "batch_name": batch_name,
                "batch_priority": priority,
                "group_id": rec.group_id,
                "crop_sha256": rec.crop_sha256,
                "photo_sha256": rec.photo_sha256,
                "source_split": rec.source_split,
            },
            "predictions": [
                {
                    "model_version": "three_way_consensus",
                    "result": [
                        {
                            "from_name": "plate_text",
                            "to_name": "image",
                            "type": "textarea",
                            "value": {"text": [suggestion]},
                        },
                        {
                            "from_name": "plate_format",
                            "to_name": "image",
                            "type": "choices",
                            "value": {"choices": ["one_line"]},
                        },
                        {
                            "from_name": "plate_type",
                            "to_name": "image",
                            "type": "choices",
                            "value": {"choices": ["white"]},
                        },
                        {
                            "from_name": "plate_quality",
                            "to_name": "image",
                            "type": "choices",
                            "value": {"choices": ["readable"]},
                        },
                    ],
                }
            ],
        }

    # Batch 0: Frozen test
    for r in batch_0_records:
        tasks.append(make_task(r, "Batch 0 (GOLD Frozen Test)", 0, "crops_322"))

    # Batch 1: Group B disputes
    for r in batch_1_records:
        tasks.append(make_task(r, "Batch 1 (Group B Disagreements)", 1, "crops"))

    # Batch 2: Group A sample
    for r in batch_2_records:
        tasks.append(make_task(r, "Batch 2 (Group A Statistical Sample)", 2, "crops"))

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)
        logger.info(
            "Generated %d pre-annotated tasks (B0=%d, B1=%d, B2=%d) to %s",
            len(tasks),
            len(batch_0_records),
            len(batch_1_records),
            len(batch_2_records),
            out_p,
        )

    return tasks


def convert_label_studio_export(
    export_data_or_path: str | Path | list[dict[str, Any]],
    output_manifest_path: str | Path | None = None,
    default_split: str = "train",
    provenance: str = "sonnetechnology",
    license_id: str = "CC-BY-4.0",
    filter_unreadable: bool = True,
) -> list[ManifestItem]:
    """
    Convert Label Studio exported annotation JSON into plate_training ManifestItem list.

    Extracts:
    - plate_text from TextArea annotation
    - quality from plate_quality Choices
    - image_path, sha256, group_id from task data
    - validates items against ManifestItem dataclass integrity rules
    """
    if isinstance(export_data_or_path, (str, Path)):
        with open(export_data_or_path, encoding="utf-8") as f:
            raw_tasks = json.load(f)
    else:
        raw_tasks = list(export_data_or_path)

    items: list[ManifestItem] = []

    for task in raw_tasks:
        annotations = task.get("annotations", [])
        if not annotations:
            # Skip unannotated task
            continue

        latest_annotation = annotations[-1]
        results = latest_annotation.get("result", [])

        plate_text_raw = ""
        quality = "readable"

        for res in results:
            from_name = res.get("from_name")
            val = res.get("value", {})
            if from_name == "plate_text":
                texts = val.get("text", [])
                if texts:
                    plate_text_raw = texts[0]
            elif from_name == "plate_quality":
                choices = val.get("choices", [])
                if choices:
                    quality = str(choices[0])

        normalized_plate = normalize_plate(plate_text_raw)
        if not normalized_plate:
            continue

        if filter_unreadable and quality == "unreadable":
            continue

        data = task.get("data", {})
        raw_img_path = data.get("image", "")
        # Extract relative image path from URL or parameter
        if "?d=" in raw_img_path:
            image_path = raw_img_path.split("?d=")[-1]
        else:
            image_path = (
                raw_img_path or f"crops/{data.get('instance_id', 'unknown')}.png"
            )

        sha256_hash = data.get("crop_sha256") or data.get("sha256")
        if not sha256_hash or len(sha256_hash) != 64:
            # Fallback placeholder 64-char sha if missing from synthetic task
            sha256_hash = hashlib.sha256(normalized_plate.encode("utf-8")).hexdigest()

        assigned_split = data.get("source_split", default_split)
        if assigned_split not in ("train", "val", "frozen-test"):
            assigned_split = default_split

        group_id = data.get("group_id") or f"grp_{sha256_hash[:16]}"

        item = ManifestItem(
            image_path=str(image_path),
            sha256=str(sha256_hash).lower(),
            plate_text=normalized_plate,
            split=str(assigned_split),
            provenance=str(data.get("provenance", provenance)),
            license=str(data.get("license", license_id)),
            plate_region="VN",
            quality=quality,
            group_id=str(group_id),
        )
        items.append(item)

    if output_manifest_path:
        out_p = Path(output_manifest_path)
        save_manifest(items, out_p)
        logger.info("Saved %d converted manifest items to %s", len(items), out_p)

    return items
