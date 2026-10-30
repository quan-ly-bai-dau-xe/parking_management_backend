# Enterprise Model Card: Compact Convolutional Transformer for Vietnamese ALPR (CCT-XS)

**Document Version**: 1.0.0 (Production Baseline & Candidate Evaluation)  
**Standard**: Mitchell et al. (2019, "Model Cards for Model Reporting")  
**Primary Architecture**: Compact Convolutional Transformer (CCT-XS)  
**Deployment Runtime**: ONNX Runtime 1.31.0 (CPU-optimized, intra_op_num_threads = 1, inter_op_num_threads = 1)  
**Target Repository**: `parking_management_backend` (`apps/parking/services/ocr.py`)  
**Status**: APPROVED BASELINE SPECIFICATION  

---

## 1. Model Details

### 1.1. Basic Information

- **Model Name**: Compact Convolutional Transformer Extra-Small v2 (`cct_xs_v2_global.onnx`).
- **Model Developer**: ANK Andrew (`ankandrew/fast-plate-ocr` project, licensed under MIT).
- **Fine-Tuning Entity**: Parking Management Engineering Team (OCR Fine-Tuning Pipeline).
- **Model Release Date**: Baseline verified October 2026; candidate fine-tuning targeted for Phase 1 release.
- **Training Paradigm**: Fine-tuning / transfer learning from published global baseline weights (`cct_xs_v2_global.keras`). Zero training from scratch.
- **Model Format**: Open Neural Network Exchange (ONNX) version 1.14+, opset 17.
- **Weight Checksum**: SHA-256 `8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44`.
- **Config Checksum**: SHA-256 `0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6`.

### 1.2. Neural Network Architecture Specification

CCT-XS replaces traditional heavy CNN backbones and recurrent LSTM/CTC decoders with a lightweight sequence-to-sequence Vision Transformer combining convolutional tokenization with sequence pooling.

```text
[Input: uint8 RGB Crop (64 x 128 x 3)]
                  │
                  ▼
   [Rescaling: x / 255.0 -> float32]
                  │
                  ▼
   ┌────────────────────────────────────────────────────────┐
   │ Convolutional Tokenizer (7 blocks):                   │
   │ - Conv2D(32, 3x3, SiLU) -> MaxBlurPooling2D(pool=2)    │
   │ - Conv2D(48, 3x3, SiLU) -> Conv2D(64, 3x3, SiLU)       │
   │ - MaxBlurPooling2D(pool=2)                             │
   │ - Conv2D(80, 3x3, SiLU) -> Conv2D(96, 3x3, SiLU)       │
   │ - Patch Size = 2, Patch MLP (dim=96, dropout=0.15)     │
   │ - Positional Embedding = True                          │
   └────────────────────────────────────────────────────────┘
                  │
                  ▼
   ┌────────────────────────────────────────────────────────┐
   │ Transformer Encoder (3 layers):                        │
   │ - 2 Attention Heads, Projection Dim = 96               │
   │ - Attention Dropout = 0.1, MLP Dropout = 0.15          │
   │ - Stochastic Depth = 0.1                               │
   │ - Normalization: Dynamic Token Normalization (DyT)     │
   └────────────────────────────────────────────────────────┘
                  │
                  ▼
   ┌────────────────────────────────────────────────────────┐
   │ Sequence-to-Sequence Classifier Head:                  │
   │ - Token Reducer (2 heads, query residual, norm)        │
   │ - 3 Post-token Reducer Layers                          │
   │ - Linear Dense Projection -> max_plate_slots = 10      │
   └────────────────────────────────────────────────────────┘
                  │
                  ▼
   [Output Logits: (Batch, 10, 37)]
```

### 1.3. Key Parameters & Input/Output Tensor Contract

