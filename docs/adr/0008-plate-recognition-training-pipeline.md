# ADR-0008: Vietnamese License Plate Recognition Fine-Tuning Pipeline on Kaggle

- **Status**: Proposed
- **Date**: 2026-10-25
- **Deciders**: Project Owner, Tech Lead, ML Engineering Team, Backend Team
- **Technical Context**: Machine Learning Lifecycle, License Plate Recognition (ALPR/ANPR), Transfer Learning, Kaggle GPU Pipeline, Open-Source Licensing Compliance, Decree 13/2023/ND-CP Personal Data Governance

---

## 1. Context & Problem Statement

In [ADR-0007](0007-backend-service-in-docker-compose-and-plate-ocr-engine.md), the backend service adopted an offline Dual-OCR Ensemble architecture for Vietnamese license plate recognition:

- **Object Detection**: Lightweight YOLOv9-t 384 (`yolo-v9-t-384-license-plates-end2end.onnx`) from `open-image-models` (MIT License).
- **Text Recognition**: Primary model Compact Convolutional Transformer (`cct_xs_v2_global.onnx`, 3 channels RGB, 64x128) paired with Mobile-ViT-v2 (`global_mobile_vit_v2_ocr.onnx`, 1 channel Grayscale, 70x140) from `fast-plate-ocr` (MIT License).
- **Inference Runtime**: CPU-inferable ONNX Runtime (`1.31.0`), achieving an average latency of ~32.8 ms per scan, baked into the Docker image with build-time SHA-256 verification.

### Problem Statement

While the production baseline achieves an exact match rate of **95.96% (309/322)** and a clean wrong-in-AUTO rate of **0.997% (3/301)** on the 322-row benchmark dataset (`sonnetechnology/license-plate-text-recognition-full`, Parquet SHA-256 `843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b`), edge cases in Vietnamese license plates remain challenging:

1. **Confusable Characters**: Inherent visual ambiguity between numeric `0` and alphabetic `D` / `O` / `Q`, numeric `8` and alphabetic `B`, numeric `5` and alphabetic `S`, numeric `1` and alphabetic `I` / `T` under varying illumination, dirt, or slight tilt.
2. **Vietnamese Specific Font Metrics & 2-Line Formats**: Vietnamese standard plates (Circular 24/2023/TT-BCA, Circular 79/2024/TT-BCA, Circular 51/2025/TT-BCA) employ specific embossed font glyphs and spacing distinct from European/Latin plates on which global models were predominantly pretrained.
3. **Absence of a Repeatable, Isolated Fine-Tuning Pipeline**: To improve recognition accuracy on Vietnamese plates without destabilizing the production Django backend, an enterprise-grade training and evaluation pipeline is required.

### Core Constraints & Governance Principles

1. **Owner Scope Alignment**: Fine-tuning is strictly transfer learning on top of published recognizer `cct_xs_v2_global` (not training from scratch). The first model targets single-line civilian car plates (`^\d{2}[A-Z]\d{4,5}$`). Military, agency 80, diplomatic/special (`NG`, `QT`, `CV`, `NN`, `LD`, `DA`, `KT`, `CD`, `TD`), and motorbike plates are out of scope and continue routing to `NEEDS_REVIEW` via backend statutory rules. Coverage of those out-of-scope types is unmeasured, detector behavior on them is `UNVERIFIED`, and extending the scope requires real, lawfully collected images of each type (a separate decision of the Owner).
2. **Zero Local Training Invariant**: In accordance with executive directive, all model training (gradient calculation, backpropagation, and epoch execution) is strictly prohibited on local workstations. Training must execute solely on cloud GPU infrastructure (Kaggle Notebooks).
3. **Subproject Isolation**: The training pipeline must reside in a dedicated subproject (`training/`) within the repository, completely decoupled from runtime backend dependencies (`apps/`, `config/`), excluded from the runtime Docker image via `.dockerignore`, and excluded from backend linting and coverage suites.
4. **Sacred Frozen Test Dataset & Hash Registry**: The 322-row benchmark dataset (`sonnetechnology/license-plate-text-recognition-full`, Parquet SHA-256 `843233e5...`, CC-BY-4.0) is held out permanently. To ensure zero PII duplication under Decree 13/2023/ND-CP, raw plain-text plate JSON fixtures are completely excluded from repository tracking. Test set validation is anchored solely by `training/data/frozen_test_registry.json` containing only image SHA-256 and 64-bit pHash values (0 plate text, 0 image bytes), while `tests/parking/fixtures_322_metadata.py` remains the pre-existing backend fixture.
5. **Permissive Open-Source Licensing**: All training code, dependencies, and model weights must adhere to permissive licenses (MIT, Apache-2.0, BSD-3-Clause). Viral copyleft licenses (AGPL-3.0 in Ultralytics YOLOv8/v11 and PyMuPDF, GPL-3.0 in WongKinYiu/yolov9) are strictly forbidden.
6. **Personal Data Protection (Decree 13/2023/ND-CP)**: Vehicle license plates contextualized with vehicle images constitute personal data under Vietnamese law. Datasets containing real plates must be hosted strictly in private cloud storage (`is_private: true`), never committed to public Git repositories, and access tokens must never be logged or stored in repository code.

