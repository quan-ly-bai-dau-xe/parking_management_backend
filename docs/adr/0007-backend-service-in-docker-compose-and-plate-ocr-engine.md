# ADR-0007: Backend Service in Docker Compose and Plate OCR Engine Selection

- **Status**: Proposed
- **Date**: 2026-10-19 (Updated in Round 34 & Round 35 with Dual-OCR Adaptive Ensemble, Review Policy, Vietnamese Plate Regulations `11..99`, 180s Soak Test & Security Threat Model)
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Containerization, Microservices Topology, Offline License Plate OCR Engine, Docker Host Volume Preservation

## 1. Context & Problem Statement

To deliver a turnkey local development and production-ready deployment environment, the backend Django REST application must be containerized and orchestrated alongside the existing PostgreSQL 18.6 database service ([ADR-0005](0005-local-docker-compose-for-postgresql.md)).

Key challenges and technical constraints include:

1. **Python Runtime & Package Baseline**: Ensuring runtime parity with the project standard Python `3.14.7-slim` while preventing Python 3.15 fragmentation ([ADR-0001](0001-fixed-tech-stack-and-lts-roadmap.md)).
2. **License Plate OCR Engine Selection**: The parking management system requires an offline, CPU-inferable License Plate Recognition (ALPR/ANPR) engine adhering strictly to permissive open-source licenses (MIT/Apache-2.0) and avoiding copyleft/viral licenses (AGPL-3.0 in Ultralytics YOLOv8 and PyMuPDF) which would compromise proprietary repository governance.
3. **Docker Host Volume Preservation**: The host environment operates under a strict safety invariant of exactly 27 Docker volumes (`(docker volume ls -q).Count == 27`). Any container orchestration must never create dangling named volumes or purge existing volumes (`docker compose down -v` and `docker volume prune` are strictly prohibited).
4. **Security & Least Privilege**: The container must run as a dedicated unprivileged user (`appuser:appgroup`), expose ports exclusively to local loopback interface (`127.0.0.1`), and provide an automated healthcheck probe (`/api/health/`).
5. **Air-Gapped Operation**: OCR models must be baked at Docker image build time into `/home/appuser/.cache/` (or `/app/models/ocr`), guaranteeing zero runtime network egress (`--network none`).

## 2. Decision Outcome

### 2.1. Backend Containerization (`Dockerfile`)

- **Base Image**: Strictly pinned to `python:3.14.7-slim` (Debian bookworm slim).
- **System Dependencies**: Minimal headless runtime packages installed in a single cached layer:
  - `curl`: Used for Docker native healthcheck probes.
  - `libpq-dev`: PostgreSQL client runtime for `psycopg` connection pooling.
  - `libgl1`, `libglib2.0-0`, `libgomp1`: Headless system libraries required for computer vision and ONNX runtime inference without heavy desktop X11 overhead.
  - APT lists cache is purged (`rm -rf /var/lib/apt/lists/*`) in the same layer to minimize image footprint.
- **Security Hardening (Non-Root User)**:
  - Create dedicated system group `appgroup` (GID 1000) and user `appuser` (UID 1000).
  - Application source code and media directories (`/app/media`, `/app/staticfiles`) are owned by `appuser:appgroup`.
  - Container process drops root privileges via `USER appuser`.
- **Automated Healthcheck**:

  ```dockerfile
  HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
    CMD curl -f http://127.0.0.1:8000/api/health/ || exit 1
  ```

- **Lifecycle Management (`docker/entrypoint.sh`)**:
  - Maintained as an executable script at `docker/entrypoint.sh` with `set -eu`.
  - Probes PostgreSQL TCP connectivity before invoking application commands.
  - Automatically executes `python manage.py migrate --noinput` to guarantee schema readiness when `RUN_MIGRATIONS=1`.
  - Loads sample catalog data when `LOAD_SAMPLE_DATA=1` via `python manage.py load_sample_data` (fails loudly on error; no silent fallback).
  - Hands over process execution to the main command via `exec "$@"`.

### 2.2. Service Orchestration (`docker-compose.yml`)

- **Service Topology**:
  - `db`: PostgreSQL 18.6 Alpine container with named volume `postgres_data` mounted at `/var/lib/postgresql` ([ADR-0005](0005-local-docker-compose-for-postgresql.md)).
  - `web`: Built from root `Dockerfile`, linked to `db` via Docker internal bridge network with `depends_on: db: { condition: service_healthy }`.
- **Network Security Boundary**:
  - Ports bound exclusively to `127.0.0.1:${WEB_PORT:-8000}:8000` to prevent exposure across public or shared Wi-Fi networks.
- **Media Storage Persistence via Bind Mount**:
  - Persisted strictly via directory bind mount `./media:/app/media`.
  - **Zero Named Volume for Media**: Named volumes for media are strictly prohibited to maintain volume preservation and allow direct host access to uploaded captures.

### 2.3. License Plate OCR Engine Selection & Measured Benchmark

#### 2.3.1 Selected Engine: `Fast-ALPR` (MIT License)

- **Selected Engine**: `fast-alpr[onnx]==0.4.0` (MIT License).
  - Multi-stage pipeline: Object detection for license plate bounding box (`yolo-v9-t-384-license-plates-end2end.onnx`) + text recognition via lightweight OCR model (`cct_xs_v2_global.onnx`).
  - Powered by ONNX Runtime for CPU-optimized inference without requiring GPU acceleration.
  - **Runtime Versions**:
    - Production Docker Container: `onnxruntime==1.31.0` (Python 3.14.7-slim).
    - Host Development Environment: `onnxruntime==1.30.0`.
  - Permissive MIT license allows proprietary commercial use and distribution with zero copyleft contagion.

#### 2.3.2 Empirical 3-Engine Benchmark on 100 Vietnamese Plates

