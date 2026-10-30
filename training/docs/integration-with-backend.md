# Backend Integration Guide & Artifact Promotion Contract

- **Subproject**: `training/`
- **Consumer**: Parking Management Backend (`apps/parking/services/ocr.py`)
- **Governing Architecture**: [ADR-0007](../../docs/adr/0007-backend-service-in-docker-compose-and-plate-ocr-engine.md) & [ADR-0008](../../docs/adr/0008-plate-recognition-training-pipeline.md)
- **Status**: Active Operational Specification

---

## 1. Overview & Purpose

This document establishes the formal lifecycle contract governing how machine learning artifacts fine-tuned in the `training/` subproject are promoted, verified, and integrated into the production Django backend.

### Architectural Invariant: Zero Runtime Code Modification

The backend recognition service (`FastAlprPlateRecognizer` in `apps/parking/services/ocr.py`) was engineered in ADR-0007 to consume externalized ONNX models and declarative YAML configurations. Promoting an updated model artifact **requires zero code modifications** to application logic in `apps/parking/`. Integration is executed strictly via model file replacement, build-time SHA-256 checksum pinning, and configuration injection.

---

## 2. Artifact Promotion Contract

A model artifact produced by a Kaggle fine-tuning experiment must satisfy the complete artifact package specification before being considered for promotion.

### 2.1. Required Promotion Artifacts Bundle

The promotion bundle delivered by `training/` consists of exactly four artifacts:

| Artifact File | Format / Schema | Specification & Tensor Invariants | Purpose |
|---|---|---|---|
| **Model Weights** (`*.onnx`) | ONNX (opset $\ge 17$) | Input: `[B, 64, 128, 3]` uint8 RGB.<br>Output: `'plate'` tensor `[B, 10, 37]` logits/probabilities.<br>Optimized with `onnxslim`. | Primary CCT-xs-v2 recognition neural network. |
| **Plate Configuration** (`*_plate_config.yaml`) | Declarative YAML | `img_height: 64`<br>`img_width: 128`<br>`max_plate_slots: 10`<br>`alphabet: "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"`<br>`pad_char: "_"`<br>`image_color_mode: rgb` | Model input pre-processing and character decoding rules. |
| **Cryptographic Manifest** (`checksums.sha256`) | Standard sha256sum | 64-character lowercase hex hash for every file in the release bundle. | Supply-chain integrity and tamper-proofing. |
| **Model & Data Documentation** (`model-card.md`, `data-card.md`) | Markdown (Mitchell et al.) | Documented training runs, dataset slices, known limitations, and bias analysis. | Auditability, compliance, and governance record. |

### 2.2. Pre-Promotion Verification Checklist (Promotion Gate)

Before initiating a pull request to the backend, the candidate model must achieve signed off status under `training/docs/promotion-gate.md`:

- [ ] **Sacred Test Non-Regression**: Exact match on 322-row frozen test set $\ge 95.96\%$ (baseline).
- [ ] **Wrong-in-AUTO Ceiling**: Clean wrong-in-AUTO $\le 1.0\%$ (target $\le 0.997\%$) at backend threshold $\tau = 90.0\%$.
- [ ] **AUTO Coverage Floor**: Automated throughput coverage $\ge 93.0\%$ (baseline $93.48\%$).
- [ ] **Slice Stability**: No individual province code or environmental slice (night, glare, angle) regresses by more than $2.0\%$ compared to baseline.
- [ ] **Latency Budget**: Standalone CCT-XS CPU inference latency $\le 10.0\text{ ms}$ `[PROPOSAL]` (Baseline median: 3.79 ms, P95: 6.16 ms; full production pipeline budget $\le 55.0\text{ ms}$, baseline median: 49.35 ms on Intel Core i7-12700H, 1 thread).
- [ ] **ONNX Mathematical Parity**: Numerical divergence between training framework and ONNX Runtime $\le 1 \times 10^{-4}$.
- [ ] **License Audit**: Zero AGPL-3.0 or GPL-3.0 dependencies in the training graph or weights lineage.

---

## 3. Protocol for Backend Pull Request (Separate PR Policy)

To preserve architectural decoupling and audit clarity, model promotions must adhere strictly to the **Separate PR Policy**.

### 3.1. Strict Separation Rules

1. **Never Bundle**: A model promotion to the backend must NEVER be combined with training code changes, dataset updates, or backend feature development.
2. **Dedicated PR Title**: Pull request title must strictly follow the convention:  
   `feat(ocr): promote fine-tuned plate recognizer vX.Y.Z (ADR-0007 addendum)`