---

## 2. Decision Outcome

We establish a comprehensive architecture for the Vietnamese license plate recognition training and artifact promotion pipeline.

### 2.1. Subproject Isolation & Repository Topology

The repository topology strictly isolates training artifacts from backend runtime code:

```text
parking_management_backend/
├── apps/                          # Django backend runtime (Untouched)
├── config/                        # Django configuration (Untouched)
├── docker/                        # Deployment orchestration (Untouched)
├── docs/
│   └── adr/
│       ├── 0007-backend-service-in-docker-compose-and-plate-ocr-engine.md
│       └── 0008-plate-recognition-training-pipeline.md  # This document
├── training/                      # Isolated training subproject
│   ├── README.md                  # Subproject guide with TODO-Owner license note
│   ├── pyproject.toml             # Independent pyproject: ruff, mypy, pytest
│   ├── requirements.txt           # General training dependencies
│   ├── requirements-train.txt     # Exact pinned (==) dependencies for Kaggle GPU training
│   ├── requirements-ci.txt        # Lightweight CI dependencies (zero PyTorch/CUDA)
│   ├── requirements-lock.txt      # Hash-pinned lockfile for requirements-ci.txt ONLY (34 packages, Python 3.14)
│   ├── configs/                   # Declarative YAML configurations
│   │   ├── plate_config_vn.yaml   # Plate pre-processing (64x128, 10 slots, 37 chars, 66 regions)
│   │   ├── model_cct_xs.yaml      # CCT-xs-v2 model architecture definition (18 layers, 7 TransformerBlocks)
│   │   └── train_cct_xs_baseline.yaml # Kaggle fine-tuning hyperparameters
│   ├── data/
│   │   ├── manifest.schema.json   # Draft 2020-12 JSON schema for dataset manifest (with group_id)
│   │   └── frozen_test_registry.json # 322 public benchmark image & crop digests (strictly 5 fields: row_index, sha256, phash, crop_sha256, crop_phash)
│   ├── docs/
│   │   ├── labeling-guide.md      # Label Studio transcription rules
│   │   ├── kaggle-runbook.md      # Operational runbook for Kaggle execution
│   │   ├── data-card.md           # Dataset provenance & slice documentation
│   │   ├── model-card.md          # Mitchell et al. model governance card
│   │   ├── evaluation-protocol.md # Metric definitions & evaluation procedure
│   │   ├── promotion-gate.md      # Statistical acceptance criteria (PROPOSAL)
│   │   └── integration-with-backend.md # Artifact handover contract
│   ├── notebooks/
│   │   ├── kaggle_train.ipynb     # Cloud training notebook (DRY_RUN switch)
│   │   └── kernel-metadata.json   # Kaggle CLI metadata
│   ├── scripts/                   # CLI utilities (build_dataset, evaluate_frozen_test, export_model, generate_frozen_registry)
│   ├── src/plate_training/        # Fully typed Python package
│   │   ├── checkpoint.py          # Pure checkpoint discovery & epoch resume selection
│   │   ├── cli.py                 # Developer command-line interface
│   │   ├── config.py              # Pydantic training configuration validator
│   │   ├── dataset.py             # Real manifest-to-PyDataset loader & 64x128 RGB preprocessor
│   │   ├── manifest.py            # Manifest schema, group_id enforcement & SHA-256 file integrity validator
│   │   ├── metrics.py             # Exact match, character accuracy, edit distance, AUTO metrics
│   │   ├── model.py               # CCT-XS Keras model builder & published weight loader / region-head slicer
│   │   ├── normalization.py       # Plate text normalization parity with backend
│   │   ├── onnx_parity.py         # Real Keras-vs-ONNX Runtime forward-pass parity check
│   │   └── split.py               # Fail-closed photo/crop SHA-256, 64-bit pHash, group_id & label-collision guard
│   └── tests/                     # Fast CPU unit & mutation tests (zero GPU, zero network in CI)
└── .github/workflows/
    ├── 02-django-check.yml        # Backend CI workflow (excludes training/**)
    └── 03-training-check.yml      # Dedicated training subproject CI workflow
```