Measured across 100 identical Vietnamese plate images using external dataset `sonnetechnology/license-plate-text-recognition-full` (test Parquet SHA-256 `843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b`) executed in an isolated throwaway Linux container (Debian 12 Bookworm, Tesseract 5.5.0, ONNX Runtime 1.31.0):

##### Set 1: Rows 0..99 of Vietnamese Subset (`^\d{2}[A-Z]`, 100 Images)

| Engine | Exact Match | Exact % | Character Accuracy % | Avg Latency (ms) | Open Source License | Benchmark Status |
|---|---|---|---|---|---|---|
| **Fast-ALPR** (`fast-alpr[onnx]==0.4.0`) | **93 / 100** | **93.00%** | **98.12%** | **32.88 ms** | MIT | **VERIFIED** |
| **RapidOCR** (`rapidocr-onnxruntime==1.2.3`) | 12 / 100 | 12.00% | 30.81% | 460.48 ms | Apache-2.0 | **VERIFIED** |
| **Tesseract OCR** (`pytesseract==0.3.13` + OpenCV pre-processing) | 0 / 100 | 0.00% | 8.79% | 746.87 ms | Apache-2.0 | **VERIFIED** |
| **EasyOCR** | N/A | N/A | N/A | N/A | Apache-2.0 | **UNVERIFIED** |

##### Set 2: Rows 100..199 of Vietnamese Subset (Team Lead Reference Set, 100 Images)

| Engine | Exact Match | Exact % | Character Accuracy % | Avg Latency (ms) | Open Source License | Benchmark Status |
|---|---|---|---|---|---|---|
| **Fast-ALPR** (`fast-alpr[onnx]==0.4.0`) | **96 / 100** | **96.00%** | **99.37%** | **32.71 ms** | MIT | **VERIFIED** |
| **RapidOCR** (`rapidocr-onnxruntime==1.2.3`) | 11 / 100 | 11.00% | 30.27% | 437.31 ms | Apache-2.0 | **VERIFIED** |
| **Tesseract OCR** (`pytesseract==0.3.13` + OpenCV pre-processing) | 0 / 100 | 0.00% | 8.32% | 758.44 ms | Apache-2.0 | **VERIFIED** |
| **EasyOCR** | N/A | N/A | N/A | N/A | Apache-2.0 | **UNVERIFIED** |

##### Key Observations on Alternatives

- **Tesseract OCR**: Without custom deep-learning bounding-box localization, classic Otsu/adaptive thresholding fails completely on raw vehicle photos, yielding 0.00% exact match and < 9% character accuracy, with high latency (> 740 ms). The claim in previous rounds of `< 65%` is corrected by measured empirical reality (`0%` exact, `8.79%` character accuracy).
- **RapidOCR**: General document OCR lacks specific plate bounding box priors; reads vehicle emblems, grille text, and surrounding text, resulting in low accuracy (11-12% exact match) and excessive latency (~450 ms).
- **EasyOCR**: Excluded from benchmark measurement due to PyTorch dependency footprint (~800MB) and marked strictly as **UNVERIFIED**.
- **Ultralytics (YOLOv8/v11) & PyMuPDF**: Strictly rejected due to viral copyleft AGPL-3.0 license.

#### 2.3.3 Operational Reality: High Confidence (99.99%) vs Character Accuracy

Fast-ALPR achieves high-confidence precision:

- In Set 1: 98/100 images had confidence `>= 85.00%`, of which 93 were exact matches (94.90% precision).
- In Set 2: 100/100 images had confidence `>= 85.00%`, of which 96 were exact matches (96.00% precision).

**Critical Security & Operational Warning**:
Incorrect reads can still report **99.99% confidence**. For example:

- In Parquet Row 267: Ground truth `51F-222611` is transcribed as `51F22261` (dropped trailing digit `1`) with confidence `99.9900%`.
- In Parquet Row 217: Ground truth `51F-025.68` is transcribed as `51F07568` with confidence `99.9900%`.

**Consequence for System Architecture**:
Setting `review_status = AUTO` based on `ai_confidence >= 85.00%` (per SRS 4.5.1) is **not an absolute guarantee** of correct license plate transcription. The system architecture must:

1. Retain the scanned image path (`entry_image_url`, `exit_image_url`) on disk for manual reconciliation.
2. Provide operator manual review capabilities (`review_status = NEEDS_REVIEW`).
3. Support customer plate fuzzy/trigram lookup to resolve single-character OCR discrepancies at gate exit.

#### 2.3.4 Architectural Abstraction

- Encapsulated behind `PlateRecognizer` interface (`apps/parking/services/ocr.py`).
- Default implementation: `FastAlprPlateRecognizer` (production & container).
- Test double implementation: `DummyPlateRecognizer` (predictable unit tests and CI offline gates).
- Safety Guard: Initializing `PARKING_OCR_ENGINE == "dummy"` outside `config.settings.test` raises `django.core.exceptions.ImproperlyConfigured`.

### 2.4. Docker Host Volume Safety Invariant (27 Volumes Preservation)

- The development host maintains an immutable baseline of 27 Docker volumes.
- All development and operations teams must adhere to:
  1. **Strict Prohibition**: Never invoke `docker compose down -v` or `docker volume prune`.
  2. **Isolated E2E Testing**: Automated test suites or integration test jobs requiring compose execution must utilize a `tmpfs` override file located **strictly outside the repository** (e.g., `%TEMP%\parking_override.yml`) using Compose specification `!override []` and `!override {}` syntax. This guarantees zero named volume allocation.

## 3. Consequences & References

### 3.1. Positive Consequences

- One-command repeatable full-stack environment (`docker compose up --build`).
- Complete legal compliance under permissive MIT and Apache-2.0 open-source licenses.
- Deterministic container startup with database dependency health checks.
- Zero risk of damaging host Docker volume state or leaking unauthorized network traffic.
- Measured, verifiable OCR performance metrics backed by raw execution logs.