| Parameter | Value / Description |
|---|---|
| **Total Parameters** | **791,700** (174 initializers: 162 float32 tensors with 791,673 params, 4 int32, 8 int64) |
| **Model Size on Disk** | **3,344,292 bytes** (~3.34 MB, original float32 ONNX) / **2,377,330 bytes** (~2.38 MB, single-head export with onnxslim from `export_model.py`) |
| **Input Tensor Shape** | `[Batch, 64, 128, 3]` (dynamic batch, uint8 RGB) |
| **Input Color Order** | RGB (normalized internally via `scale = 0.00392156862745098`) |
| **Output Tensor Name** | `'plate'` |
| **Output Tensor Shape** | `[Batch, 10, 37]` (probabilities or unscaled logits) |
| **Max Plate Slots** | `10` characters |
| **Alphabet (37 Chars)** | `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_` (Pad char `_`) |

---

## 2. Intended Use & Deployment Scope

### 2.1. Primary Intended Applications

- **Target Vehicle Domain**: Standard civilian passenger cars bearing 1-line rectangular license plates conforming to Circular 24/2023/TT-BCA, Circular 79/2024/TT-BCA, and Circular 51/2025/TT-BCA single-letter series (`^\d{2}[A-Z]\d{4,5}$`).
- **Automated Barrier Access Control**: Deployed in commercial parking garage entry and exit lanes for automated license plate logging, ticket validation, and automatic barrier lifting.
- **Backend Service Integration**: Encapsulated behind the `PlateRecognizer` interface (`apps/parking/services/ocr.py`) as the primary recognizer inside `FastAlprPlateRecognizer`.
- **Ensemble Pairing**: Paired with secondary recognizer `global_mobile_vit_v2_ocr.onnx` (Grayscale 70x140) to execute multi-signal agreement verification.
- **Automated Gate Opening Criteria (`review_status = AUTO`)**:
  1. Primary and ensemble models agree on normalized plate string (`cct_norm == mv2_norm`).
  2. Lowest individual character confidence exceeds threshold ($\tau = 90.0\%$).
  3. Syntax complies with Circular 24/2023/TT-BCA, Circular 79/2024/TT-BCA, and Circular 51/2025/TT-BCA.
  4. Detection succeeded without low-confidence fallback retry.
  5. Geometric aspect ratio ($1.3 \le w/h \le 6.0$) and Laplacian sharpness ($\ge 30.0$) pass validation.

### 2.2. Out-of-Scope & Prohibited Operational Modes

- **General Scope Boundary**: This model does NOT claim universal recognition across all Vietnamese vehicle registrations. The initial release is strictly calibrated for single-line civilian automobiles.
- **Specific Out-of-Scope Series & Routing**:
  1. **Military Vehicle Plates**: Plates featuring 2 uppercase series letters followed by 4 or 5 digits (e.g., `QA`, `TC`, `TM`) are OUT OF SCOPE. In production, `classify_plate_syntax()` flags them as `UNKNOWN_PLATE_PATTERN`, enforcing `review_status = "NEEDS_REVIEW"`.
  2. **Central Agency Plates (Code 80)**: Central government and national police registrations (`80A`, `80B`, `80CD`, `80NG`) are OUT OF SCOPE for unattended gate opening and must be manually verified by human staff (`NEEDS_REVIEW`).
  3. **Diplomatic, International & Specialized Series**: Series `NG`, `QT`, `CV`, `NN`, `LD`, `DA`, `KT`, `CD`, `TD` are OUT OF SCOPE. Model accuracy on these series is unmeasured, and detector bounding-box reliability is designated as `UNVERIFIED`.
  4. **Motorbike & Two-Wheeler Registrations**: 2-line stacked motorcycle plates (`^\d{2}[A-Z]\d`) possess differing font proportions and aspect ratios. They are strictly classified as `INVALID_FORMAT` by car parking rules and routed to `NEEDS_REVIEW`.
  5. **High-Speed Free-Flow Tolling**: Calibrated strictly for barrier-controlled gate lanes ($\le 30\text{ km/h}$). Free-flow open-road capture causes severe motion smear exceeding model design bounds.
- **Scope Expansion Governance**: Expanding model recognition capabilities to out-of-scope series mandates lawful acquisition of real-world representative image samples compliant with Decree 13/2023/ND-CP, subject to an independent Project Owner determination.

---

## 3. Factors, Slices & Environmental Conditions