#### Isolation Invariants

- **Root `pyproject.toml` Exclusion**: `training/` is explicitly excluded from backend `ruff`, `mypy`, `pytest` collection, and test coverage calculation.
- **Docker Runtime Exclusion**: `.dockerignore` contains `training/` and `kaggle.json`, guaranteeing zero training code or artifacts leak into production container images.
- **Dedicated CI Workflow**: `.github/workflows/03-training-check.yml` triggers exclusively on changes to `training/**`, executing formatting, typing, and unit tests independently.

---

### 2.2. Text Recognizer Architecture Decision Table

To select the optical character recognition architecture for fine-tuning on Vietnamese license plates, four candidate paradigms were evaluated against core project requirements:

| Evaluation Criterion | Option 1: Fine-tune fast-plate-ocr CCT-XS (Selected) | Option 2: Train CCT-XS From Scratch | Option 3: Transformer OCR (TrOCR) | Option 4: PaddleOCR (PP-OCRv4 Recognizer) |
|---|---|---|---|---|
| **Open-Source License** | **MIT License** (Fully permissive, zero copyleft risk) | **MIT License** | **MIT / Apache-2.0** (Microsoft / Hugging Face) | **Apache-2.0** (Baidu) |
| **Vietnamese Plate Accuracy Potential** | **Very High** (Pretrained on multi-million global plates, adapts quickly to VN font variations) | **Moderate to Low** (Requires >100,000 labeled images to generalize without overfitting) | **Very High** (Strong linguistic attention on sequence) | **High** (Strong on general scene text) |
| **Single-Image CPU Latency** | **3.79 ms median / 6.16 ms p95** (Measured standalone CCT-XS on Intel i7-12700H, 1 thread; well within 10 ms recognition budget) | ~3.8 ms | **200 – 800 ms** (Autoregressive beam search decoder is prohibitive on CPU) | ~25 – 45 ms (Acceptable, but higher memory footprint) |
| **ONNX Runtime Export** | **Native 1-click export** (`fast_plate_ocr export --export-type onnx`), validated with `onnxslim` | Native 1-click export | **Complex & Fragile** (Separate encoder/decoder graphs, dynamic kv-cache) | Requires `Paddle2ONNX` toolchain (frequent operator conversion bugs) |
| **Runtime Compatibility** | **100% Drop-in Compatibility** with existing `FastAlprPlateRecognizer` backend | 100% Compatible | Zero compatibility (Requires complete backend rewrite) | Low compatibility (Requires custom pre/post-processing glue code) |
| **Engineering Effort** | **Minimal** (Leverages existing `fast-plate-ocr` library and configs) | High (Data collection burden, hyperparameter grid search) | Very High (Custom pipeline, slow serving, heavy dependencies) | High (Secondary deep learning ecosystem in Python runtime) |
| **Technical & Architectural Risk** | **Extremely Low** | High (Sample efficiency risk on small private datasets) | Critical (Breaks 33 ms latency budget and throughput SLAs) | Moderate to High (Ecosystem fragmentation, dual runtime dependencies) |

#### Recommendation & Decision

**Selected: Option 1 — Fine-tune `fast-plate-ocr` Compact Convolutional Transformer (`cct_xs_v2_global`).**
*Rationale*: CCT-XS offers the optimal trade-off between character-level representation power, tiny compute footprint (3.79 ms median standalone CPU latency, 791,700 parameters), seamless ONNX export, and 100% drop-in compatibility with the existing production backend. Fine-tuning from existing global weights focuses strictly on civilian car 1-line plates; out-of-scope categories (military, 80, NG/QT/special series, motorbike) are safely handled by the backend review policy.

---

### 2.3. Plate Detector Governance & Alternative Policy

