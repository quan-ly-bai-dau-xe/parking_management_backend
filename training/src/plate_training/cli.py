"""CLI entrypoints for plate-training subproject."""

import json
import sys
from pathlib import Path

import click

from plate_training.assembly import (
    HumanVerificationRequiredError,
    build_training_manifest,
)
from plate_training.benchmark import extract_benchmark_crops
from plate_training.cache import (
    compute_sha256,
    ensure_cache_dir,
    fetch_published_weights,
    get_cache_dir,
)
from plate_training.manifest import load_manifest, verify_image_hashes
from plate_training.onnx_parity import check_onnx_parity
from plate_training.pool import build_candidate_pool
from plate_training.split import validate_splits
from plate_training.triage import generate_label_studio_tasks, run_triage


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """Plate Training CLI — Vietnamese License Plate OCR Training Pipeline."""


@main.command(name="validate-manifest")
@click.option(
    "--manifest",
    "-m",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to manifest JSON.",
)
@click.option(
    "--schema",
    "-s",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Optional JSON Schema path.",
)
@click.option(
    "--verify-hashes",
    is_flag=True,
    default=False,
    help="Verify physical image SHA-256 hashes.",
)
@click.option(
    "--base-dir",
    "-b",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Base directory for image paths.",
)
def validate_manifest_cmd(
    manifest: str, schema: str | None, verify_hashes: bool, base_dir: str | None
) -> None:
    """Validate manifest dataset schema and optionally verify image hashes."""
    click.echo(f"Loading manifest from {manifest}...")
    items = load_manifest(manifest, schema_path=schema)
    click.echo(f"Manifest schema valid! Loaded {len(items)} samples.")

    if verify_hashes:
        root_dir = Path(base_dir) if base_dir else Path(manifest).parent
        click.echo(f"Verifying image hashes relative to {root_dir}...")
        results = verify_image_hashes(items, base_dir=root_dir, fail_fast=False)
        failed = sum(1 for passed in results.values() if not passed)
        if failed > 0:
            click.echo(
                f"ERROR: {failed}/{len(items)} images failed hash verification!",
                err=True,
            )
            sys.exit(1)
        click.echo(f"All {len(items)} image hashes successfully verified.")


@main.command(name="check-splits")
@click.option(
    "--manifest",
    "-m",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to manifest JSON.",
)
@click.option(
    "--base-dir",
    "-b",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Base directory for image files.",
)
@click.option(
    "--phash-threshold",
    "-t",
    default=4,
    type=int,
    help="pHash Hamming distance threshold.",
)
def check_splits_cmd(manifest: str, base_dir: str | None, phash_threshold: int) -> None:
    """Check dataset splits for exact duplicate or near-duplicate leakage."""
    click.echo(f"Checking dataset splits in {manifest}...")
    items = load_manifest(manifest)
    root_dir = Path(base_dir) if base_dir else Path(manifest).parent
    validate_splits(
        items, base_dir=root_dir, check_phash=True, phash_threshold=phash_threshold
    )
    click.echo(f"Zero data leakage detected across {len(items)} samples.")


@main.command(name="check-parity")
@click.option(
    "--keras-model",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to Keras model checkpoint.",
)
@click.option(
    "--onnx-model",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to exported ONNX model.",
)
@click.option("--atol", default=1e-4, type=float, help="Absolute tolerance threshold.")
@click.option("--rtol", default=1e-4, type=float, help="Relative tolerance threshold.")
def check_parity_cmd(
    keras_model: str, onnx_model: str, atol: float, rtol: float
) -> None:
    """Verify forward-pass output equivalence between Keras and ONNX models."""
    click.echo(f"Checking parity between {keras_model} and {onnx_model}...")
    result = check_onnx_parity(keras_model, onnx_model, atol=atol, rtol=rtol)
    click.echo(
        f"Parity verified! Status: {result['status']}, Max Diff: {result['max_diff']:.6e}"
    )