### 3.2. Negative Consequences / Trade-offs

- Building image from scratch requires ~400-600MB download on first run (cached subsequently).
- Fast-ALPR ONNX weights require CPU memory overhead during inference (~150MB RSS).
- High-confidence scans may occasionally misrecognize characters, requiring human verification workflows.

### 3.3. References

- [ADR-0001: Fixed Tech Stack & LTS Roadmap](0001-fixed-tech-stack-and-lts-roadmap.md)
- [ADR-0005: Local PostgreSQL 18 via Docker Compose](0005-local-docker-compose-for-postgresql.md)
- Fast-ALPR Project: <https://github.com/ankandrew/fast-alpr>
- Fast-Plate-OCR Project: <https://github.com/ankandrew/fast-plate-ocr>
- Open-Image-Models Project: <https://github.com/ankandrew/open-image-models>
- ONNX Runtime Project: <https://onnxruntime.ai>
- Dataset `sonnetechnology/license-plate-text-recognition-full`: <https://huggingface.co/datasets/sonnetechnology/license-plate-text-recognition-full>
- Docker Compose Specification (Merge and Override): <https://docs.docker.com/compose/compose-file/13-merge/>

---

## 4. Addendum Round 34: Dual-OCR Ensemble, Review Policy & Recognition Hardening (A1..A6)

### 4.1. Dual-OCR Ensemble & Build-Time SHA-256 Pinning (A1)

To address single-model blind spots identified in Round 33 (e.g., misreading characters with false 99.99% confidence), Round 34 introduces a **Dual-OCR Ensemble Architecture**:

1. **Detection Stage**: License plate bounding box detected once using lightweight `yolo-v9-t-384-license-plates-end2end.onnx` (conf_thresh = 0.40).
2. **Dual Recognition Stage**: On the cropped plate image, two independent neural network architectures execute inference:
   - **Primary Model**: Compact Convolutional Transformer (`cct_xs_v2_global.onnx`, 3-channel RGB, shape 64x128).
   - **Ensemble Model**: Mobile-ViT-v2 (`global_mobile_vit_v2_ocr.onnx`, 1-channel Grayscale, shape 70x140).
3. **Session Optimization**:
   - `intra_op_num_threads = 2`, `inter_op_num_threads = 1` preventing CPU core oversubscription under multi-worker Gunicorn serving.
   - `GraphOptimizationLevel.ORT_ENABLE_ALL`, `enable_cpu_mem_arena = True`, `execution_mode = ORT_SEQUENTIAL`.
4. **Build-Time Verification & Offline Guarantees**:
   All ONNX models and YAML configurations are downloaded at Docker build time into `/app/models/ocr` and verified via pinned SHA-256 checksums (`sha256sum -c`), ensuring deterministic, tamper-proof air-gapped operation (`--network none`).

### 4.2. Review Policy & Deterministic 161/161 Trade-Off Curve (A2 & H7)

Per SRS 4.5.1 and requirements A2 / H7, automated barrier opening (`review_status = "AUTO"`) is permitted **ONLY when all four conditions hold simultaneously**:

1. **Model Agreement**: Both OCR models reach consensus on the normalized plate (`cct_norm == mv2_norm`) or Adaptive Ensemble confidence criteria pass (`cct_min_conf >= 94.0` and `cct_char_confs[0] >= 99.2` and `is_valid_vietnamese_car_plate(cct_norm)`).
2. **High Minimum Character Confidence**: Lowest individual character confidence satisfies `min_char_confidence >= threshold` (calibrated strictly on the tuning split).
3. **Valid Positional Syntax**: Plate adheres strictly to Vietnamese car syntax (`CURRENT | LEGACY | AGENCY` province code `11..99` per Circular 24/2023/TT-BCA, Circular 79/2024/TT-BCA, and Circular 51/2025/TT-BCA).
4. **First-Pass Detection**: Detection succeeded on the initial pass without fallback retry (`fallback_used == False`).

When any condition fails, `review_status = "NEEDS_REVIEW"` with registered `review_reasons` (`MODEL_DISAGREEMENT`, `LOW_CHAR_CONFIDENCE`, `INVALID_FORMAT`, `UNKNOWN_PLATE_PATTERN`, `NO_DETECTION_RETRY`).

#### Empirical Trade-Off Curve Across 9 Thresholds (322 Vietnamese Plate Images — H7)

Dataset `sonnetechnology/license-plate-text-recognition-full` (`322` rows, test Parquet SHA-256 `843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b`) partitioned deterministically (`even = row_idx % 2 == 0`, `odd = row_idx % 2 == 1`):

- **Tuning Split**: Even indices (`0, 2, ..., 320`) = **161 rows**.
- **Test Split**: Odd indices (`1, 3, ..., 321`) = **161 rows** (held out, evaluated once at locked rule `threshold = 85.0%`).

##### Tuning Split (161 Even Rows — Hyperparameter Calibration)

| Threshold (%) | AUTO Count / Total | AUTO Coverage % | NEEDS_REVIEW Count | Wrong in AUTO | Wrong % in AUTO |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 70.0% | 152 / 161 | 94.41% | 9 | 5 | 3.29% |
| 75.0% | 152 / 161 | 94.41% | 9 | 5 | 3.29% |
| 80.0% | 150 / 161 | 93.17% | 11 | 4 | 2.67% |
| 82.0% | 150 / 161 | 93.17% | 11 | 4 | 2.67% |
| **85.0%** | **150 / 161** | **93.17%** | **11** | **4** | **2.67%** |
| 88.0% | 150 / 161 | 93.17% | 11 | 4 | 2.67% |
| 90.0% | 149 / 161 | 92.55% | 12 | 4 | 2.68% |
| 92.0% | 149 / 161 | 92.55% | 12 | 4 | 2.68% |
| 95.0% | 146 / 161 | 90.68% | 15 | 4 | 2.74% |