1. **Current Production Policy (Frozen Pretrained Weights)**:
   - The primary detector `yolo-v9-t-384-license-plates-end2end.onnx` provided by `open-image-models` (MIT License) remains **frozen** in Phase 0 and Phase 1.
   - The detector delivers 98.7% first-pass detection rate and 100% recovery with fallback retry (`conf_thresh = 0.02`), adding 0.00 ms latency overhead for 98.7% of scans.
2. **Strict Prohibition of Copyleft Detector Repositories**:
   - **GPL-3.0**: The original YOLOv9 training repository (`WongKinYiu/yolov9`) is licensed under GPL-3.0. No code, scripts, or training recipes from this repository may enter our codebase.
   - **AGPL-3.0**: Ultralytics YOLO repositories (YOLOv5, YOLOv8, YOLOv11) are licensed under AGPL-3.0. Incorporating Ultralytics code or fine-tuning pipelines is strictly prohibited under ADR-0007 and corporate IP guidelines.
3. **Pre-Approved License-Clean Alternatives for Future Detector Fine-Tuning**:
   If future operational requirements necessitate fine-tuning the detector stage, only permissive, license-clean alternatives may be adopted:
   - **RT-DETR (Real-Time DEtection TRansformer)**: Apache-2.0 License (Baidu / PaddleDetection / `lyuwen`). End-to-end transformer architecture, eliminates NMS post-processing, native ONNX export.
   - **YOLOX**: Apache-2.0 License (Megvii). Anchor-free, battle-tested in commercial deployments.
   - **YOLOv6**: Apache-2.0 License (Meituan). Hardware-optimized for edge and CPU inference.
   - **Torchvision Detection (SSDlite / RetinaNet)**: BSD-3-Clause License.

---

### 2.4. Cloud Training Infrastructure (Kaggle GPU)

Training will be executed remotely in Kaggle Notebooks under the following technical specifications:

| Hardware / Platform Dimension | Specification / Constraint | Operational Rationale |
|---|---|---|
| **Cloud Platform** | Kaggle Notebooks (Web / CLI) | Free tier GPU allocation, reproducible environment, enterprise security controls |
| **GPU Accelerators** | NVIDIA Tesla T4 x2 (16GB x2) or P100 (16GB) | Accelerated mixed-precision training (FP16/BF16) |
| **Weekly Resource Quota** | 30 GPU-hours per rolling 7 days [UNVERIFIED - Platform Dependent] | Requires disciplined epoch budgeting and fast convergence |
| **Maximum Session Duration** | Up to 12 hours for batch commit (`kaggle kernels push`) [UNVERIFIED - Platform Dependent] (CLI default: 3600s via `-t, --timeout` per `https://github.com/Kaggle/kaggle-api`) | Requires per-epoch checkpointing and resume capability |
| **Deep Learning Framework** | Keras 3 with PyTorch Backend (`KERAS_BACKEND=torch`) | Inherited from upstream `fast-plate-ocr` library; memory efficiency and CUDA stability are architectural hypotheses `[HYPOTHESIS]` to be empirically verified during the Stage 0 Kaggle smoke run |
| **Network & Security Boundary** | Air-gapped execution (`enable_internet: false`) | Compliant with corporate offline data security standards |
| **Offline Dependency Strategy** | Pre-bundled `.whl` files via Kaggle Dataset | Pinned SHA-256 wheels installed via `pip install --no-index --find-links=...` |
| **Authentication & Telemetry** | SMS Phone-Verified Account [UNVERIFIED - Platform & Account Dependent] | Required by Kaggle to enable GPU runtimes and outbound internet access |

---

### 2.5. Data Policy, Manifest Schema & Leakage Prevention

1. **Manifest Contract (`training/data/manifest.schema.json`)**:
   Every dataset utilized in the training pipeline must be cataloged in a JSON manifest conforming to JSON Schema Draft 2020-12:
   - `image_path`: Relative file path within dataset bundle.
   - `sha256`: 64-character lowercase hexadecimal hash of raw image bytes.
   - `plate_text`: Ground truth transcription (raw string).
   - `plate_normalized`: Uppercase alphanumeric transcription (identical to backend `PlateRecognizer.normalize_plate`).
   - `split`: Enumerated partition (`"train"`, `"val"`, `"frozen-test"`).
   - `license`: SPDX license identifier (e.g., `"CC-BY-4.0"`, `"Proprietary"`).
   - `provenance`: Originating source, collection context, and anonymization status.
   - `group_id`: Vehicle or capture session identifier (mandatory for non-public splits to eliminate multi-frame cross-split contamination).