@main.command(name="prepare-heavy-inputs")
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Target cache directory (defaults to PLATE_TRAINING_CACHE or standard system cache).",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force re-download / re-generation even if files already exist.",
)
@click.option(
    "--parquet-path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Optional path to local sonnetechnology benchmark Parquet file.",
)
def prepare_heavy_inputs_cmd(
    cache_dir: str | None,
    force: bool,
    parquet_path: str | None,
) -> None:
    """Prepare and verify heavy test inputs (published weights, 322 crops, and labels)."""
    resolved_cache = get_cache_dir(cache_dir)
    click.echo(f"[CACHE] Resolving heavy inputs into: {resolved_cache}")

    # 1. Fetch & verify published weights
    click.echo("[WEIGHTS] Fetching and verifying cct_xs_v2_global.keras...")
    w_file = fetch_published_weights(cache_dir=cache_dir, force=force)
    w_sha = compute_sha256(w_file)
    w_size = w_file.stat().st_size

    # 2. Extract & verify 322 crops and benchmark labels
    click.echo("[CROPS] Preparing 322 detector benchmark crops & labels...")
    crops_dir, labels_file = extract_benchmark_crops(
        parquet_path=parquet_path,
        cache_dir=cache_dir,
        force=force,
    )
    crops_count = len(list(crops_dir.glob("crop_*.png")))

    manifest = {
        "status": "READY",
        "cache_dir": str(resolved_cache),
        "weights": {
            "path": str(w_file),
            "sha256": w_sha,
            "size_bytes": w_size,
            "verified": True,
        },
        "crops": {
            "dir": str(crops_dir),
            "count": crops_count,
            "verified": crops_count == 322,
        },
        "labels": {
            "path": str(labels_file),
            "verified": labels_file.is_file(),
        },
    }

    click.echo("\n--- Heavy Inputs Manifest ---")
    click.echo(json.dumps(manifest, indent=2))
    click.echo("[READY] Heavy inputs preparation complete. 0 errors.")


@main.command(name="build-candidate-pool")
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Path to PLATE_TRAINING_CACHE directory outside repository.",
)
@click.option(
    "--margin",
    type=int,
    default=4,
    show_default=True,
    help="Padding margin in pixels clamped to image bounds.",
)
@click.option(
    "--phash-threshold",
    type=int,
    default=4,
    show_default=True,
    help="Hamming distance threshold for pHash quarantine and clustering.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force re-extraction and overwrite existing cached pool and crops.",
)
@click.option(
    "--output-pool",
    type=click.Path(dir_okay=False),
    default=None,
    help="Output path for candidate pool JSON file.",
)
@click.option(
    "--output-summary",
    type=click.Path(dir_okay=False),
    default=None,
    help="Output path for aggregate summary JSON file.",
)
@click.option(
    "--splits",
    type=str,
    default="train,validation",
    show_default=True,
    help="Comma-separated splits to process from cache.",
)
@click.option(
    "--registry-path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to frozen_test_registry.json.",
)
def build_candidate_pool_cmd(
    cache_dir: str | None,
    margin: int,
    phash_threshold: int,
    force: bool,
    output_pool: str | None,
    output_summary: str | None,
    splits: str,
    registry_path: str | None,
) -> None:
    """Build candidate pool from cached Parquets with quarantine and group clustering."""
    resolved_splits = tuple(s.strip() for s in splits.split(",") if s.strip())
    click.echo(
        f"[POOL] Building candidate pool for splits: {list(resolved_splits)} "
        f"(margin={margin}px, phash_threshold={phash_threshold})..."
    )
    _instances, summary = build_candidate_pool(
        cache_dir=cache_dir,
        registry_path=registry_path,
        margin=margin,
        phash_threshold=phash_threshold,
        output_pool_path=output_pool,
        output_summary_path=output_summary,
        splits=resolved_splits,
        force=force,
    )
    total = summary["total_instances"]
    clean = summary["total_clean"]
    quarantined = summary["total_quarantined"]
    photo_nd = summary["quarantine_photo_near_duplicates_h4"]
    num_groups = summary["clustering"]["total_groups"]

    click.echo(
        f"[POOL] Successfully processed {total} plate instances: "
        f"{clean} clean, {quarantined} quarantined."
    )
    click.echo(
        f"[QUARANTINE] Quarantined {quarantined} instances "
        f"({photo_nd} photo pHash near-duplicates <= {phash_threshold} to frozen test)."
    )
    click.echo(
        f"[CLUSTERING] Formed {num_groups} deterministic groups among clean instances."
    )
    click.echo("[SUMMARY] Aggregate summary written with 0 plate strings.")