##### Test Split (161 Odd Rows — Unseen Evaluation at Locked $\tau = 85.0\%$)

| Threshold (%) | AUTO Count / Total | AUTO Coverage % | NEEDS_REVIEW Count | Wrong in AUTO | Wrong % in AUTO | Acceptance Target | Result |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 70.0% | 155 / 161 | 96.27% | 6 | 1 | 0.65% | Wrong $\le 1.0\%$, Cov $\ge 93\%$ | PASS |
| 75.0% | 155 / 161 | 96.27% | 6 | 1 | 0.65% | Wrong $\le 1.0\%$, Cov $\ge 93\%$ | PASS |
| 80.0% | 153 / 161 | 95.03% | 8 | 1 | 0.65% | Wrong $\le 1.0\%$, Cov $\ge 93\%$ | PASS |
| 82.0% | 153 / 161 | 95.03% | 8 | 1 | 0.65% | Wrong $\le 1.0\%$, Cov $\ge 93\%$ | PASS |
| **85.0%** | **153 / 161** | **95.03%** | **8** | **1** | **0.65%** | **Wrong $\le 1.0\%$, Cov $\ge 93\%$** | **PASS (LOCKED)** |
| 88.0% | 153 / 161 | 95.03% | 8 | 1 | 0.65% | Wrong $\le 1.0\%$, Cov $\ge 93\%$ | PASS |
| 90.0% | 153 / 161 | 95.03% | 8 | 1 | 0.65% | Wrong $\le 1.0\%$, Cov $\ge 93\%$ | PASS |
| 92.0% | 153 / 161 | 95.03% | 8 | 1 | 0.65% | Wrong $\le 1.0\%$, Cov $\ge 93\%$ | PASS |
| 95.0% | 151 / 161 | 93.79% | 10 | 1 | 0.66% | Wrong $\le 1.0\%$, Cov $\ge 93\%$ | PASS |

*Conclusion*: Locked at `threshold = 85.0%` from the tuning split, the unseen odd test split achieves **0.65% Wrong in AUTO** (`1 / 153 <= 1.0%`) and **95.03% AUTO coverage** (`153 / 161 >= 93.0%`). Note: Dataset row `102` (Parquet index `267`, labeled `51F-222611` with 6 serial digits) is a dirty 9-character label in the external dataset; the OCR models transcribe the actual 8-character plate `51F22261` on the vehicle photo.

### 4.3. Vietnamese Car Plate Regulations (`11..99`) & Structured Confusable Corrections (H2 & H6)

Per Circular 24/2023/TT-BCA (effective 15 Aug 2023), Circular 79/2024/TT-BCA (effective 1 Jan 2025), and Circular 51/2025/TT-BCA Appendix 02 (effective 1 Jul 2025 following the national administrative merger into 34 provinces/cities), `apps/parking/data/vn_plate_rules.py` classifies all `89` two-digit codes `11..99`:

- **`CURRENT` (`50` codes)**: Active provincial/municipal codes for the 34 post-merger provinces/cities (including multi-code cities such as Hanoi `29..32, 40`, Ho Chi Minh City `41, 50..59`, Hai Phong `15, 16`, and Dong Nai `39, 60`).
- **`LEGACY` (`30` codes)**: Pre-merger provincial codes (`17, 18, 21, 23, 28, 33, 34, 48, 61, 62, 63, 68, 71, 72, 73, 77, 78, 82, 83, 84, 85, 86, 88, 90, 92, 93, 94, 95, 97, 98`) that remain legally valid on existing circulating vehicles.
- **`AGENCY` (`1` code)**: Code `80` (central government agencies issued by the Traffic Police Department - Cục CSGT).
- **`NEVER_ISSUED` (`8` codes)**: Codes `13, 42, 44, 45, 46, 87, 91, 96` (national reserve codes never issued). Total valid car codes (`CURRENT | LEGACY | AGENCY`) = **`81`**, rejected (`NEVER_ISSUED`) = **`8`**.
- **Car-Only Grammar (`OQ-86`, `TL-51`, `PROP-4.5.1-P16`)**:
  - Motorbike patterns (`^\d{2}[A-Z]\d\d{4,5}$` such as `29-B1 123.45`) are removed from the car validator and rejected with `PROP-4.5.1-P16`.
  - Syntax classification distinguishes **`INVALID_FORMAT`** (`< 7` or `> 9` chars, non-alphanumeric) from **`UNKNOWN_PLATE_PATTERN`** (`7..9` alphanumeric characters with a `NEVER_ISSUED` province code or unrecognized series).
- **Structured Confusable Corrections (`H6`)**:
  - `POST /api/v1/parking/plate-scans/` returns `plate_raw`, `plate_final`, `best_candidate` (synced to `plate_final`), and `corrections: [{position, from, to, rule, reason}]`.
  - Clean 322-row dataset benchmark: **`321 / 321 (100.00%)`** valid-label rows untouched, **`0` broken correct reads** (`broken_correct_reads = 0`); repaired `5DZ1630 -> 50Z1630` on row `109`.
  - Synthetic confusable-character noise benchmark: **`104 / 104 (100.00%)`** corrupted plates repaired back to ground truth, **`0` broken reads**.

### 4.4. Detection Fallback (A4)

When initial YOLOv9-t 384 detection yields 0 candidates, an immediate fallback retry is triggered with `conf_thresh = 0.02`:

- **Recovery Rate**: Recovered **100% of detection misses** (rows `249`, `721`, `855`), transcribing `51A72110` and `51G10209` with 100% character accuracy.
- **Zero Latency Penalty**: Fallback logic executes conditionally (`if not detections:`), adding **0.00 ms** overhead for the 98.7% of scans succeeding on the first pass.