3. **Allowed File Changes in Backend PR**:
   - `docs/adr/0007-backend-service-in-docker-compose-and-plate-ocr-engine.md`: Appended Addendum documenting the promotion, performance delta, and checksums.
   - `Dockerfile`: Updated build-time download URLs and pinned SHA-256 checksums.
   - `.env.example` / `docker-compose.yml`: Updated environment variables (if directory or filenames changed).
   - `tests/parking/test_ocr_benchmark.py`: Baseline assertion constants updated to match verified numbers.
   - **STRICTLY FORBIDDEN**: Modifying core business logic in `apps/` or database schemas in `db/`.

---

## 4. Dockerfile Build-Time Download with `sha256sum -c`

To ensure deterministic, tamper-proof builds and preserve air-gapped production operation (`--network none`), model artifacts are baked into the container image at build time.

### 4.1. Production Dockerfile Implementation

In `Dockerfile`, update the model baking layer within the runtime build stage:

```dockerfile
# ------------------------------------------------------------------------------
# OCR Model Weights & Configuration Baking Layer
# Air-gapped guarantees: Downloaded and verified at build time; zero network at runtime.
# ------------------------------------------------------------------------------
ARG OCR_MODELS_DIR=/app/models/ocr
ARG OCR_RELEASE_TAG=v1.1.0-vn-cct-xs

ENV PARKING_OCR_MODELS_DIR=${OCR_MODELS_DIR}

RUN mkdir -p ${OCR_MODELS_DIR} && \
    # 1. Download model weights and config from secure release storage
    curl -fsSL -o ${OCR_MODELS_DIR}/cct_xs_v2_global.onnx \
        https://github.com/example-org/parking_management_backend/releases/download/${OCR_RELEASE_TAG}/cct_xs_v2_global.onnx && \
    curl -fsSL -o ${OCR_MODELS_DIR}/cct_xs_v2_global_plate_config.yaml \
        https://github.com/example-org/parking_management_backend/releases/download/${OCR_RELEASE_TAG}/cct_xs_v2_global_plate_config.yaml && \
    # 2. Pin SHA-256 checksums and verify immediately
    echo "8a4f91e2b5c7...  ${OCR_MODELS_DIR}/cct_xs_v2_global.onnx" > ${OCR_MODELS_DIR}/checksums.sha256 && \
    echo "f3c801d9a2e4...  ${OCR_MODELS_DIR}/cct_xs_v2_global_plate_config.yaml" >> ${OCR_MODELS_DIR}/checksums.sha256 && \
    sha256sum -c ${OCR_MODELS_DIR}/checksums.sha256 && \
    # 3. Ensure proper file permissions for unprivileged appuser
    chown -R appuser:appgroup ${OCR_MODELS_DIR} && \
    chmod 644 ${OCR_MODELS_DIR}/*
```

### 4.2. Build Failure Conditions

If the downloaded artifact does not match the pinned SHA-256 checksum byte-for-byte, `sha256sum -c` fails immediately with exit code `1`, aborting the Docker build and preventing corrupted or tampered weights from deploying to staging or production.

---

## 5. Runtime Configuration via `PARKING_OCR_MODELS_DIR`

The backend resolves model files dynamically via the environment variable `PARKING_OCR_MODELS_DIR`.

### 5.1. Directory Structure Resolution

The directory pointed to by `PARKING_OCR_MODELS_DIR` must contain the following file structure:

```text
/app/models/ocr/
├── yolo-v9-t-384-license-plates-end2end.onnx  # Detector (frozen)
├── cct_xs_v2_global.onnx                     # Primary Recognizer (promoted)
├── cct_xs_v2_global_plate_config.yaml        # Primary Recognizer Config
├── global_mobile_vit_v2_ocr.onnx             # Ensemble Recognizer
├── global_mobile_vit_v2_ocr_config.yaml      # Ensemble Recognizer Config
└── checksums.sha256                          # Build verification manifest
```

### 5.2. Backend Loading Mechanism (`apps/parking/services/ocr.py`)

During worker initialization, `FastAlprPlateRecognizer._initialize()` inspects `settings.PARKING_OCR_MODELS_DIR`:

```python
models_dir = Path(settings.PARKING_OCR_MODELS_DIR)

cct_model_file = models_dir / "cct_xs_v2_global.onnx"
cct_cfg_file = models_dir / "cct_xs_v2_global_plate_config.yaml"

if cct_model_file.is_file() and cct_cfg_file.is_file():
    self._ocr_cct = fast_plate_ocr.LicensePlateRecognizer(
        onnx_model_path=cct_model_file,
        plate_config_path=cct_cfg_file,
        sess_options=opts,
    )
else:
    # Fallback to packaged hub defaults if custom directory is not provided
    self._ocr_cct = fast_plate_ocr.LicensePlateRecognizer(
        hub_ocr_model="cct-xs-v2-global-model",
        sess_options=opts,
    )
```

