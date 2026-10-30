import contextlib
import os

# Default to PyTorch backend for Keras 3 across the training pipeline
os.environ.setdefault("KERAS_BACKEND", "torch")

from plate_training.assembly import (
    CIVILIAN_CAR_VOCABULARY,
    AssemblyDistribution,
    AssemblyError,
    AssemblyResult,
    HumanVerificationRequiredError,
    build_training_manifest,
    compute_distribution,
    select_smoke_groups,
)
from plate_training.checkpoint import find_latest_checkpoint
from plate_training.config import TrainConfig
from plate_training.dataset import (
    PlateDataset,
    build_dataset,
    decode_plate_prediction,
    encode_plate_label,
    preprocess_plate_image,
    read_and_preprocess_image,
)
from plate_training.manifest import (
    ManifestItem,
    compute_file_sha256,
    load_manifest,
    save_manifest,
    validate_manifest,
    verify_image_hashes,
)
from plate_training.metrics import (
    EvaluationReport,
    compute_auto_metrics,
    compute_cer,
    compute_character_accuracy,
    compute_exact_match,
    evaluate_predictions,
    levenshtein_distance,
)
from plate_training.normalization import normalize_plate
from plate_training.onnx_parity import ParityCheckError, check_onnx_parity
from plate_training.pool import (
    CandidateInstance,
    build_candidate_pool,
    clamp_bbox,
    cluster_instances,
    evaluate_quarantine_status,
    extract_normalized_crop,
)
from plate_training.split import (
    DataLeakageError,
    check_registry_leakage,
    compute_phash,
    detect_exact_duplicates,
    detect_group_leakage,
    detect_near_duplicates,
    get_default_registry_path,
    hamming_distance,
    load_frozen_test_registry,
    validate_splits,
)
from plate_training.triage import (
    TriageRecord,
    convert_label_studio_export,
    generate_label_studio_tasks,
    is_civilian_car_one_line,
    run_triage,
    triage_readings,
)

__version__ = "0.1.0"

__all__ = [
    "PlateDataset",
    "build_dataset",
    "encode_plate_label",
    "decode_plate_prediction",
    "preprocess_plate_image",
    "read_and_preprocess_image",
    "ManifestItem",
    "compute_file_sha256",
    "load_manifest",
    "save_manifest",
    "validate_manifest",
    "verify_image_hashes",
    "normalize_plate",
    "DataLeakageError",
    "compute_phash",
    "hamming_distance",
    "detect_exact_duplicates",
    "detect_near_duplicates",
    "detect_group_leakage",
    "check_registry_leakage",
    "load_frozen_test_registry",
    "get_default_registry_path",
    "validate_splits",
    "levenshtein_distance",
    "compute_exact_match",
    "compute_character_accuracy",
    "compute_cer",
    "compute_auto_metrics",
    "evaluate_predictions",
    "EvaluationReport",
    "check_onnx_parity",
    "ParityCheckError",
    "find_latest_checkpoint",
    "CandidateInstance",
    "build_candidate_pool",
    "clamp_bbox",
    "extract_normalized_crop",
    "evaluate_quarantine_status",
    "cluster_instances",
    "TriageRecord",
    "run_triage",
    "triage_readings",
    "is_civilian_car_one_line",
    "generate_label_studio_tasks",
    "convert_label_studio_export",
    "AssemblyDistribution",
    "AssemblyError",
    "AssemblyResult",
    "HumanVerificationRequiredError",
    "build_training_manifest",
    "compute_distribution",
    "select_smoke_groups",
    "CIVILIAN_CAR_VOCABULARY",
    "TrainConfig",
    "build_model",
    "load_aligned_model",
    "slice_plate_model",
    "verify_loaded_weights",
    "count_model_parameters",
    "inspect_model_topology",
]

with contextlib.suppress(ImportError):
    from plate_training.model import (
        build_model,
        count_model_parameters,
        inspect_model_topology,
        load_aligned_model,
        slice_plate_model,
        verify_loaded_weights,
    )
