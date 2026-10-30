# Plate Recognition Training Subproject (Vietnamese License Plates)

Isolated training, evaluation, and export pipeline for fine-tuning Compact Convolutional Transformer (CCT) license-plate recognition models for the parking management backend.

## Purpose & Scope

This subproject provides tooling for Vietnamese license-plate character recognition:

- **Pretrained Foundation**: This pipeline is strictly **NOT training from scratch**. It executes transfer learning and fine-tuning on the published `cct_xs_v2_global` Compact Convolutional Transformer recognizer from upstream `fast-plate-ocr`.
- **Target Operational Scope**: The initial fine-tuned model focuses exclusively on **civilian car plates, one line** (`^\d{2}[A-Z]\d{4,5}$`), in full alignment with the facility System Requirements Specification (SRS) and statutory definitions in `apps/parking/data/vn_plate_rules.py`.
- **Explicit Out-of-Scope Categories**: This model does NOT claim to recognize every Vietnamese vehicle plate. The following categories are explicitly **OUT OF SCOPE** for the first model release:
  - Military vehicle plates (2 uppercase letters + 4 or 5 digits, e.g., `QA1234`, `TC12345`).
  - Central government and agency plates (Province code `80`).
  - Diplomatic, foreign, joint-venture, and specialized series (`NG`, `QT`, `CV`, `NN`, `LD`, `DA`, `KT`, `CD`, `TD`).
  - Motorbike plates (2-line square format).
- **Statutory Review Policy Invariant**: All out-of-scope plate categories are deterministically routed to human operator inspection (`review_status = "NEEDS_REVIEW"`) by backend business rules (`apps/parking/services/review_policy.py`). The OCR model artifact produces raw character logits only and has zero authority over barrier opening.
- **Scientific Honesty & Extension Policy**: Recognition accuracy and detector coverage on out-of-scope plate types remain unmeasured, and detector localization behavior on them is designated as `UNVERIFIED`. Any future scope expansion requires lawful collection of real-world operational images under Decree 13/2023/ND-CP, which constitutes a separate Owner decision.
- Dataset manifest validation, SHA-256 verification, and strict train/val/frozen-test split leakage prevention.
- Model evaluation pipelines computing Exact Match %, Character Accuracy %, CER (Levenshtein), and Review Policy metrics (AUTO Coverage % and Wrong-in-AUTO %).
- ONNX export and numerical parity verification against Keras tensors with tolerance atol=1e-4, rtol=1e-4.
- Kaggle GPU notebook orchestration for remote fine-tuning without local GPU dependencies.

## Artifact Contract with Backend

The backend OCR service (`apps/parking/services/ocr.py`) consumes the exported ONNX model and configuration without requiring backend code changes.

### Contract Specifications

- **Model File**: `cct_xs_v2_global.onnx`
- **Config File**: `cct_xs_v2_global_plate_config.yaml`
- **Input Tensor**:
  - Name: Primary image input
  - Shape: Dynamic batch `[Batch, 64, 128, 3]`
  - Type: `uint8`
  - Color mode: RGB
- **Output Tensor**:
  - Name: `'plate'`
  - Shape: `[Batch, 10, 37]`
  - Type: `float32` probabilities / logits
- **Character Set**:
  - Alphabet: `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_` (37 characters)
  - Max plate slots: `10`
  - Pad character: `_` (index 36)
- **Deployment Location**:
  - Controlled by the `PARKING_OCR_MODELS_DIR` environment variable (defaults to `/app/models/ocr` in Docker).

## Quickstart Guide

### 1. Environment Setup

```bash
# Create an isolated virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Option A: Fast CPU-only CI gate (strictly 34 packages, hash-pinned)
pip install --require-hashes -r requirements-lock.txt

# Option B: Complete Kaggle GPU training stack (exact pinned packages)
pip install -r requirements-train.txt

# Install plate-training in editable mode
pip install -e . --no-deps
```

### 2. Code Quality & Static Checks

```bash
# Run Ruff linting
ruff check .

# Run Ruff formatting check
ruff format --check .

# Run Mypy static type checking
mypy .

# Run isolated test suite
pytest
```

### 3. Command Line Interface (CLI)

```bash
# Show CLI options
plate-training --help

# Validate manifest schema and image hashes
plate-training validate-manifest --manifest data/manifest.json --verify-hashes

# Check split leakage (exact SHA-256 duplicates and pHash near-duplicates)
plate-training check-splits --manifest data/manifest.json

# Check parity between Keras checkpoint and exported ONNX model
plate-training check-parity --keras-model model.keras --onnx-model model.onnx
```

## Directory Layout