### 4.5. Trigram Similarity Suggestions (A5)

When a scanned plate triggers `review_status = "NEEDS_REVIEW"` or is not found in the vehicle catalog, up to 3 candidate plates within edit distance $\le 1$ or `pg_trgm` similarity $\ge 0.5$ are queried via `idx_vehicle_plate_trgm` in a single indexed PostgreSQL query:

- **PostgreSQL Index Verification (`EXPLAIN (ANALYZE, BUFFERS)` on `vehicle`)**:
  - Plan: `Bitmap Heap Scan on vehicle` -> `Bitmap Index Scan on idx_vehicle_plate_trgm` (`Index Cond: ((license_plate_norm)::text % '43K86059'::text)`).
  - Measured Execution Time: `0.294 ms` (`Buffers: shared hit=31`).
- **Integrity Boundary**: Suggestions are strictly advisory (`suggestions: list[str]`) and never automatically overwrite database values.

### 4.6. Multi-Frame Consensus Architecture & Synthetic Simulation (A6)

For barrier camera streams capturing 3 to 5 frames per vehicle approach, confidence-weighted character voting (`aggregate_multi_frame_scans`) combines per-character Softmax probabilities across frames, applies `correct_plate_characters_detailed`, and flags `NEEDS_REVIEW` (`MARGINAL_CONSENSUS_MARGIN`) when top-two margin is `< 20%`.

### 4.7. Open-Source Licensing Compliance & Permissive Status

All components utilized in the plate recognition and OCR pipeline are verified under permissive open-source licenses:

| Component | Repository / Author | License | Copyleft Risk | Commercial Permissibility |
|---|---|---|---|---|
| **fast-alpr** | [ankandrew/fast-alpr](https://github.com/ankandrew/fast-alpr) | **MIT** | None | Approved |
| **fast-plate-ocr** | [ankandrew/fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr) | **MIT** | None | Approved |
| **open-image-models** | [ankandrew/open-image-models](https://github.com/ankandrew/open-image-models) | **MIT** | None | Approved |
| **onnxruntime** | [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) | **MIT** | None | Approved |
| **OpenCV (headless)** | opencv-python-headless | **Apache-2.0** | None | Approved |

#### Verbatim MIT License Notice (Citing ankandrew)

```text
MIT License

Copyright (c) 2024 ankandrew

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

### 4.8. High-Concurrency Production Serving & Anti-Restart-Storm Architecture (H3)

#### Problem Analysis: Worker Restart Storm

At concurrency `64`, `max_requests = 1000` caused 23 Gunicorn worker restarts within 2 minutes. Because each restarted worker re-initializes ONNX Runtime sessions (`~368 ms`), frequent restarts under heavy load caused `RemoteDisconnected` / `502` client errors and latency spikes.

#### Architectural Decision & 180-Second Soak Test Verification

1. **Default Zero Max Requests**: `GUNICORN_MAX_REQUESTS = 0` by default in `docker/gunicorn.conf.py`, `docker-compose.yml`, and `.env.example`.
2. **RSS Memory Watchdog**: In `docker/gunicorn.conf.py`, `post_request` samples resident set size (`resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`) every 100 requests and sets `worker.alive = False` only if RSS exceeds `GUNICORN_MEMORY_LIMIT_MB` (default `1536 MB`).
3. **Measured 180-Second Soak Test at Concurrency `64`**:
   - **`lookup` (`c = 64`, `180.3 s`)**: `49,668` requests, **`275.4 RPS`**, `p50 = 255.2 ms`, `p95 = 323.8 ms`, `p99 = 355.9 ms`, `200:49668`, **`errors = 0`**.
   - **`check-in+out cycle` (`c = 64`, `180.6 s`)**: `18,199` cycles (`36,398` HTTP requests), **`100.8 RPS`**, `p50 = 673.2 ms`, `p95 = 846.1 ms`, `p99 = 911.4 ms`, `200:18199`, **`errors = 0`**.
   - **Worker Stability (`86,066` HTTP requests)**: Worker PIDs `18, 19, 20, 21` remained identical before and after (`0` restarts), with stable RSS `258,668 kB .. 259,332 kB` (`~253 MB`) and `pg_stat_activity = 17 / 100` across all `5 s` samples.

### 4.9. End-to-End Scan Latency Profiling Across Image Resolutions (H4a)

Measured inside `parking_r35-web-1` with `time.process_time()` (CPU-ms) and `time.perf_counter()` (Wall-ms) on Python `3.14.7` + ONNX Runtime `1.24.4`:

| Pipeline Stage | 640x480 (CPU / Wall ms) | 1080p FHD (CPU / Wall ms) | 12MP UHD (CPU / Wall ms) | Architectural Assessment |
| :--- | :--- | :--- | :--- | :--- |
| `multipart_parse` | 0.00 / 0.01 | 0.00 / 0.03 | 0.00 / 0.15 | Sub-millisecond byte parsing in RAM. |
| `validate_decode` | 0.00 / 1.49 | 15.62 / 10.81 | 46.88 / 65.78 | Pillow JPEG decode + LANCZOS downscale to `<= 1280px`. |
| `bgr_conversion` | 0.00 / 0.29 | 0.00 / 0.77 | 0.00 / 5.41 | SIMD-accelerated OpenCV RGB-to-BGR conversion. |
| `detector_primary` | 46.88 / 38.65 | 31.25 / 42.07 | 62.50 / 53.13 | YOLOv9-t `384x384` ONNX detection (`~73-84%` of inference time). |
| `crop_margin` | 0.00 / 0.01 | 0.00 / 0.01 | 0.00 / 0.02 | `4px` margin crop with bounds clamping. |
| `ocr_model_1_cct` | 0.00 / 4.59 | 15.62 / 4.30 | 0.00 / 6.78 | CCT-xs-v2 recognition on cropped plate (`~4.3 ms`). |
| `ocr_model_2_mv2` | 0.00 / 4.30 | 0.00 / 4.27 | 15.62 / 9.54 | Mobile-ViT-v2 fallback OCR (`0.00 ms` when skipped in Adaptive mode). |
| `review_policy` | 0.00 / 0.09 | 0.00 / 0.02 | 0.00 / 0.02 | In-memory positional grammar & threshold validation (`< 0.1 ms`). |
| `db_queries` | 0.00 / 1.11 | 0.00 / 1.05 | 0.00 / 1.15 | Indexed vehicle + open-session lookup (`4` queries total). |
| `serializer_response`| 0.00 / 0.04 | 0.00 / 0.03 | 0.00 / 0.06 | DRF JSON response serialization. |
| `file_write` | 0.00 / 1.12 | 0.00 / 0.85 | 0.00 / 1.22 | Media snapshot persistence (`parking_scans/YYYY/MM/DD/`). |
| **TOTAL** | **46.88 / 51.71** | **62.50 / 64.22** | **125.00 / 143.24** | **Single-worker CPU floor is ~47-63 CPU-ms per scan.** |

### 4.10. ONNX Runtime Threading Matrix & Adaptive Ensemble (H4b, H4c, H4d)

#### Official ONNX Runtime Threading Citation & Configuration

Per official ONNX Runtime documentation ([Thread management](https://onnxruntime.ai/docs/performance/tune-performance/threading.html), accessed 2026-10-19):

> "Controls whether additional INTRA or INTER threads spin waiting for work."

In session configuration:

```python
sess_opt.AddConfigEntry("session.intra_op.allow_spinning", "0")
```

Setting `ONNX_INTRA_OP_THREADS = 1`, `ONNX_INTER_OP_THREADS = 1`, and `ONNX_ALLOW_SPINNING = 0` (`session.intra_op.allow_spinning = "0"`) eliminates spin-wait CPU contention across concurrent Gunicorn workers (`workers = 4`, `threads = 6`, `OCRConcurrencyGate = 4`):

| Config (`W_T_IO_Spin_Gate`) | Scan 640x480 (`c=32` RPS / p95) | Scan 640x480 (`c=64` RPS / p95) | Scan 1080p (`c=32` RPS / p95) | Scan 1080p (`c=64` RPS / p95) |
| :--- | :---: | :---: | :---: | :---: |
| `R34_Baseline_W4_T8_IO2_Spin1_G2` | 47.5 / 1019.8 ms | 51.4 / 1992.0 ms | 38.4 / 1514.4 ms | 43.6 / 2406.6 ms |
| `W4_T8_IO1_Spin0_G2` | 67.3 / 791.9 ms | 69.9 / 1281.0 ms | 56.6 / 862.1 ms | 58.5 / 1906.4 ms |
| `W2_T4_IO1_Spin0_G4` | 55.1 / 852.1 ms | 55.6 / 1602.5 ms | 46.6 / 984.9 ms | 48.5 / 1848.8 ms |
| `W3_T4_IO1_Spin0_G4` | 65.5 / 728.0 ms | 65.8 / 1272.2 ms | 53.9 / 860.9 ms | 57.0 / 1502.4 ms |
| `W6_T4_IO1_Spin0_G2` | 65.8 / 767.0 ms | 70.0 / 1364.3 ms | 55.3 / 889.8 ms | 58.7 / 1495.5 ms |
| `W4_T4_IO1_Spin0_G8` | 66.8 / 763.9 ms | 69.7 / 1185.0 ms | 56.9 / 906.6 ms | 58.3 / 1551.8 ms |
| **`Optimal_W4_T4_IO1_Spin0_G4`** | **70.2 / 711.7 ms** | **69.7 / 1139.1 ms** | **60.1 / 887.2 ms** | **59.6 / 1416.7 ms** |

#### Full vs. Adaptive Ensemble on All 322 Vietnamese Plates (H4c)

- **Full Ensemble (`PARKING_OCR_ADAPTIVE_ENSEMBLE=False`)**: `exact_final = 309 / 322 (95.96%)`, `m2_ran = 321 / 322`, `auto = 295 (91.61%)`, `wrong_in_auto = 5 (1.69%)`, `mean_ms = 46.17 ms`, `p50_ms = 45.12 ms`, `p95_ms = 51.66 ms`.
- **Adaptive Ensemble (`PARKING_OCR_ADAPTIVE_ENSEMBLE=True`)**: `exact_final = 309 / 322 (95.96%)`, `m2_ran = 19 / 322 (5.90%)`, `auto = 303 (94.10%)`, `wrong_in_auto = 5 (1.65%)`, `mean_ms = 42.07 ms`, `p50_ms = 41.12 ms`, `p95_ms = 47.62 ms`.
- **Crop Margin & Model Path Resolution (H4d)**: `PARKING_OCR_CROP_MARGIN = 4` expands bounding boxes by 4px with clamping; `settings.PARKING_OCR_MODELS_DIR` resolves the baked `/app/models/ocr` directory and raises a clear `FileNotFoundError` if missing.

### 4.11. Database Query Ceiling Governance & `sessions list` 4.26x Speedup (H5)

#### Enforced Query Budgets (`django_assert_max_num_queries` in `tests/parking/test_query_budgets.py`)

| Operation / Endpoint | Ceiling Budget | Measured Queries (`CaptureQueriesContext`) | Optimization Strategy |
| :--- | :---: | :---: | :--- |
| **Plate Scan** (`POST /api/v1/parking/plate-scans/`) | **$\le 5$** | **4** | Session auth (`2`) + single `Vehicle.objects.select_related('vehicle_type', 'customer')` (`1`) + open session (`1`). |
| **Vehicle Lookup** (`GET /api/v1/parking/vehicles/lookup/`) | **$\le 5$** | **3** | Session auth (`2`) + `Subquery` annotations for `has_active_ticket` and `has_open_session` (`1`). |
| **Vehicle Search** (`GET /api/v1/parking/vehicles/search/`) | **$\le 5$** | **5** | Session auth (`2`) + `Exists` annotations (`has_active_ticket`, `is_currently_parked`) + `Prefetch` (`3`). |
| **Check-in** (`POST /api/v1/parking/sessions/check-in/`) | **$\le 10$** | **10** | Session auth (`2`) + `select_for_update` slot/gate/vehicle checks + `INSERT` session + `refresh_from_db`. |
| **Check-out** (`POST /api/v1/parking/sessions/{id}/check-out/`) | **$\le 9$** | **7** | Session auth (`2`) + `select_related('vehicle__vehicle_type')` on locked session + ticket/fee/payment update. |

#### `sessions list` 4.26x Speedup (`267.1 RPS` Host / `285.9 RPS` In-Network at `c = 32`)

By replacing full-table `COUNT(*)` pagination with a Slice-Plus-One check (`page_size + 1` rows in `StandardResultsSetPagination`), pruning unused `select_related` joins, and projecting only the 22 columns required by `SessionListItemSerializer` via `.only(...)`, `GET /api/v1/parking/sessions/` at `c = 32` improved from Round 33's `62.7 RPS` (`p95 = 554.8 ms`) to **`267.1 RPS` (`4.26x`, `p50 = 115.7 ms`, `p95 = 196.9 ms <= 277 ms`)** from host and **`285.9 RPS` (`4.56x`, `p50 = 96.0 ms`, `p95 = 203.3 ms`)** inside the Compose network.

### 4.12. Security Threat Model for Image Upload & OCR Pipeline (Engineering Standard 7)

1. **Decompression bomb**: Mitigated by setting Pillow `Image.MAX_IMAGE_PIXELS = 25_000_000` and rejecting any image with width or height `> 6000 px` (`MAX_IMAGE_DIMENSION`) before full raster decoding.
2. **Polyglot file**: Mitigated by inspecting the first 12 magic bytes (`JPEG`, `PNG`, `WEBP` signatures only), running `Image.verify()`, applying `ImageOps.exif_transpose()`, and re-encoding in memory to a clean RGB JPEG buffer (stripping all metadata/polyglot payloads).
3. **Path traversal**: Mitigated by discarding the client filename (`uploaded_file.name`) during storage and generating a cryptographically random `uuid.uuid4().hex + ".jpg"` path strictly inside `MEDIA_ROOT/parking_scans/YYYY/MM/DD/`.
4. **Disk fill**: Mitigated by enforcing `DATA_UPLOAD_MAX_MEMORY_SIZE = 5 MB`, `MAX_UPLOAD_SIZE_BYTES = 5 MB`, downscaling images to `<= 1280 px` (`JPEG quality=85`, `~40-90 KB`), and providing the `purge_orphan_scans` command (`--dry-run` default, 24h grace period).
5. **Slowloris / CPU DoS**: Mitigated by Gunicorn `timeout = 30s`, `keepalive = 5s`, and the per-worker `OCRConcurrencyGate` semaphore (`limit = 4`, `timeout = 2.0s`) which sheds excess concurrent OCR requests with HTTP `503 Service Unavailable`, `Retry-After: 3`, and code `PROP-4.5.1-P15`.

### 4.13. Operations & Incident Runbook Integration (J7.d, Standard 6)

For day-to-day operations, on-call incident response, and runtime telemetry, see the authoritative runbook embedded in the project documentation:

- **Authoritative Operations Runbook**: Refer to [`README.md §3.11: Production Operations Runbook & Incident Playbooks`](../../README.md#step-11-production-operations-runbook--incident-playbooks-j7d-standard-6).
- **Core Operational Invariants**:
  - **Zero Volume Loss**: The host Docker volume count is strictly pinned to `27`. Never run `docker compose down -v` or `docker volume prune`.
  - **Concurrency Back-Pressure**: `GUNICORN_THREADS` (`6`) strictly exceeds `PARKING_OCR_CONCURRENCY_LIMIT` (`4`) to ensure worker threads can queue and trigger HTTP `503 Service Unavailable` with `Retry-After: 3` (`PROP-4.5.1-P15`) without dropping socket connections.
  - **Memory RSS Watchdog**: Gunicorn `post_request` hook monitors worker RSS against `GUNICORN_MEMORY_LIMIT_MB` (`1536 MB`) and initiates a graceful recycle when exceeded.
  - **Structured Observability**: Every scan request emits a single structured JSON line with microsecond-level stage timings (`decode`, `detect`, `ocr1`, `ocr2`, `db`, `write`) and privacy-compliant masked license plate numbers (`51F***81`).

### 4.14. Addendum Round 38: 10-Run Benchmark Distribution, Rounding Diff & Honest Reporting (L4)

#### 1. 10-Run Benchmark AUTO Count Distribution Across 8 Configurations

To investigate the historical 301-vs-302 `AUTO` count variation, an exhaustive empirical benchmark of 10 runs per configuration (80 total runs across 322 external Vietnamese dataset images, Parquet SHA-256 `843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b`) was executed in an isolated environment across all combinations of ONNX intra-op threading (1 vs 2), serving workers (1 vs 4), and decimal rounding (`round(conf, 4)` vs unrounded float):

| Config ID | ONNX Intra Threads | Serving Workers | 4-Decimal Rounding | Runs | Measured AUTO Counts | Mean AUTO | Min / Max AUTO | Duration Avg (s) | 302 Reproduced? |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CFG-1** | 1 | 1 | False | 10 | `[301, 301, 301, 301, 301, 301, 301, 301, 301, 301]` | 301.0 | 301 / 301 | 12.80s | **NO (0/10)** |
| **CFG-2** | 1 | 1 | True  | 10 | `[301, 301, 301, 301, 301, 301, 301, 301, 301, 301]` | 301.0 | 301 / 301 | 12.83s | **NO (0/10)** |
| **CFG-3** | 1 | 4 | False | 10 | `[301, 301, 301, 301, 301, 301, 301, 301, 301, 301]` | 301.0 | 301 / 301 | 3.97s  | **NO (0/10)** |
| **CFG-4** | 1 | 4 | True  | 10 | `[301, 301, 301, 301, 301, 301, 301, 301, 301, 301]` | 301.0 | 301 / 301 | 4.26s  | **NO (0/10)** |
| **CFG-5** | 2 | 1 | False | 10 | `[301, 301, 301, 301, 301, 301, 301, 301, 301, 301]` | 301.0 | 301 / 301 | 8.88s  | **NO (0/10)** |
| **CFG-6** | 2 | 1 | True  | 10 | `[301, 301, 301, 301, 301, 301, 301, 301, 301, 301]` | 301.0 | 301 / 301 | 8.81s  | **NO (0/10)** |
| **CFG-7** | 2 | 4 | False | 10 | `[301, 301, 301, 301, 301, 301, 301, 301, 301, 301]` | 301.0 | 301 / 301 | 3.55s  | **NO (0/10)** |
| **CFG-8** | 2 | 4 | True  | 10 | `[301, 301, 301, 301, 301, 301, 301, 301, 301, 301]` | 301.0 | 301 / 301 | 3.83s  | **NO (0/10)** |

**Key Empirical Finding & Deletion of Float32 Theory**:
In all 80 runs across all 8 configurations, the AUTO count is deterministically and invariant **301 / 322 (93.48%)**. Count `302` was **NEVER** reproduced in any run (`0 / 80`). The hypothesis attributing `301-vs-302` to IEEE 754 float32 non-associative arithmetic or SIMD instruction differences is marked **`UNVERIFIED`** and removed from technical claims.

#### 2. Root Cause of Historical 301 vs 302 Discrepancy

Ablation testing isolating each review signal revealed the true root cause:

- **With `plate_aspect_ratio` validation**: `AUTO` = **301**. Row `236` (`51A-691.72`, ground-truth cropped bounding box has aspect ratio `w/h = 1.05 - 1.25 < 1.30`) triggers `ReviewReasonCode.IRREGULAR_ASPECT_RATIO` and is routed to `NEEDS_REVIEW`.
- **Without `plate_aspect_ratio` validation** (omitted in early test scripts): `AUTO` = **302**. Row `236` passed all other checks (model agreement = True, min_char_conf = 100.0%, syntax = VALID) and was admitted to `AUTO`.
- *Conclusion*: The 301 vs 302 difference was caused by whether the secondary geometric signal `plate_aspect_ratio` was evaluated, not by numerical float32 precision.

#### 3. 322-Row Rounding Diff Analysis: Harmless Quantization Proof

A row-by-row comparative evaluation of review decisions across all 322 dataset rows comparing raw floating-point confidence vs `round(conf, 4)` quantization confirmed:

- **Identical Decisions**: **`322 / 322 (100.00%)`**.
- **Decision Divergence**: **`0 / 322 (0.00%)`**.
- **Review Reasons Diff**: **`0 / 322 (0.00%)`**.
- *Conclusion*: 4-decimal rounding (`round(conf, 4)`) is **100% harmless**, preserves identical gate decisions, and provides clean serializable values for logging and API responses.

#### 4. Honest Three-Number Reporting & Safety Margins

Per Milestone 3 integrity requirements, the three `wrong-in-AUTO` figures are stated together transparently:

1. **Point Estimate (Clean Benchmark)**: **`0.997%`** (`3 / 301`), excluding external dataset dirty label at Row 102 (labeled `51F-222611` with 9 characters, vehicle photo is 8-character `51F22261`). The 3 real joint misreads are Row 76 (`51F02568 -> 51F07568`), Row 200 (`60A35937 -> 60A35981`), and Row 279 (`51A69122 -> 51A69172`).
2. **Point Estimate (Conservative / Full Denominator)**: **`1.33%`** (`4 / 301`), including Row 102 as an error.
3. **95% Confidence Interval Upper Bound**: **`2.89%`** (Wilson score: `2.889%`, Clopper-Pearson exact binomial: `2.885%`).

#### 5. Operational Mitigations for Zero-Safety-Margin Risk

Because the 95% confidence upper bound (`2.89%`) exceeds the 1.0% operational target, threshold tuning alone cannot eliminate joint misreads where both models agree with 100% confidence. Safety is guaranteed by operational mitigation:

- **Raw Image Retention**: The uncompressed captured image is persisted on disk (`image_url`) for every scan request and referenced in the audit trail.
- **Entry/Exit Plate Reconciliation**: At parking checkout, the exit plate read is compared against the entry session plate. If edit distance is 1 (such as `51F02568` vs `51F07568`), automated barrier opening is inhibited, presenting side-by-side entry/exit photos to the operator for mandatory manual confirmation.
- **Threshold Invariance**: Threshold remains locked at `PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD = 90.0%`. Nested 5-fold cross-validation on K-1 folds selects 90.0% / 92.0%, proving no threshold modification is warranted without degrading coverage below 93%.

#### 6. Third-Party Dataset Attribution & Licensing (CC-BY-4.0)

Per Milestone 4 / Requirement L5, external benchmark dataset attribution is explicitly stated:

- **Dataset**: `sonnetechnology/license-plate-text-recognition-full`
- **Author / Publisher**: `Sonnetechnology`
- **Repository Link**: [Hugging Face Dataset: sonnetechnology/license-plate-text-recognition-full](https://huggingface.co/datasets/sonnetechnology/license-plate-text-recognition-full)
- **License**: [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/)