The model's operational reliability is evaluated across 5 principal factor dimensions:

### 3.1. Factor 1: Administrative Province Codes (Circular 51/2025/TT-BCA)

- **CURRENT Codes (50 codes)**: Post-merger administrative divisions (e.g., Ho Chi Minh City `41, 50..59`, Hanoi `29..32, 40`, Hai Phong `15, 16`, Dong Nai `39, 60`).
- **LEGACY Codes (30 codes)**: Pre-merger valid circulating provincial codes (e.g., `17, 18, 61, 62, 72, 77, 98`).
- **AGENCY Code (1 code)**: Code `80` (Central Government / Cục Cảnh sát giao thông).
- **NEVER_ISSUED Codes (8 codes)**: `13, 42, 44, 45, 46, 87, 91, 96` (strictly routed to `NEEDS_REVIEW` under `ReviewReasonCode.UNKNOWN_PLATE_PATTERN`).

### 3.2. Factor 2: Form Factor & Aspect Ratio

- **1-Line Format**: Standard rectangular plate ($470 \times 110\text{ mm}$, aspect ratio $w/h \approx 2.4 - 3.2$).
- **2-Line Format**: Square/stacked plate ($280 \times 200\text{ mm}$, aspect ratio $w/h \approx 1.3 - 1.8$).

### 3.3. Factor 3: Vehicle Category & Colorways

- **Civilian**: White reflective background, black embossed alphanumeric text.
- **Commercial / Logistics**: Yellow reflective background, black embossed text (e.g., taxi, delivery trucks).
- **Diplomatic / Foreign**: White background, red/black lettering (`NG`, `QT`).
- **State Agency**: Blue reflective background, white lettering.

### 3.4. Factor 4: Illumination & Environmental Interference

- Daytime direct sunlight (extreme specular glare).
- Overcast / shaded canopy (optimal diffuse illumination).
- Nighttime under infrared illuminators ($850\text{ nm}$ monochrome retro-reflective response).
- Headlight glare (direct high-beam flare dazzling the camera sensor).

### 3.5. Factor 5: Optical & Mechanical Degradation

- Lens defocus / Gaussian blur.
- Motion blur ($\ge 10\text{ px}$ smear).
- Physical plate wear: faded paint on raised character edges (confusing `8` with `B`, `0` with `D`, `3` with `8`, `2` with `Z`).

---

## 4. Evaluation Metrics & Definitions

1. **Exact Match Rate (EM %)**:
   $$\text{EM} = \frac{1}{N} \sum_{i=1}^N \mathbf{1}\left( \text{norm}(y_i) == \text{norm}(\hat{y}_i) \right) \times 100\%$$
2. **Character Accuracy (CA %)**:
   $$\text{CA} = \left( 1.0 - \frac{\sum_{i=1}^N \text{Levenshtein}(\text{norm}(y_i), \text{norm}(\hat{y}_i))}{\sum_{i=1}^N \max(\text{len}(y_i), \text{len}(\hat{y}_i))} \right) \times 100\%$$
3. **Minimum Character Confidence ($\min_j p_j$)**:
   Lowest individual predicted character probability in the plate sequence: $c_{\min} = \min_{j} p_{i, j} \times 100.0$.
4. **AUTO Coverage (%)**:
   Percentage of total scans admitted to automated gate opening: $\text{Cov}_{\text{AUTO}} = \frac{N_{\text{AUTO}}}{N_{\text{total}}} \times 100\%$.
5. **Wrong-in-AUTO Rate (%)**:
   Percentage of scans admitted to `AUTO` where the transcribed plate does not match ground truth:
   $$\text{WIA} = \frac{N_{\text{wrong in AUTO}}}{N_{\text{AUTO}}} \times 100\%$$
   - *Clean Benchmark*: Excludes Row 102 dirty label.
   - *Conservative Benchmark*: Includes Row 102 dirty label as a misread.
   - *95% Statistical Confidence Bound*: Wilson Score Interval upper bound.
6. **Inference Latency (ms)**:
   Single-crop execution time in milliseconds under ONNX Runtime CPU (`intra_op_num_threads = 1`, `inter_op_num_threads = 1`).

