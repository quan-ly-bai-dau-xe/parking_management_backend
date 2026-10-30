"""Unit tests for 3-way label quality triage, Label Studio kit, and export converter."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from plate_training.manifest import validate_manifest
from plate_training.triage import (
    TriageRecord,
    convert_label_studio_export,
    generate_label_studio_tasks,
    is_civilian_car_one_line,
    triage_readings,
)


@pytest.mark.unit
def test_is_civilian_car_one_line_valid_samples() -> None:
    """Verify that compliant Vietnamese civilian car plates return True."""
    # Standard 5-digit civilian car plates (2 digits + 1 series letter + 5 digits)
    assert is_civilian_car_one_line("51K99214") is True
    assert is_civilian_car_one_line("30H12345") is True
    assert is_civilian_car_one_line("29A56789") is True
    assert is_civilian_car_one_line("60B98765") is True

    # Legacy 4-digit civilian car plates (2 digits + 1 series letter + 4 digits)
    assert is_civilian_car_one_line("99P5688") is True
    assert is_civilian_car_one_line("51A1234") is True


@pytest.mark.unit
def test_is_civilian_car_one_line_out_of_scope_or_invalid() -> None:
    """Verify that out-of-scope, military, agency, and invalid formats return False."""
    # Agency 80 (Traffic Police / Ministry agency) excluded from civilian training
    assert is_civilian_car_one_line("80A12345") is False
    assert is_civilian_car_one_line("80B99999") is False

    # Dual-letter special car series
    assert is_civilian_car_one_line("99LD04411") is False
    assert is_civilian_car_one_line("29NG12345") is False
    assert is_civilian_car_one_line("51QT00123") is False

    # Military plates (2 letters + 4-5 digits)
    assert is_civilian_car_one_line("TM1234") is False
    assert is_civilian_car_one_line("QA5678") is False

    # Reserved never-issued province codes
    assert is_civilian_car_one_line("13A12345") is False
    assert is_civilian_car_one_line("42A12345") is False
    assert is_civilian_car_one_line("87A12345") is False

    # Invalid series letters (I, J, O, Q, R, W strictly forbidden for civilian cars)
    assert is_civilian_car_one_line("51I12345") is False
    assert is_civilian_car_one_line("30O12345") is False
    assert is_civilian_car_one_line("29W12345") is False

    # Invalid lengths or formats (e.g. extra digit error)
    assert is_civilian_car_one_line("99F222611") is False
    assert is_civilian_car_one_line("51A123") is False
    assert is_civilian_car_one_line("") is False
    assert is_civilian_car_one_line("GARBAGE") is False


@pytest.mark.unit
def test_triage_readings_group_a_consensus() -> None:
    """Group A requires all three readings equal and valid civilian car one-line syntax."""
    # Full 3-way consensus on valid civilian plate
    grp, verdict, msg = triage_readings("51K99214", "51K99214", "51K99214")
    assert grp == "A"
    assert verdict == "VALID"
    assert "civilian" in msg.lower()

    # Legacy 4-digit consensus
    grp4, verdict4, _ = triage_readings("99P5688", "99P5688", "99P5688")
    assert grp4 == "A"
    assert verdict4 == "VALID"


@pytest.mark.unit
def test_triage_readings_group_b_disagreements() -> None:
    """Group B captures any disagreement where at least one reading is valid/recoverable."""
    # Synthetic extra digit error: TrOCR produced extra digit, while Prod and CCT-XS read correctly
    grp_dirty, verdict_dirty, msg_dirty = triage_readings(
        r1="99F222611",  # 9 chars (extra digit error)
        r2="99F22261",  # 8 chars (valid)
        r3="99F22261",  # 8 chars (valid)
    )
    assert grp_dirty == "B"
    assert verdict_dirty == "DISAGREEMENT"
    assert "recoverable" in msg_dirty.lower()

    # Single character disagreement between recognizers
    grp_sub, verdict_sub, _ = triage_readings(
        r1="30E12345",
        r2="30E12346",
        r3="30E12345",
    )
    assert grp_sub == "B"
    assert verdict_sub == "DISAGREEMENT"

    # All three distinct but plausible
    grp_diff, verdict_diff, _ = triage_readings(
        r1="29A11111",
        r2="29A11112",
        r3="29A11113",
    )
    assert grp_diff == "B"
    assert verdict_diff == "DISAGREEMENT"


@pytest.mark.unit
def test_triage_readings_group_c_out_of_scope() -> None:
    """Group C excludes military, special series, central agency 80, and garbage."""
    # Agency 80 consensus
    grp_80, verdict_80, _ = triage_readings("80A12345", "80A12345", "80A12345")
    assert grp_80 == "C"

    # Special series LD consensus
    grp_ld, verdict_ld, _ = triage_readings("99LD04411", "99LD04411", "99LD04411")
    assert grp_ld == "C"

    # Military plate consensus
    grp_mil, verdict_mil, _ = triage_readings("TM1234", "TM1234", "TM1234")
    assert grp_mil == "C"

    # All invalid garbage readings
    grp_bad, verdict_bad, _ = triage_readings("XYZ99", "INVALID", "EMPTY")
    assert grp_bad == "C"


@pytest.mark.unit
def test_triage_record_serialization_roundtrip() -> None:
    """Verify TriageRecord serialization and deserialization integrity."""
    rec = TriageRecord(
        instance_id="inst_train_001_0",
        source_split="train",
        reading_trocr="51K99214",
        reading_prod_backend="51K99214",
        reading_cct_xs="51K99214",
        syntax_verdict="VALID",
        syntax_message="Compliant civilian car plate.",
        triage_group="A",
        crop_filename="inst_train_001_0.png",
        crop_sha256="a" * 64,
        photo_sha256="b" * 64,
        group_id="grp_51k99214",
        is_quarantined=False,
        is_frozen_test=False,
    )
    d = rec.to_dict()
    assert d["instance_id"] == "inst_train_001_0"
    assert d["triage_group"] == "A"

    rebuilt = TriageRecord.from_dict(d)
    assert rebuilt == rec


@pytest.mark.unit
def test_generate_label_studio_tasks_structure(tmp_path: Path) -> None:
    """Verify that Label Studio task generator correctly partitions batches and structures schema."""
    records: list[TriageRecord] = []

    # 1. Five frozen test records (Batch 0)
    for i in range(5):
        records.append(
            TriageRecord(
                instance_id=f"frozen_{i:03d}",
                source_split="frozen-test",
                reading_trocr="30A12345",
                reading_prod_backend="30A12345",
                reading_cct_xs="30A12345",
                syntax_verdict="VALID",
                syntax_message="OK",
                triage_group="A",
                crop_filename=f"crop_{i:03d}.png",
                crop_sha256="c" * 64,
                photo_sha256="d" * 64,
                group_id=f"grp_frozen_{i}",
                is_frozen_test=True,
            )
        )

    # 2. Four Group B pool records (Batch 1)
    for i in range(4):
        records.append(
            TriageRecord(
                instance_id=f"pool_b_{i:03d}",
                source_split="train",
                reading_trocr="51A12345",
                reading_prod_backend="51A12346",
                reading_cct_xs="51A12345",
                syntax_verdict="DISAGREEMENT",
                syntax_message="Disagreement",
                triage_group="B",
                crop_filename=f"pool_b_{i:03d}.png",
                crop_sha256="e" * 64,
                photo_sha256="f" * 64,
                group_id=f"grp_pool_b_{i}",
                is_frozen_test=False,
            )
        )

    # 3. Ten Group A pool records (Batch 2 candidate pool)
    for i in range(10):
        records.append(
            TriageRecord(
                instance_id=f"pool_a_{i:03d}",
                source_split="train",
                reading_trocr="29A99999",
                reading_prod_backend="29A99999",
                reading_cct_xs="29A99999",
                syntax_verdict="VALID",
                syntax_message="OK",
                triage_group="A",
                crop_filename=f"pool_a_{i:03d}.png",
                crop_sha256="0" * 64,
                photo_sha256="1" * 64,
                group_id=f"grp_pool_a_{i}",
                is_frozen_test=False,
            )
        )

    output_file = tmp_path / "test_tasks.json"
    tasks = generate_label_studio_tasks(
        records,
        output_path=output_file,
        group_a_sample_size=3,
        seed=42,
    )

    # Expected: 5 (B0) + 4 (B1) + 3 (B2) = 12 tasks
    assert len(tasks) == 12
    assert output_file.is_file()

    # Check batch partitions
    b0_tasks = [t for t in tasks if t["data"]["batch_priority"] == 0]
    b1_tasks = [t for t in tasks if t["data"]["batch_priority"] == 1]
    b2_tasks = [t for t in tasks if t["data"]["batch_priority"] == 2]

    assert len(b0_tasks) == 5
    assert len(b1_tasks) == 4
    assert len(b2_tasks) == 3

    # Check Label Studio prediction schema format
    sample_task = tasks[0]
    assert "data" in sample_task
    assert "predictions" in sample_task
    pred = sample_task["predictions"][0]
    assert pred["model_version"] == "three_way_consensus"
    result_names = {r["from_name"] for r in pred["result"]}
    assert "plate_text" in result_names
    assert "plate_format" in result_names
    assert "plate_type" in result_names
    assert "plate_quality" in result_names


@pytest.mark.unit
def test_convert_label_studio_export_to_manifest(tmp_path: Path) -> None:
    """Verify Label Studio export converter generates valid ManifestItem objects passing JSON schema."""
    sample_export = [
        {
            "id": 1,
            "data": {
                "image": "/data/local-files/?d=crops/inst_train_001_0.png",
                "instance_id": "inst_train_001_0",
                "crop_sha256": "a" * 64,
                "group_id": "grp_test_session1",
                "source_split": "train",
            },
            "annotations": [
                {
                    "id": 101,
                    "result": [
                        {
                            "from_name": "plate_text",
                            "to_name": "image",
                            "type": "textarea",
                            "value": {
                                "text": ["51-K 992.14"]
                            },  # Dirty formatting to test normalization
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
        },
        {
            "id": 2,
            "data": {
                "image": "/data/local-files/?d=crops/inst_train_002_0.png",
                "instance_id": "inst_train_002_0",
                "crop_sha256": "b" * 64,
                "group_id": "grp_test_session2",
                "source_split": "val",
            },
            "annotations": [
                {
                    "id": 102,
                    "result": [
                        {
                            "from_name": "plate_text",
                            "to_name": "image",
                            "type": "textarea",
                            "value": {"text": ["30H12345"]},
                        },
                        {
                            "from_name": "plate_quality",
                            "to_name": "image",
                            "type": "choices",
                            "value": {"choices": ["unreadable"]},  # Unreadable sample
                        },
                    ],
                }
            ],
        },
    ]

    manifest_file = tmp_path / "manifest.json"
    items = convert_label_studio_export(
        sample_export,
        output_manifest_path=manifest_file,
        default_split="train",
        filter_unreadable=True,
    )

    # Sample 2 is marked unreadable and should be filtered out
    assert len(items) == 1
    item = items[0]
    assert item.plate_text == "51K99214"  # Punctuation stripped and normalized
    assert item.quality == "readable"
    assert item.group_id == "grp_test_session1"
    assert item.split == "train"

    # Validate against JSON schema Draft 2020-12
    with open(manifest_file, encoding="utf-8") as f:
        manifest_data = json.load(f)
    validate_manifest(manifest_data)


@pytest.mark.unit
def test_wilson_sample_size_derivation_arithmetic() -> None:
    """Verify that the analytical Wilson score interval upper bound yields exactly n >= 381."""
    # Target confidence 95% -> alpha = 0.05 -> two-tailed z = 1.959964
    z = 1.959964
    z_sq = z**2
    assert math.isclose(z_sq, 3.841459, rel_tol=1e-5)

    p_target = 0.01

    # Analytic formula for 0 observed errors:
    # p_U = z^2 / (n + z^2) < p_target <=> n > z^2 * (1 / p_target - 1)
    factor = (1.0 / p_target) - 1.0
    assert math.isclose(factor, 99.0)

    n_continuous = z_sq * factor
    assert math.isclose(n_continuous, 380.3044, rel_tol=1e-4)

    n_required = math.ceil(n_continuous)
    assert n_required == 381

    # Verify boundary behavior:
    # At n = 380: p_U should EXCEED or equal 0.01
    p_u_380 = z_sq / (380 + z_sq)
    assert p_u_380 >= p_target

    # At n = 381: p_U should be STRICTLY BELOW 0.01
    p_u_381 = z_sq / (381 + z_sq)
    assert p_u_381 < p_target