If `PARKING_OCR_MODELS_DIR` is set to an invalid path or files are unreadable, the initialization records `self._init_error` and subsequent scan attempts raise a descriptive `RuntimeError`, failing fast rather than silently producing garbage predictions.

---

## 6. Backend Benchmark Re-Verification Protocol

Before any model promotion PR can be merged, the backend team must execute the full benchmark suite inside an isolated Linux container to independently re-verify performance claims.

### 6.1. Mandatory Verification Commands

Run the following test commands sequentially:

```bash
# 1. Unit & Integration OCR Benchmarks
pytest tests/parking/test_ocr_benchmark.py -v

# 2. Comprehensive 322-Row Review Policy Benchmark
python tests/parking/benchmark_plate_correction_and_review_policy.py

# 3. 5-Fold Nested Cross-Validation Stability Test
python tests/parking/nested_cv_evaluation.py

# 4. Gunicorn Serving & Concurrency Soak Verification
pytest tests/parking/test_gunicorn_rss_watchdog.py
```

### 6.2. Acceptance Scorecard

| Benchmark Metric | Baseline (ADR-0007 / S2) | Promotion Acceptance Threshold | Action on Failure |
|---|---|---|---|
| **Exact Match (Full 322 Rows)** | $95.96\%$ ($309/322$) | $\ge 95.00\%$ (Regression Guard `[PROPOSAL]`) | Block PR. Investigate misread rows. |
| **Exact Match (Set 1: 0..99)** | $96.00\%$ ($96/100$ measured) | $\ge 96.00\%$ | Block PR. (+3.00% over standalone CCT-XS via positional correction). |
| **Exact Match (Set 2: 100..199)** | $97.00\%$ ($97/100$ measured) | $\ge 97.00\%$ | Block PR. (+1.00% over standalone CCT-XS via positional correction). |
| **Clean Wrong-in-AUTO** | $0.997\%$ ($3/301$) | 1-Sided 95% Wilson Upper Bound $\le 1.00\%$ `[PROPOSAL]` | Block PR. Automated gate opening compromised. (Baseline upper bound is $2.47\%$). |
| **AUTO Coverage** | $93.48\%$ ($301/322$) | $\ge 93.00\%$ | Block PR. Operator workload increased. |
| **Average Scan Latency (FHD)** | Standalone: $3.79\text{ ms}$ / Pipeline: $49.35\text{ ms}$ | Standalone $\le 10.0\text{ ms}$ / Pipeline $\le 55.0\text{ ms}$ `[PROPOSAL]` | Block PR. CPU bottleneck detected. (Intel i7-12700H, 1 thread). |
| **Corrupted Plate Repair** | $104/104$ ($100\%$) | $100\%$ ($0$ broken correct reads) | Block PR. Grammar correction regressed. |

---

## 7. Rollback Playbook & Disaster Recovery

If anomalous behavior, degraded accuracy, or unexpected CPU latency is observed in production following a model promotion, execute the following staged rollback procedure.

### 7.1. Level 1: Hot Environment Variable Switch (Zero Rebuild)

If the previous model files were retained in the image under `/app/models/ocr_v_prev/`:

1. Update `docker-compose.yml` or environment configuration:

   ```yaml
   environment:
     - PARKING_OCR_MODELS_DIR=/app/models/ocr_v_prev
   ```

2. Trigger graceful reload:

   ```bash
   docker compose up -d web
   ```

3. Workers restart gracefully via Gunicorn zero-downtime reload; `FastAlprPlateRecognizer` re-initializes with previous weights. Downtime: **0 seconds**.

### 7.2. Level 2: Docker Image Tag Rollback

If weights were baked exclusively into the latest image tag:

1. Re-deploy the previously verified Docker image tag:

   ```bash
   docker compose pull web:v1.0.4-stable
   docker compose up -d web
   ```

2. Execution time: $< 30\text{ seconds}$.

### 7.3. Level 3: Git Revert of Promotion PR

1. Execute `git revert <promotion_commit_sha>` on `dev` and `main`.
2. Push revert PR; CI executes full regression test suite.
3. Automatically triggers standard CD deployment pipeline.

### 7.4. Incident Post-Mortem & Data Triage

1. Query scan audit logs for all scans flagged with `review_status = "NEEDS_REVIEW"` or operator-overridden transactions.
2. Export captured crop images and ground truth corrections to the triage bucket.
3. Incorporate failure cases as hard negatives into the next training iteration cycle in `training/`.