---

## 5. Quantitative Baseline Performance (Empirical Baseline Measurements)

All baseline performance metrics below were empirically verified on CPU on the frozen test dataset (SHA-256 `843233e5...`, Intel Core i7-12700H, single thread):

### 5.1. CCT-XS Standalone Model Performance

| Evaluation Dataset Slice | Sample Count | Exact Match (EM %) | Character Accuracy (CA %) | Average CPU Latency |
|---|:---:|:---:|:---:|:---:|
| **Set 1: Rows 0..99** | 100 | **93.00%** (93/100) | **98.12%** | Median 3.79 ms |
| **Set 2: Rows 100..199** | 100 | **96.00%** (96/100) | **99.37%** | Median 3.79 ms |
| **Full Frozen Test Set** | 322 | **94.72%** (305/322) | **98.91%** | **Median 3.79 ms (P95: 6.16 ms)** |

### 5.2. Dual-OCR Ensemble & Production Review Policy Performance

When CCT-XS operates inside the production ensemble with Mobile-ViT-v2 and the Multi-Signal Review Policy:

| Evaluation Slice | AUTO Count / Total | AUTO Coverage % | Wrong in AUTO Count | Wrong in AUTO % | Verification Status |
|---|:---:|:---:|:---:|:---:|:---:|
| **Tuning Split (161 Even, $\tau = 85\%$)** | 150 / 161 | **93.17%** | 4 | **2.67%** | VERIFIED |
| **Test Split (161 Odd, $\tau = 85\%$)** | 153 / 161 | **95.03%** | 1 | **0.65%** ($\le 1.0\%$) | **VERIFIED (PASS)** |
| **Full 322 Rows ($\tau = 90\%$, Production)** | 301 / 322 | **93.48%** | Clean: 3 / Cons: 4 | **Clean: 0.997%** / **Cons: 1.33%** | **VERIFIED** |

- **Exact Match on 322 Rows (Ensemble + Policy)**: **95.96%** (309 / 322) [Wilson 95% CI: **93.22% – 97.63%**, CC: **93.03% – 97.74%**].
- **95% Confidence Intervals for Wrong-in-AUTO (322 Rows)**:
  - Clean Wrong-in-AUTO (3 / 301 = 0.997%): Two-sided Wilson 95% CI **[0.34%, 2.89%]** (with CC: **[0.26%, 3.13%]**); One-sided 95% Wilson Upper Bound is **2.47%** (with CC: **2.70%**).
  - Conservative Wrong-in-AUTO (4 / 301 = 1.33%): Two-sided Wilson 95% CI **[0.52%, 3.37%]** (with CC: **[0.43%, 3.60%]**); One-sided 95% Wilson Upper Bound is **2.93%** (with CC: **3.15%**).
- **End-to-End Latency Breakdown (Empirically Measured on Intel Core i7-12700H, 1 thread)**:
  - YOLOv9-t 384 plate detection: Median **43.72 ms** (P95: 77.11 ms, ~88% of pipeline execution time).
  - CCT-XS v2 recognition (RGB): Median **4.58 ms** (P95: 8.81 ms).
  - Mobile-ViT-v2 recognition (Grayscale, conditional): Median **0.00 ms** (bypassed in AUTO agreements; P95: 3.54 ms).
  - Total end-to-end pipeline latency: Median **49.35 ms** (P95: 86.88 ms, mean 46.83 ms $\pm$ 1.99 ms across 5 repeated runs with exact match standard deviation **0.00%**). *Note: ADR-0007 reported ~32.8 ms on a different hardware host.*

---

## 6. Analytical Slice-Based Breakdown (6 Strata)