2. **Multi-Tier Split Leakage Invariants**:
   To prevent data leakage and guarantee valid generalization estimates, `plate_training.split` enforces multi-tiered barriers:
   - **Tier 1 (Exact SHA-256 Guard)**: No SHA-256 hash registered in `training/data/frozen_test_registry.json` or cross-split partitions may appear in `train` or `val`. Missing image files trigger fail-closed abortion (`allow_missing_files = False`).
   - **Tier 2 (Perceptual pHash Near-Duplicate Guard)**: Evaluates pairwise Hamming distance across all split combinations (`train` vs `val`, `train` vs `frozen-test`, `val` vs `frozen-test`). Hamming distance $\le 4$ enforces co-partitioning. Furthermore, multi-frame vehicle captures require explicit `group_id` metadata in the manifest to prohibit cross-split vehicle leakage.
3. **Decree 13/2023/ND-CP Personal Data Governance**:
   - Real vehicle plate captures constitute personal data.
   - Raw image datasets are categorized as confidential and hosted solely in private Kaggle datasets (`"isPrivate": "true"`).
   - Committing real vehicle license plate images to the Git repository is strictly prohibited.
   - `training/data/frozen_test_registry.json` holds SHA-256 and 64-bit pHash digests of public-dataset photos (`sonnetechnology/license-plate-text-recognition-full`) and their detector crops (strictly 5 fields: `row_index`, `sha256`, `phash`, `crop_sha256`, `crop_phash`).
   - The 322 plate strings of those public benchmark images already appear in the public repository at `tests/parking/fixtures_322_metadata.py`.
   - The project never commits plate strings or images from the Owner's own cameras or private operational datasets.

---

### 2.6. Baseline Reproduction & No-Training Verification

The Phase 0 baseline verification established and proved model integrity on CPU without executing any model training:

1. **Empirical Baseline Reproduction on Sacred Frozen Test Set (`sonnetechnology`, 322 rows, SHA-256 `843233e5...`)**:
   - **Set 1 (Rows 0..99)**: Exact Match **93.00%**, Character Accuracy **98.12%**.
   - **Set 2 (Rows 100..199)**: Exact Match **96.00%**, Character Accuracy **99.37%**.
   - **Tuning Split (161 Even Rows)**: AUTO Coverage **93.17%**, Wrong-in-AUTO **2.67%** (4/150).
   - **Test Split (161 Odd Rows)**: AUTO Coverage **95.03%**, Wrong-in-AUTO **0.65%** (1/153 $\le 1.0\%$).
   - **Full 322 Rows**: Exact Match **95.96%** (309/322), AUTO Coverage **93.48%** (301/322), Clean Wrong-in-AUTO **0.997%** (3/301 $\le 1.0\%$), Conservative Wrong-in-AUTO **1.33%** (4/301). Standalone CCT-XS CPU latency median **3.79 ms** (P95 **6.16 ms**); full production pipeline median **49.35 ms** (P95 **86.88 ms**, mean **46.83 ms** $\pm$ **1.99 ms** across 5 repeated runs with exact match standard deviation **0.00%** on Intel Core i7-12700H, 1 thread).
   - All reproduced metrics match ADR-0007 with **$\Delta = 0.00\%$**.
2. **ONNX Export & Parity Verification**:
   - Pretrained CCT-XS Keras weights built from YAML configurations and exported to ONNX format (published 2-head ONNX: 3,344,292 bytes, 791,700 initializer values; single-head export with onnxslim: 2,377,330 bytes, 574,053 initializer values).
   - Mathematical output equivalence between Keras and ONNX Runtime confirmed: `max_diff = 1.86e-8 <= 1e-4` on synthetic tensors.
   - Verified that `FastAlprPlateRecognizer` loads the exported ONNX model via `PARKING_OCR_MODELS_DIR` and successfully processes mock images without code modification.
3. **Dry-Run Notebook Execution**:
   - `training/notebooks/kaggle_train.ipynb` executed locally with `DRY_RUN=True` via `jupyter nbconvert --execute`.
   - Verified 0 epochs, 0 weight updates, 0 secret leakages, validating end-to-end syntax and data pipelines safely on CPU.

---

## 3. Consequences & Risks

### 3.1. Positive Consequences