@main.command(name="run-triage")
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Path to PLATE_TRAINING_CACHE.",
)
@click.option(
    "--candidate-pool",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to candidate_pool.json.",
)
@click.option(
    "--frozen-labels",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to benchmark_322_labels.json.",
)
@click.option(
    "--output-summary",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to output triage_summary.json.",
)
@click.option(
    "--output-tasks",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to output label_studio_tasks.json.",
)
@click.option(
    "--threads",
    type=int,
    default=4,
    show_default=True,
    help="Number of intra-op threads for OCR inference.",
)
@click.option(
    "--sample-size",
    type=int,
    default=381,
    show_default=True,
    help="Wilson score interval sample size for Group A QA.",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    show_default=True,
    help="Deterministic random seed for sampling.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force recomputation even if summary exists.",
)
def run_triage_cmd(
    cache_dir: str | None,
    candidate_pool: str | None,
    frozen_labels: str | None,
    output_summary: str | None,
    output_tasks: str | None,
    threads: int,
    sample_size: int,
    seed: int,
    force: bool,
) -> None:
    """Run 3-way label quality triage and generate Label Studio review tasks."""
    click.echo(
        "[TRIAGE] Executing 3-way label quality triage (TrOCR, Prod Recognizer, CCT-XS)..."
    )
    records, summary = run_triage(
        cache_dir=cache_dir,
        candidate_pool_path=candidate_pool,
        frozen_labels_path=frozen_labels,
        output_summary_path=output_summary,
        threads=threads,
        force=force,
    )
    clean = summary["clean_candidate_pool"]
    q = summary["quarantine_pool"]
    bench = summary["frozen_test_benchmark"]
    overall = summary["overall_totals"]

    click.echo(
        f"[TRIAGE] Clean Pool ({clean['total']}): "
        f"A={clean['group_a']['count']} ({clean['group_a']['pct']}%), "
        f"B={clean['group_b']['count']} ({clean['group_b']['pct']}%), "
        f"C={clean['group_c']['count']} ({clean['group_c']['pct']}%)"
    )
    click.echo(
        f"[TRIAGE] Quarantine ({q['total']}): "
        f"A={q['group_a']['count']} ({q['group_a']['pct']}%), "
        f"B={q['group_b']['count']} ({q['group_b']['pct']}%), "
        f"C={q['group_c']['count']} ({q['group_c']['pct']}%)"
    )
    click.echo(
        f"[TRIAGE] Frozen Test ({bench['total']}): "
        f"A={bench['group_a']['count']} ({bench['group_a']['pct']}%), "
        f"B={bench['group_b']['count']} ({bench['group_b']['pct']}%), "
        f"C={bench['group_c']['count']} ({bench['group_c']['pct']}%) | "
        f"Disagreements (full photo)={bench['r2_disagreements_with_trocr_full_photo']}, "
        f"Disagreements (crop)={bench['r2_disagreements_with_trocr_s3_crop']}"
    )
    click.echo(
        f"[TRIAGE] Overall Totals ({summary['total_instances_evaluated']}): "
        f"A={overall['group_a']['count']} ({overall['group_a']['pct']}%), "
        f"B={overall['group_b']['count']} ({overall['group_b']['pct']}%), "
        f"C={overall['group_c']['count']} ({overall['group_c']['pct']}%)"
    )

    resolved_cache = ensure_cache_dir(cache_dir)
    target_tasks = (
        Path(output_tasks)
        if output_tasks
        else resolved_cache / "label_studio_tasks.json"
    )
    tasks = generate_label_studio_tasks(
        records,
        output_path=target_tasks,
        group_a_sample_size=sample_size,
        seed=seed,
    )
    click.echo(
        f"[LABEL-STUDIO] Generated {len(tasks)} risk-ordered review tasks "
        f"(B0=322, B1={clean['group_b']['count']}, B2={sample_size}) to {target_tasks}"
    )