| Strata Identifier | Sample Size | Primary Failure Mode | Standalone CCT-XS Accuracy | Review Policy Filtering Action |
|---|:---:|---|:---:|---|
| `TPHCM_8` | 258 | Standard 8-character HCMC series | 96.90% (250/258) | High throughput; > 95% routed to AUTO |
| `NON_TPHCM_8` | 39 | Major provincial series (`29`, `60`, `61`) | 94.87% (37/39) | High throughput; correctly admitted |
| `LEGACY_7` | 14 | Pre-merger 4-digit serials (`52P-5688`) | 92.86% (13/14) | Position-aware correction repairs confusable letters |
| `HARD_8` | 10 | Extreme glare, deep blur, physical mud | 70.00% (7/10) | Quarantined to `NEEDS_REVIEW` by low confidence |
| `DUAL_9` | 3 | Specialized 9-character registrations | 100.0% (3/3) | Admitted to AUTO |
| `DIRTY_102` | 1 | External dataset label error (`51F-222611`) | 100.0% visual match | Transcribes true plate `51F22261` |

---

## 7. Ethical Considerations, Privacy & Decree 13/2023/ND-CP

### 7.1. Statutory Privacy Safeguards

- In full compliance with **Decree 13/2023/ND-CP**:
  - License plate numbers are treated as protected personal data.
  - Training pipeline processes only tight crops ($64 \times 128$) eliminating human faces and identifiable landmarks.
  - `training/data/frozen_test_registry.json` holds SHA-256 and 64-bit pHash digests of public-dataset photos (`sonnetechnology/license-plate-text-recognition-full`) and their detector crops (strictly 5 fields: `row_index`, `sha256`, `phash`, `crop_sha256`, `crop_phash`).
  - The 322 plate strings of those public benchmark images already appear in the public repository at `tests/parking/fixtures_322_metadata.py`.
  - The project never commits plate strings or images from the Owner's own cameras or private operational datasets.
  - Structured production logging enforces PII masking (`PARKING_LOG_MASK_PLATES = True` -> `51F***81`).
  - Production media retention follows strict soft-delete and purge retention floor ($\ge 30$ days) per `03-delete-rules-catalog.md`.

### 7.2. Defense Against Membership Inference Attacks (MIA)

- **Threat**: Attackers querying model confidence scores to infer whether a specific VIP or high-profile vehicle plate was present in the training corpus.
- **Mitigation Architecture**:
  - Heavy regularization applied during fine-tuning: Weight decay ($0.01$), dropout ($0.15$), stochastic depth ($0.1$), and label smoothing ($0.01$).
  - Early stopping on validation plate accuracy prevents over-memorization of specific training samples.
  - Production API suppresses raw internal softmax logit distributions, returning rounded confidence scores only (`round(conf, 2)`).

---

## 8. Limitations, Operational Failure Modes & System Mitigations

### 8.1. Documented Failure Modes

1. **False High-Confidence Agreement (Failure Mode #76)**:
   - Row 76 (`51F-025.68`): Ground truth is `51F02568`. The models misread character `2` as `7`, yielding `51F07568` with $99.99\%$ confidence due to dirt on the character stroke.
   - *System Mitigation*: Multi-Signal Entry/Exit Plate Reconciliation. When a vehicle checks out, the exit plate is compared against the active entry session. If edit distance is exactly 1, automated barrier lifting is inhibited, triggering operator manual verification with side-by-side photo inspection.
2. **Extreme Aspect Ratio Distortion (Row 236)**:
   - Square plates with $w/h \le 1.25$ suffer horizontal character compression.
   - *System Mitigation*: Geometric aspect ratio filter enforces $1.3 \le w/h \le 6.0$. Out-of-bounds crops are automatically routed to `NEEDS_REVIEW`.
3. **Dirty/Muddy Occlusion**:
   - Heavy mud obscuring more than 30% of a character stroke reduces confidence below $85\%$, correctly routing the session to `NEEDS_REVIEW`.

---

## 9. Model Governance & Sign-Off

| Role | Name / Title | Date | Signature Status |
|---|---|---|---|
| **Author / Lead Investigator** | Lead Computer Vision Engineer | 2026-10-25 | SIGNED |
| **Computer Vision Architect** | Lead AI Architect | 2026-10-25 | PENDING REVIEW |
| **Data Protection Officer (DPO)**| Enterprise Compliance Lead | 2026-10-25 | PENDING REVIEW |