- **Complete Decoupling**: Backend production codebase (`apps/`, `config/`) remains lean, stable, and completely untouched during ML research iterations.
- **Enterprise Reproducibility**: Manifest hashing, pinned dependencies, declarative configs, and seed locking ensure any experiment on Kaggle can be reproduced bit-for-bit.
- **Strict IP & Compliance Safety**: Elimination of AGPL/GPL dependencies safeguards commercial ownership; private cloud datasets comply with Decree 13/2023/ND-CP.
- **Guaranteed Test Set Sanctity**: Zero leakage into train/val preserves the integrity of the 322-row benchmark as a trustworthy gatekeeper.
- **Zero Local Workstation Burden**: ML training overhead is shifted entirely to cloud GPUs.

### 3.2. Negative Consequences & Trade-offs

- **Cloud Quota Latency**: Development iterations are constrained by Kaggle’s weekly GPU quota (~30 hours) and session duration limits (up to 12 hours) [UNVERIFIED - Platform Dependent].
- **Dual Virtual Environments**: Engineers must maintain distinct virtual environments for backend Django development (`requirements/local.txt`) and ML training (`training/requirements.txt`).
- **Two-Step Release Overhead**: Promoting a newly trained model requires a separate, formal PR to the backend repository with full regression re-verification.

### 3.3. Risks & Mitigations

| Risk Description | Severity | Likelihood | Mitigation Strategy |
|---|---|---|---|
| **Training Split Leakage**: Sacred test images contaminate training data, inflating accuracy metrics. | Critical | Low | Two-tier automated CI gate (`test_split_leakage.py` checking exact SHA-256 and pHash Hamming $\le 4$). |
| **Decree 13 Non-Compliance**: Real license plate images leaked to public repositories or unauthenticated storage. | Critical | Very Low | Automated git pre-commit checks, `.gitignore` wildcards for `training/data/**`, strictly enforced private Kaggle datasets. |
| **Kaggle API Token Leakage**: Developer commits `kaggle.json` or embeds tokens in notebooks. | High | Low | Repository root `.gitignore` ignores `kaggle.json` and `.kaggle/`; CI scanner blocks any commits containing `kaggle.json` or API tokens; runbook instructs placement in `~/.kaggle/`. |
| **Supply-Chain Dependency Poisoning**: Unverified wheel files or pretrained weights downloaded at runtime. | High | Low | Pinned SHA-256 checksums required for all wheel artifacts and base model weights in `requirements-lock.txt` and configs. |
| **Kaggle Session Interruption**: Session timeout (up to 12 hours [UNVERIFIED - Platform Dependent]) or spot instance reclaim aborts training mid-run. | Medium | Moderate | Per-epoch model checkpointing with automated resume logic in `kaggle_train.ipynb`. |
| **Model Drift / Silent Regression**: Fine-tuned model overfits to specific training slices while degrading on production edge cases. | High | Moderate | Strict Promotion Gate protocol (`training/docs/promotion-gate.md`) requiring non-regression across all slices before backend acceptance. |

---

## 4. References

1. [ADR-0001: Fixed Tech Stack & LTS Roadmap](0001-fixed-tech-stack-and-lts-roadmap.md)
2. [ADR-0005: Local PostgreSQL 18 via Docker Compose](0005-local-docker-compose-for-postgresql.md)
3. [ADR-0007: Backend Service in Docker Compose and Plate OCR Engine Selection](0007-backend-service-in-docker-compose-and-plate-ocr-engine.md)
4. Fast-Plate-OCR Project: <https://github.com/ankandrew/fast-plate-ocr> (MIT License)
5. Open-Image-Models Project: <https://github.com/ankandrew/open-image-models> (MIT License)
6. Keras 3 Multi-Backend Documentation: <https://keras.io/keras_3/>
7. Kaggle API & Kernel Specifications: <https://github.com/Kaggle/kaggle-api> (Official CLI timeout flag definition: "-t, --timeout: Timeout in seconds for kernel execution (default 3600)")
8. Dataset `sonnetechnology/license-plate-text-recognition-full`: <https://huggingface.co/datasets/sonnetechnology/license-plate-text-recognition-full> (CC-BY-4.0)
9. Government of Vietnam: *Decree No. 13/2023/ND-CP on Personal Data Protection*, effective July 1, 2023.
10. Ministry of Public Security of Vietnam: *Circular No. 24/2023/TT-BCA*, *Circular No. 79/2024/TT-BCA*, and *Circular No. 51/2025/TT-BCA* on vehicle registration and license plates.
11. Kaggle Docker Python Images: <https://github.com/Kaggle/docker-python>