```text
training/
├── README.md                  # Subproject documentation and artifact contract
├── pyproject.toml             # Package metadata, tool.ruff, tool.mypy, tool.pytest
├── requirements.txt           # General dependencies
├── requirements-train.txt     # Pinned full training dependencies for Kaggle GPU (exact == pins)
├── requirements-ci.txt        # Lightweight CI dependencies (zero PyTorch/CUDA, fast CPU gate)
├── requirements-lock.txt      # Hash-pinned lockfile covering requirements-ci.txt ONLY (strictly 34 packages, Python 3.14)
├── .gitignore                 # Excludes data images, weights, outputs, kaggle secrets
├── configs/                   # Model and training hyperparameter configurations
│   ├── plate_config_vn.yaml   # Vietnamese PlateConfig (10 slots, 37 chars, RGB)
│   ├── model_cct_xs.yaml      # CCT-XS model architecture definition
│   └── train_cct_xs_baseline.yaml # Baseline training hyperparameters
├── data/
│   ├── manifest.schema.json   # JSON Schema for dataset manifests (with group_id)
│   ├── frozen_test_registry.json # 322 public benchmark image & crop digests (strictly 5 fields: row_index, sha256, phash, crop_sha256, crop_phash)
│   └── .gitkeep               # Preserves data directory structure
├── docs/                      # Technical documentation and governance guidelines
│   ├── data-card.md           # Dataset provenance & slice documentation (PII compliance)
│   ├── evaluation-protocol.md # Metric definitions & statistical evaluation procedure
│   ├── integration-with-backend.md # Artifact handover contract and latency budget
│   ├── kaggle-runbook.md      # Operational runbook for Kaggle execution
│   ├── label-studio-template.xml # Label Studio plate crop XML configuration
│   ├── labeling-guide.md      # Double-labeling protocol and transcription rules
│   ├── model-card.md          # Model governance card (CCT-XS architecture & weights)
│   └── promotion-gate.md      # Statistical acceptance criteria (Wilson CIs, McNemar gate)
├── notebooks/                 # Kaggle GPU training notebooks
│   ├── kaggle_train.ipynb     # Validated notebook with DRY_RUN switch and real fit call
│   └── kernel-metadata.json   # Kaggle CLI push metadata with placeholders
├── scripts/                   # Utility scripts for data preparation and export
│   ├── build_dataset.py       # Manifest compilation from raw image crops
│   ├── evaluate_frozen_test.py # Benchmark evaluation on frozen test set (5x spread & latency)
│   ├── export_model.py        # Keras to ONNX export with parity check and region-head slicing
│   └── generate_frozen_registry.py # Reproducible registry builder (full-frame and crop hashes)
├── src/
│   └── plate_training/        # Core Python package
│       ├── __init__.py        # Public package API
│       ├── checkpoint.py      # Atomic SHA-256 checkpoint resume and writer helper
│       ├── cli.py             # CLI commands
│       ├── config.py          # YAML configuration loader and structural validator
│       ├── dataset.py         # Keras Sequence data loader and preprocessing parity module
│       ├── manifest.py        # Manifest loader and JSON schema validator (group_id enforced)
│       ├── metrics.py         # Levenshtein, Exact Match, Char Acc, CER, Review metrics
│       ├── model.py           # Pretrained weight loader, architecture verifier, and region-head slicer
│       ├── normalization.py   # Plate normalizer matching backend logic 100%
│       ├── onnx_parity.py     # Keras vs ONNX inference parity checker
│       └── split.py           # Split leakage detector (full-frame & crop SHA-256/pHash + label collision)
└── tests/                     # Unit test suite
    ├── __init__.py
    ├── test_boundary_routing.py # 9-class scope boundary and special series routing tests
    ├── test_configs.py        # Config schema tests without model training
    ├── test_dataset.py        # Preprocessing parity, label encoding round-trip, and evaluate tests
    ├── test_manifest.py       # Manifest schema and Python object validation tests
    ├── test_metrics.py        # Metric calculation correctness tests
    ├── test_model.py          # Weight loading, 322-crop equivalence, and mutation tests
    ├── test_no_hardcoded_verdicts.py # Anti-facade scanner guarding against hardcoded verdicts
    ├── test_normalization.py  # Plate normalization edge cases tests
    ├── test_notebook_execution.py # AST fit check and DRY_RUN True/False execution tests
    ├── test_onnx_parity.py    # Parity verification tests
    └── test_split_leakage.py  # Full-frame and crop-level exact/pHash split leakage tests
```

> **Note on Lockfile Scope**: `requirements-lock.txt` strictly locks the 34 lightweight packages of `requirements-ci.txt` for fast CPU-only CI gates (`.github/workflows/03-training-check.yml`). The complete GPU training and export stack is defined and pinned in `requirements-train.txt`.

## Data Governance & Personal Data Protection (Decree 13/2023/ND-CP)

In strict compliance with Decree No. 13/2023/ND-CP on Personal Data Protection:

- `training/data/frozen_test_registry.json` holds SHA-256 and 64-bit pHash digests of public-dataset photos (`sonnetechnology/license-plate-text-recognition-full`) and their detector crops (strictly 5 fields: `row_index`, `sha256`, `phash`, `crop_sha256`, `crop_phash`).
- The 322 plate strings of those public benchmark images already appear in the public repository at `tests/parking/fixtures_322_metadata.py`.
- The project never commits plate strings or images from the Owner's own cameras or private operational datasets. Benchmark label collision checks read reference plate strings exclusively from local cache (`benchmark_322_labels.json` in `PLATE_TRAINING_CACHE`).

## License & Intellectual Property Notice

<!-- TODO-Owner: Licensing terms for the training subproject will be finalized by the project owner prior to release. -->

Notice: This directory does NOT contain a LICENSE file. All rights, intellectual property models, and licensing terms are reserved for determination by the project owner (TODO-Owner). Do not add a LICENSE file without explicit written owner authorization.