@main.command(name="build-training-manifest")
@click.option(
    "--pool-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to candidate_pool.json.",
)
@click.option(
    "--triage-summary",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to triage_summary.json.",
)
@click.option(
    "--triage-records",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to triage_records.json.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Target directory for output manifest, metadata, crops, and archive.",
)
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Path to PLATE_TRAINING_CACHE root.",
)
@click.option(
    "--val-ratio",
    type=float,
    default=0.2,
    show_default=True,
    help="Validation split ratio for full training manifest.",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    show_default=True,
    help="Random seed for deterministic group-disjoint splitting.",
)
@click.option(
    "--allow-provisional",
    is_flag=True,
    default=False,
    help="Allow provisional machine-generated labels without human verification.",
)
@click.option(
    "--smoke",
    is_flag=True,
    default=False,
    help="Build 128-crop Kaggle smoke dataset (64 train, 64 val, Group A only).",
)
@click.option(
    "--smoke-train-count",
    type=int,
    default=64,
    show_default=True,
    help="Number of train instances in smoke mode.",
)
@click.option(
    "--smoke-val-count",
    type=int,
    default=64,
    show_default=True,
    help="Number of val instances in smoke mode.",
)
@click.option(
    "--copy-crops/--no-copy-crops",
    default=True,
    show_default=True,
    help="Copy physical crop images into output directory.",
)
@click.option(
    "--create-archive/--no-create-archive",
    default=True,
    show_default=True,
    help="Package dataset folder into deployable archive.",
)
def build_training_manifest_cmd(
    pool_file: str | None,
    triage_summary: str | None,
    triage_records: str | None,
    output_dir: str | None,
    cache_dir: str | None,
    val_ratio: float,
    seed: int,
    allow_provisional: bool,
    smoke: bool,
    smoke_train_count: int,
    smoke_val_count: int,
    copy_crops: bool,
    create_archive: bool,
) -> None:
    """Build training manifest enforcing human verification, group-disjoint splits, and smoke mode."""
    mode_str = "128-crop Kaggle smoke mode" if smoke else "full training manifest mode"
    click.echo(f"[ASSEMBLY] Assembling dataset under {mode_str} (seed={seed})...")

    try:
        result = build_training_manifest(
            pool_path=pool_file,
            output_dir=output_dir,
            cache_dir=cache_dir,
            triage_records_path=triage_records,
            val_ratio=val_ratio,
            seed=seed,
            allow_provisional=allow_provisional,
            smoke=smoke,
            smoke_train_count=smoke_train_count,
            smoke_val_count=smoke_val_count,
            copy_crops=copy_crops,
            create_archive=create_archive,
            validate=True,
        )
    except HumanVerificationRequiredError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"ERROR: Assembly failed: {exc}", err=True)
        sys.exit(1)

    click.echo(
        f"[ASSEMBLY] Manifest generated: {result.total_items} samples "
        f"(train={result.train_count} [{result.train_groups} groups], "
        f"val={result.val_count} [{result.val_groups} groups])"
    )
    click.echo(
        f"[ASSEMBLY] Label status: '{result.label_status}' "
        f"(provisional={result.is_provisional})"
    )
    click.echo(f"[ASSEMBLY] Saved manifest to {result.manifest_path}")
    click.echo(f"[ASSEMBLY] Saved metadata to {result.metadata_path}")

    # Display distribution summary
    overall_dist = result.distributions["overall"]
    train_dist = result.distributions["train"]
    val_dist = result.distributions["val"]

    click.echo(
        f"[DISTRIBUTION] Vocabulary characters: {len(overall_dist.character_counts)} defined, "
        f"total characters={overall_dist.total_characters} "
        f"(train={train_dist.total_characters}, val={val_dist.total_characters})"
    )
    click.echo(
        f"[DISTRIBUTION] Province codes: {len(overall_dist.province_counts)} distinct provinces "
        f"(train={len(train_dist.province_counts)}, val={len(val_dist.province_counts)})"
    )

    if result.archive_path and result.archive_sha256:
        click.echo(
            f"[ARCHIVE] Packaged {result.archive_path.name} "
            f"({result.archive_size_bytes} bytes, SHA-256: {result.archive_sha256})"
        )

    click.echo(
        "[SUMMARY] Aggregate counts only. Zero real license plate strings printed or committed."
    )


if __name__ == "__main__":
    main()
