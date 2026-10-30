# Enterprise Data Card: Vietnamese License Plate Recognition Dataset

**Document Version**: 1.1.0 (Candidate Pool, Quarantine, 3-Way Triage & Synthetic Pipeline Specification)  
**Standard**: Gebru et al. (Datasheets for Datasets) / Hugging Face Enterprise Dataset Card  
**Regulatory Framework**: Decree 13/2023/ND-CP on Personal Data Protection (Vietnam)  
**Target Subproject**: `training/` (Isolated English-only Training Pipeline)  
**Status**: APPROVED BASELINE & CANDIDATE DATASET SPECIFICATION  

---

## 1. Executive Summary & Dataset Identification

| Metadata Attribute | Specification / Value |
|---|---|
| **Dataset Title** | Vietnamese License Plate Crop Recognition Dataset (VN-ALPR-OCR) |
| **Component A: Frozen Test Benchmark** | `sonnetechnology/license-plate-text-recognition-full` (Subset `^\d{2}[A-Z]`) |
| **Frozen Test Parquet File** | `test-00000-of-00001-a359b6560048e51f.parquet` (22,545,723 bytes) |
| **Frozen Test SHA-256 Checksum** | `843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b` |
| **Frozen Test Row Count** | Exactly **322 verified rows** (Read-only sacred regression benchmark) |
| **Frozen Test License** | Creative Commons Attribution 4.0 International (`CC-BY-4.0`) |
| **Component B: Extracted Candidate Pool** | 2,826 Vietnamese plate instances extracted from `train` and `validation` splits |
| **Quarantined Benchmark Leakage** | Exactly **257 instances** (181 photo pHash $\le 4$, 88 crop pHash $\le 4$, 0 exact SHA-256) |
| **Clean Candidate Pool** | Exactly **2,569 instances** partitioned into **1,827 deterministic `group_id` clusters** |
| **Component C: Kaggle Smoke Dataset** | `smoke_128` (128 crops: 64 train across 53 groups, 64 val across 43 groups, 0 group overlap) |
| **Smoke Archive Size & SHA-256** | `smoke_128.zip` (2,193,186 bytes, SHA-256: `ae8995d60e70ce643d0ecaa309f65188afea2d533a01ac25d7449f110fda44f4`) |
| **Data Modality** | 3-channel RGB image crops ($64 \times 128$ pixels) + text annotations |
| **Target Alphabet** | 30 statutory characters (10 digits `0-9` + 20 letters) + blank pad `_` (37 recognizer symbols) |
| **Training Distribution Privacy** | Private Dataset strictly enforced (`"isPrivate": true` on Kaggle, air-gapped container) |

### 1.1. Public Vietnamese ALPR Datasets Landscape & Audit Attestation

In accordance with enterprise data governance and anti-facade mandates, candidate public datasets were audited against primary sources:

| Dataset Identifier | Canonical URL | Access Date | License / Terms | Verified Content | Verification Status & Release Assessment |
|---|---|---|---|---|---|
| **`sonnetechnology/license-plate-text-recognition-full`** | `https://huggingface.co/datasets/sonnetechnology/license-plate-text-recognition-full` | 2026-10-25 | **CC-BY-4.0** | 322 Vietnamese vehicle plate crops (subset `^\d{2}[A-Z]`) from `test` Parquet (22,545,723 bytes, SHA-256 `843233e5...`) | **VERIFIED (Directly Inspected & Checksum Pinned)**. Sacred Frozen Test & Regression Guard ONLY. Strictly forbidden in training/val splits. |
| **Kaggle Vietnam License Plate Segment (Duy Dieu Nguyen)** | `https://www.kaggle.com/datasets/...` `[UNVERIFIED]` | Pending Audit | Unknown / Academic `[UNVERIFIED]` | ~5,000 images (mixed car and motorbike) `[UNVERIFIED]` | **`UNVERIFIED [Pending Audit]`**. Must be directly inspected with verified URL and commercial license prior to ingestion. |
| **Kaggle VNLicensePlate_yolov7 (Bao Mai Chi)** | `https://www.kaggle.com/datasets/...` `[UNVERIFIED]` | Pending Audit | Open Database / CC0 `[UNVERIFIED]` | ~1,000 images (bounding boxes) `[UNVERIFIED]` | **`UNVERIFIED [Pending Audit]`**. Lacks character transcriptions; unsuitable for recognizer training without relabeling. |
| **Roboflow Universe Vietnamese Plate Projects** | `https://universe.roboflow.com/...` `[UNVERIFIED]` | Pending Audit | Commonly CC-BY-NC-4.0 `[UNVERIFIED]` | Various (100–3,000 images) `[UNVERIFIED]` | **`UNVERIFIED [Pending Audit]`**. Non-Commercial restrictions (NC) legally prohibit enterprise deployment. |

---

## 2. Dataset Motivation & Intended Purpose (Gebru et al. — Motivation)

### 2.1. Purpose

This dataset is curated to fine-tune and evaluate the Compact Convolutional Transformer (CCT-XS) model—initialized from published global weights `cct_xs_v2_global` (transfer learning, strictly not training from scratch)—for automated transcription of civilian passenger vehicle license plates in barrier-controlled parking access systems in Vietnam.

### 2.2. Domain Scope & Target Distribution

- **Geographic Scope**: Vietnam (national territory, 34 restructured administrative divisions per Circular 51/2025/TT-BCA, Circular 79/2024/TT-BCA, and Circular 24/2023/TT-BCA).
- **Target In-Scope Class**: Civilian passenger automobiles bearing standard 1-line rectangular registration plates (`^\d{2}[A-Z]\d{4,5}$`).
- **Explicit Out-of-Scope Series**:
  - Military vehicle registrations (`^[A-Z]{2}\d{4,5}$`).
  - Central government and agency plates (Code `80`).
  - Diplomatic, foreign, joint-venture, and special dual-letter series (`NG`, `QT`, `CV`, `NN`, `LD`, `DA`, `KT`, `CD`, `TD`).
  - Motorbike and two-wheeler plates (2-line square format).
- **Measurement Status & Boundary Guarantees**: Quantitative coverage on out-of-scope series is unmeasured, and detector localization on non-standard plate colorways (red military plates, blue agency plates) is designated as `UNVERIFIED`. All out-of-scope plates are safely filtered to human operator inspection (`NEEDS_REVIEW`) by backend statutory rules.

### 2.3. Out-of-Scope Uses & Explicit Prohibitions

- Open-road high-speed tolling without barrier guidance (free-flow multi-lane highway tolling).
- Indiscriminate mass urban surveillance, vehicle tracking across multiple facilities, or law-enforcement profiling without judicial warrant.
- Facial recognition, biometric surveillance, or chassis vehicle profiling.

---

## 3. Upstream Provenance Chain & Licensing Audit (Gebru et al. — Provenance)

### 3.1. Four-Tier Upstream Pedigree

The provenance and legal pedigree of the training data were traced through primary API endpoints:

```text
[Tier 3: Root Public Source]
Roboflow Universe: "augmented-startups/vehicle-registration-plates-trudk"
(HTTP 403 Forbidden / Cloudflare Challenge -> Status: UNVERIFIED)
        │
        ▼ (Exported COCO bounding boxes)
[Tier 2: Intermediate Detection Dataset]
Hugging Face: "keremberke/license-plate-object-detection"
(Card YAML license: None / Body text: "CC BY 4.0")
        │
        ▼ (Cropped bounding boxes & ran automated OCR)
[Tier 1: Derivative Recognition Dataset]
Hugging Face: "sonnetechnology/license-plate-text-recognition-full"
(Declared: CC-BY-4.0 | Labels generated by microsoft/trocr-large-printed)
        │
        ├── 322 Rows: Frozen Test Benchmark (Read-Only Sacred Regression Guard)
        └── 2,826 Instances: Candidate Vietnamese Pool (257 Quarantined, 2,569 Clean)
```

| Pipeline Tier | Entity Identifier | Declared License | Primary Query & Status | Verification Assessment |
|---|---|---|---|---|
| **Tier 1 (Derivative)** | `sonnetechnology/license-plate-text-recognition-full` | `CC-BY-4.0` | Hugging Face Dataset API -> `HTTP 200 OK` | **VERIFIED (Derivative Card)**. Declares `cc-by-4.0` in metadata; README explicitly documents annotations as machine-generated. |
| **Tier 2 (Detection)** | `keremberke/license-plate-object-detection` | Undeclared (Card) / `CC BY 4.0` (Text) | Hugging Face Dataset API -> `HTTP 200 OK` | **PARTIALLY VERIFIED (Text Only)**. Structured metadata lacks license field (`cardData.license: None`). Markdown body claims CC BY 4.0. |
| **Tier 3 (Root Source)** | Roboflow Universe: `augmented-startups/vehicle-registration-plates-trudk` | Unknown / Blocked | Web URL -> `HTTP 403 Forbidden`; REST API -> `HTTP 401 Unauthorized` | **`UNVERIFIED`**. Cloudflare protection prevents automated validation of commercial redistribution rights. |
| **Label Generator** | `microsoft/trocr-large-printed` | MIT License | GitHub Repository (`microsoft/unilm`) -> `HTTP 200 OK` | **VERIFIED**. Permissive open-source research license. |

### 3.2. Legal & Intellectual Property Analysis

- **Derivative Works & Upstream Rights**: Under copyright principles, a downstream compiler (`sonnetechnology`) cannot grant broader rights than those provided by the primary copyright holder (`augmented-startups`). If the root dataset carried Non-Commercial restrictions (`NC`), downstream `CC-BY-4.0` claims are unenforceable for commercial deployment.
- **Machine-Generated Annotations**: Annotations generated by automated model inference (`microsoft/trocr-large-printed`) generally lack human authorship required for copyright protection. However, the input photographic images remain protected by original photographic copyright.
- **Public Weight Distribution Risk**: Model weights trained directly on unverified root data risk copyright dispute if published publicly or distributed in commercial SaaS solutions.

### 3.3. Strategic Options for the Project Owner

To maintain compliance without imposing a unilateral business decision, three actionable options are established:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PROJECT OWNER STRATEGIC OPTIONS                       │
├────────────────────────┬────────────────────────────┬───────────────────────┤
│ Option 1: Research Only│ Option 2: Commercial Grant │ Option 3: Own Camera  │
│ Private Model Weights  │ Contact Upstream Author    │ Field Data Transition │
├────────────────────────┼────────────────────────────┼───────────────────────┤
│ • Model weights kept   │ • Contact Augmented        │ • Collect images from │
│   strictly internal    │   Startups for written     │   Owner's parking     │
│ • No public weights    │   commercial confirmation  │   cameras with notice │
│ • Fast, zero friction  │ • Resolves Tier 3 status   │ • 100% legal clarity  │
│ • Zero commercial SaaS │ • Dependent on third-party │ • Requires operational│
│   redistribution       │   response and terms       │   labelling pipeline  │
└────────────────────────┴────────────────────────────┴───────────────────────┘
```

1. **Option 1: Internal & Research Training Only (Private Weights)**: Proceed with candidate fine-tuning exclusively for internal evaluation and staging. Weights remain strictly private (`"isPrivate": true`) and are never published to public registries.
2. **Option 2: Seek Written Permission from Augmented Startups**: Request written commercial confirmation or licensing terms from Augmented Startups, resolving the `UNVERIFIED` status of Tier 3.
3. **Option 3: Progressive Replacement with Owner-Owned Camera Data (Decree 13/2023/ND-CP)**: Collect operational vehicle crops from client parking facilities with user notice under Decree 13/2023/ND-CP, annotate via the internal review kit, and retire third-party datasets.

---

## 4. Dataset Composition & Instance Inventory (Gebru et al. — Composition)

### 4.1. Component A: Frozen Test Benchmark (322 Rows)

- **Origin**: Public research dataset `sonnetechnology/license-plate-text-recognition-full` (`test` Parquet split).
- **Filtering Logic**: Evaluated deterministically via regex `re.match(r"^\d{2}[A-Z]", target_text)`.
- **Exact Count**: Exactly **322 verified rows** (indices 0..321).
- **Cryptographic Pinned Contract**: SHA-256 and 64-bit DCT pHash digests for all 322 full photos and detector crops are committed in `training/data/frozen_test_registry.json`.

#### Documented Label Anomaly: Benchmark Row 102 Defect

- **Benchmark Index**: Row `102` (Parquet table row `267`, photo SHA-256: `5425ce2473621a7341ed48724c0d695f80407e4c6b04f872fc5686c9a4ef905d`).
- **Raw Machine Label**: 9 characters with 6 trailing digits (redacted: `51F-******`).
- **Physical Vehicle Image**: Physical vehicle photo clearly displays standard 8-character registration (synthetic illustration: `99F22261`).
- **Model Behavior**: Standard OCR recognizers transcribe the 8-character string with 100% confidence.
- **Root Cause Analysis**: The upstream label generator `microsoft/trocr-large-printed` suffered an optical character repetition hallucination due to optical reflection or font artifact. Vietnamese motor vehicle standards (Circular 24/2023/TT-BCA) strictly restrict civilian passenger car series to 4 digits (legacy) or 5 digits (standard). A 6-digit serial tail does not exist in Vietnamese law.
- **Reporting Invariant**: Model evaluation reports must state both Clean Benchmark (excluding Row 102, baseline error rate `0.997%`) and Conservative Benchmark (penalizing Row 102 as misread, baseline error rate `1.33%`).

### 4.2. Component B: Extracted Candidate Pool & Quarantine (2,826 Instances)

Candidate extraction from cached Parquet splits (`train`: 167,983,745 bytes; `validation`: 46,305,889 bytes) evaluating all bounding boxes matching `^\d{2}[A-Z]` yields:

| Split Name | File Size (Bytes) | SHA-256 Digest | Extracted VN Instances | Quarantined Instances | Clean Candidate Instances |
|---|---|---|---|---|---|
| `train` | 167,983,745 | `04fb8000f100d46fd68cd0321561aba8b12f7112f5510383eb4437405ad53e61` | 2,177 | 196 | 1,981 |
| `validation` | 46,305,889 | `73734b712ffdb67ba1968029de3869d52e174c5b27407dc6f2ca88f1465697b5` | 649 | 61 | 588 |
| **Combined** | **214,289,634** | — | **2,826** | **257** | **2,569** |

#### Quarantine Isolation Against Benchmark Contamination

To enforce air-gapped test separation, every extracted instance is audited against `training/data/frozen_test_registry.json`:

- **Exact SHA-256 Matches**: Exactly **0** full photo matches and **0** crop matches.
- **Full-Photo Near-Duplicates ($D_{\text{Hamming}} \le 4$)**: Exactly **181 instances** (134 in `train`, 47 in `validation`).
- **Crop Near-Duplicates ($D_{\text{Hamming}} \le 4$)**: **88 instances** (72 in `train`, 16 in `validation`).
- **Total Quarantined**: Exactly **257 instances** (196 in `train`, 61 in `validation`).
- **Enforcement**: Quarantined items are tagged with `quarantine_{sha[:16]}` and permanently excluded from training and validation sets.

#### Pairwise Minimum pHash Distance Histogram to Benchmark

Distribution of minimum Hamming distance $D_H$ from candidate images to the 322 frozen-test benchmark images:

| Minimum Distance ($D_H$) | Number of Images | Cumulative Count | Cumulative Share | Risk Assessment |
|---|---|---|---|---|
| 0 | 35 | 35 | 1.24% | Exact perceptual duplicate -> QUARANTINE |
| 1 | 0 | 35 | 1.24% | Parity constraint |
| 2 | 60 | 95 | 3.37% | Minor compression artifact -> QUARANTINE |
| 3 | 0 | 95 | 3.37% | Parity constraint |
| 4 | 86 | **181** | **6.42%** | Minor crop/shift perturbation -> QUARANTINE |
| 6 | 140 | 321 | 11.38% | Clean separation boundary (Admitted) |
| 8 | 263 | 584 | 20.71% | Distinct scene / angle (Admitted) |
| 10 | 388 | 972 | 34.47% | Distinct vehicle capture (Admitted) |
| $\ge 12$ | 1,848 | 2,820 | 100.00% | Completely uncorrelated (Admitted) |

#### Deterministic Group Clustering (`group_id`)

Vehicles captured across sequential video frames share visual context. Connected-components graph clustering ($D_H \le 4$ or shared `image_id`) on the 2,569 clean instances establishes **1,827 deterministic groups**:

- **Singleton Groups**: 1,366 groups (single-frame captures).
- **Multi-Instance Groups**: 461 groups (burst-capture sequences of 2 to 14 frames).
- **Group Naming Contract**: Deterministically assigned as `grp_{min_photo_sha256[:16]}`.

---

## 5. Label Quality Triage & Annotation Provenance (Gebru et al. — Collection & Labeling)

### 5.1. Machine-Generated Origin & Quality Verification

Per lines 46–52 of `sonnetechnology` README, 100% of upstream labels were generated by `microsoft/trocr-large-printed`. To detect machine hallucinations, a 3-way consensus triage was executed comparing:

1. **Reading 1 ($R_1$)**: Upstream Parquet label (TrOCR machine transcription).
2. **Reading 2 ($R_2$)**: Production dual-OCR recognizer (`FastAlprPlateRecognizer`: YOLOv9-t + CCT-xs-v2 + Mobile-ViT-v2 ensemble).
3. **Reading 3 ($R_3$)**: Published standalone `cct_xs_v2_global` ONNX model evaluated directly on normalized $64 \times 128$ RGB crops.

### 5.2. Three-Way Label Quality Triage Breakdown

| Dataset Partition | Evaluated Instances | Group A (3-Way Consensus) | Group B (Disagreements) | Group C (Out-of-Scope / Invalid) |
|---|---|---|---|---|
| **Clean Candidate Pool** | 2,569 | **2,391 (93.07%)** | **121 (4.71%)** | **57 (2.22%)** |
| **Quarantine Pool** | 257 | **249 (96.89%)** | **6 (2.33%)** | **2 (0.78%)** |
| **Frozen Test Benchmark** | 322 | **302 (93.79%)** | **17 (5.28%)** | **3 (0.93%)** |
| **Overall Dataset** | **3,148** | **2,942 (93.46%)** | **144 (4.57%)** | **62 (1.97%)** |

- **Group A (3-Way Consensus)**: $R_1 == R_2 == R_3$ and syntax is `STRICT_VALID` civilian passenger car (`^\d{2}[A-Z]\d{4,5}$`).
- **Group B (Disagreement / Recoverable)**: Models disagree on 1 or more characters, but at least one reading yields valid civilian syntax (includes Row 102 where $R_2$ and $R_3$ agree on the correct 5-digit civilian registration).
- **Group C (Out-of-Scope / Format Error)**: Special dual-letter registrations (e.g. 3 benchmark rows `57`, `65`, `181` are joint-venture `LD` series), central agency `80`, military registrations, or unreadable noise. Permanently barred from candidate training sets.

### 5.3. Benchmark Disagreements with Production Recognizer

On the 322 frozen-test benchmark images:

- Production Recognizer ($R_2$) on **full photo**: exactly **13 disagreements** with TrOCR ground truth (95.96% agreement).
- Production Recognizer ($R_2$) on **standardized crop**: **15 disagreements** with TrOCR ground truth (95.34% agreement).
- **Audit Classification**: Formally designated as `UNKNOWN_PENDING_HUMAN_REVIEW`. True ground truth accuracy cannot be determined by machine voting alone and requires independent human arbitration.

### 5.4. Human Review Protocol & Statistical Quality Bounds

To certify training data without unbounded human annotation effort, `training/docs/labeling-guide.md` establishes a risk-tiered review protocol:

1. **Review Cohort Partitioning (824 Total Tasks)**:
   - **Batch 0 (Gold Benchmark)**: 100% of the 322 frozen-test images (independent verification of evaluation ground truth).
   - **Batch 1 (High Risk Disagreements)**: 100% of the 121 Group B clean candidate pool instances.
   - **Batch 2 (Statistical Consensus Sample)**: Random sample of $n \ge 381$ instances from Group A.
2. **Wilson Score Upper Bound Exact Derivation ($n \ge 381$)**:
   To establish with $95\%$ confidence ($\alpha = 0.05, z = 1.959964$) that the residual error rate of Group A consensus labels does not exceed $p_{\text{target}} = 1.0\%$ when $0$ errors are observed in the sample, the Wilson score continuity upper bound is solved:
   $$p_U = \frac{z^2}{n + z^2} < 0.01 \implies n > z^2 \left(\frac{1}{0.01} - 1\right) = (1.959964)^2 \times 99 = 380.3044 \implies n \ge 381$$
3. **Double-Annotation & Consensus Targets**:
   - Double independent annotation on 100% of Batch 1 and Batch 2.
   - Character Error Rate target: $\text{CER}(A_1, A_2) \le 0.5\%$.
   - Cohen's kappa target: $\kappa \ge 0.90$.
   - Total labor estimate: 1,648 primary annotations + 44 dispute arbitrations $\approx$ **4.94 person-hours** (~5 person-hours).

---

## 6. Bounding Box Geometry & Resolution Limitations

### 6.1. Bounding Box Convention Verification

All 3,142 Vietnamese plate bounding boxes across the dataset were evaluated:

- **Condition $x_1 < x_2$**: Satisfied by **3,142 / 3,142 (100.0%)**.
- **Condition $y_1 < y_2$**: Satisfied by **3,142 / 3,142 (100.0%)**.
- **Coordinate System**: Absolute pixel values $[x_1, y_1, x_2, y_2]$ where $(x_1, y_1)$ is top-left and $(x_2, y_2)$ is bottom-right.
- **Normalization Formula**: Scaled to image dimensions as $[x_1 / W, y_1 / H, x_2 / W, y_2 / H]$.

### 6.2. Crop Resolution Percentile Distribution

Calculated across all 3,142 Vietnamese plate bounding boxes:

| Dimension / Metric | Min | p10 | p25 | Median | p75 | p90 | Max |
|---|---|---|---|---|---|---|---|
| **Width (px)** | 36.0 | 78.0 | 91.0 | **103.0** | 112.0 | 126.0 | 170.0 |
| **Height (px)** | 9.0 | 22.0 | 26.0 | **31.0** | 37.0 | 47.9 | 125.0 |
| **Aspect Ratio ($w/h$)** | 1.01 | 2.40 | 2.87 | **3.29** | 3.67 | 4.00 | 7.10 |

### 6.3. Small-Resolution Share Breakdown

| Resolution Threshold | Condition | Candidate Pool Share | Technical Risk & Implication |
|---|---|---|---|
| **$< 64 \times 128$ px** | Both dimensions ($w < 128$ and $h < 64$) | **90.32%** | Over 90% of plates possess lower native resolution than model input. |
| **$< 64 \times 128$ px** | Either dimension ($w < 128$ or $h < 64$) | **99.08%** | Almost all candidate crops require upscaling interpolation. |
| **$< 32 \times 96$ px** | Both dimensions ($w < 96$ and $h < 32$) | **28.49%** | Severe low-resolution domain; extreme stroke blending risk. |
| **$< 32 \times 96$ px** | Either dimension ($w < 96$ or $h < 32$) | **57.80%** | More than half of crops have sub-optimal character definition. |

### 6.4. Implications of Upsampling Interpolation Blur

Because the CCT-XS model expects standardized $64 \times 128$ RGB tensors:

1. **Edge Sharpness Degradation**: Bilinear and bicubic upsampling of small crops (e.g. median $103 \times 31$ up to $128 \times 64$, and extreme cases down to $36 \times 9$) acts as a low-pass filter, smoothing sharp character edges and blurring inter-character spaces.
2. **Character Confusion Vulnerabilities**: Interpolation blur increases confusion among visually similar glyphs:
   - Digit `8` versus letter `B`.
   - Digit `0` versus letter `D`.
   - Digit `5` versus letter `S`.
3. **Training Mitigation**: Model pre-training and data augmentation must apply synthetic downsampling jitter ($Q \in [30, 85]$, resolution reduction to $103 \times 31$ followed by interpolation) to render the model invariant to upsampling blur.

---

## 7. Distribution Analysis & Rare Slices (Gebru et al. — Composition)

### 7.1. Target Alphabet & Vocabulary Representation

The Vietnamese civilian automobile plate vocabulary comprises **30 statutory characters** (10 digits `0-9` and 20 legal series letters):

$$\Sigma = \{0, 1, 2, 3, 4, 5, 6, 7, 8, 9, A, B, C, D, E, F, G, H, K, L, M, N, P, S, T, U, V, X, Y, Z\}$$

*(Note: Letters `I, J, O, Q, W, R` are excluded from statutory civilian series under Circular 24/2023/TT-BCA).*

### 7.2. Character Distribution in Clean Candidate Pool (2,569 Instances)

Total characters across the 2,569 clean candidate instances: **20,776 characters**.

| Character | Class | Clean Pool Count (2,569) | Representation Share | Category / Slice Risk |
|---|---|---|---|---|
| `0` | Digit | 1,701 | 8.19% | Well-represented |
| `1` | Digit | 3,962 | 19.07% | High frequency (Province `51` & serials) |
| `2` | Digit | 1,613 | 7.76% | Well-represented |
| `3` | Digit | 1,005 | 4.84% | Well-represented |
| `4` | Digit | 1,152 | 5.54% | Well-represented |
| `5` | Digit | 3,485 | 16.77% | High frequency (Province `51` & serials) |
| `6` | Digit | 1,402 | 6.75% | Well-represented |
| `7` | Digit | 1,207 | 5.81% | Well-represented |
| `8` | Digit | 1,040 | 5.01% | Well-represented |
| `9` | Digit | 1,291 | 6.21% | Well-represented |
| `A` | Letter | 872 | 4.20% | Frequent series letter |
| `B` | Letter | 18 | 0.09% | **Rare slice (< 30 instances)** |
| `C` | Letter | 4 | 0.02% | **Rare slice (< 30 instances)** |
| `D` | Letter | 49 | 0.24% | Moderate frequency |
| `E` | Letter | 10 | 0.05% | **Rare slice (< 30 instances)** |
| `F` | Letter | 1,120 | 5.39% | Dominant series letter (`51F` series) |
| `G` | Letter | 388 | 1.87% | Frequent series letter |
| `H` | Letter | **0** | **0.00%** | **ZERO INSTANCES IN REAL DATASET** |
| `K` | Letter | 4 | 0.02% | **Rare slice (< 30 instances)** |
| `L` | Letter | 49 | 0.24% | Moderate frequency |
| `M` | Letter | 1 | 0.005% | **Rare slice (< 30 instances)** |
| `N` | Letter | 20 | 0.10% | **Rare slice (< 30 instances)** |
| `P` | Letter | 5 | 0.02% | **Rare slice (< 30 instances)** |
| `S` | Letter | 2 | 0.01% | **Rare slice (< 30 instances)** |
| `T` | Letter | 6 | 0.03% | **Rare slice (< 30 instances)** |
| `U` | Letter | 2 | 0.01% | **Rare slice (< 30 instances)** |
| `V` | Letter | 20 | 0.10% | **Rare slice (< 30 instances)** |
| `X` | Letter | 2 | 0.01% | **Rare slice (< 30 instances)** |
| `Y` | Letter | 37 | 0.18% | Moderate frequency |
| `Z` | Letter | 20 | 0.10% | **Rare slice (< 30 instances)** |

*(Note: Unverified raw machine labels also contained single machine-transcription errors: `J`: 1, `R`: 1, isolated in Group B/C triage).*

### 7.3. Province Code Distribution in Clean Candidate Pool (2,569 Instances)

| Province Code | Administrative Division (Per Circular 51/2025/TT-BCA) | Clean Pool Count | Pool Percentage | Slice Status |
|---|---|---|---|---|
| **`51`** | Ho Chi Minh City (Primary Car Series) | **2,098** | **81.67%** | Dominant mode |
| **`60`** | Dong Nai Province | **103** | **4.01%** | Major province |
| **`29`** | Hanoi Capital (Series A) | **52** | **2.02%** | Major province |
| **`61`** | Binh Duong Province | **52** | **2.02%** | Major province |
| **`50`** | Ho Chi Minh City (Commercial / Suburban Series) | **51** | **1.99%** | Moderate province |
| **`48`** | Đắk Nông Province | **44** | **1.71%** | Moderate province |
| **`52`** | Ho Chi Minh City (Legacy / Relief Series) | **43** | **1.67%** | Moderate province |
| **`30`** | Hanoi Capital (Series B) | **41** | **1.60%** | Moderate province |
| **`62`** | Long An Province | **36** | **1.40%** | Moderate province |
| `86` | Binh Thuan Province | 11 | 0.43% | Rare slice (< 30 instances) |
| `93` | Bình Phước Province | 11 | 0.43% | Rare slice (< 30 instances) |
| `56` | Khánh Hòa Province | 8 | 0.31% | Rare slice (< 30 instances) |
| `34` | Hai Duong Province | 4 | 0.16% | Rare slice (< 30 instances) |
| `43` | Da Nang City | 4 | 0.16% | Rare slice (< 30 instances) |
| `71` | Ben Tre Province | 4 | 0.16% | Rare slice (< 30 instances) |
| `47` | Dak Lak Province | 3 | 0.12% | Rare slice (< 30 instances) |
| `49` | Lam Dong Province | 1 | 0.04% | Rare slice (< 30 instances) |
| `16` | Hai Phong City | 1 | 0.04% | Rare slice (< 30 instances) |
| `55` | Quang Tri Province | 1 | 0.04% | Rare slice (< 30 instances) |
| `00` | Machine Transcription Error (Group C) | 1 | 0.04% | Format error |
| **All Others** | **Remaining Vietnamese Administrative Provinces** | **0** | **0.00%** | **ZERO SAMPLES** |

- **Ho Chi Minh City Concentration**: Codes `50`, `51`, and `52` account for **2,192 instances (85.32%)** of the entire clean candidate pool.
- **Geographic Blind Spots**: 25 out of 34 restructured administrative divisions have zero representation in the dataset.

### 7.4. Recognizer Generalization Risk Assessment

1. **Extreme Letter Blind Spots**: Letter `H` has literally **0** samples in the dataset, while `B`, `C`, `E`, `K`, `M`, `P`, `S`, `T`, `U`, `X` have fewer than 20 samples each. A recognizer trained exclusively on real candidate crops cannot reliably transcribe these characters and will produce out-of-vocabulary hallucinations.
2. **Geographic Overfitting**: An OCR model fine-tuned on this dataset without distribution balancing will become severely biased toward Ho Chi Minh City registrations (`51A`, `51F`, `51G`), failing on vehicles registered in Hanoi (`29/30`), Da Nang (`43`), or northern/central provinces.
3. **Engineering Mitigation**: Balanced synthetic data generation is mathematically indispensable to ensure uniform coverage across all 30 characters and all 34 statutory provinces.

---

## 8. Smoke 128 Kaggle Dataset Specification

The `smoke_128` dataset is an air-gapped, verifiable dataset configured for executing Kaggle smoke pipeline validation:

| Attribute | Specification Value |
|---|---|
| **Dataset Identifier** | `smoke_128` |
| **Total Sample Count** | Exactly **128 crop images** ($64 \times 128$ RGB PNG) |
| **Split Partitioning** | 64 Train samples / 64 Validation samples |
| **Group Partitioning** | Train: 53 groups / Validation: 43 groups (**0 group overlap**) |
| **Quality Tier** | **100% Group A** (Verified 3-way consensus among TrOCR, Recognizer, and CCT-XS) |
| **Label Status** | `"provisional_machine_generated"` (`provisional: true`, `verified_by_human: false`) |
| **Archive Filename** | `smoke_128.zip` |
| **Archive File Size** | **2,193,186 bytes** (~2.19 MB) |
| **Archive SHA-256 Digest** | `ae8995d60e70ce643d0ecaa309f65188afea2d533a01ac25d7449f110fda44f4` |
| **Archive Total Entries** | Exactly **129 entries** (1 `manifest.json` + 128 physical PNG crops) |
| **Benchmark Deduplication** | Minimum pHash Hamming distance to 322 frozen test = **6** (strictly $\ge 5$, 0 leakage $\le 4$) |
| **Exact SHA-256 Benchmark Overlap** | Exactly **0** matches |
| **Validation Schema** | Strictly passes `manifest.schema.json` and `plate_training.split.validate_splits` |

### 8.1. Smoke 128 Character and Province Distribution

- **Total Characters**: 1,019 characters (Train: 509, Val: 510).
- **Character Breakdown**:
  - Digits: `0` (77), `1` (198), `2` (72), `3` (54), `4` (64), `5` (168), `6` (67), `7` (58), `8` (66), `9` (67).
  - Letters: `A` (39), `C` (1), `F` (65), `G` (18), `N` (1), `Y` (3), `Z` (1).
- **Provinces Present**: 9 distinct provinces (51: 107, 60: 8, 29: 4, 52: 3, 62: 2, 30: 1, 50: 1, 61: 1, 86: 1).

---

## 9. Synthetic Plate Generation Pipeline Technical Specification

To eliminate the severe letter skew (e.g. Letter `H` = 0) and address the licensing vulnerabilities of public web datasets, an in-house synthetic plate generation pipeline is architected for remote execution on Kaggle GPU hardware.

### 9.1. Statutory Regulatory Specifications

The synthetic rendering engine must adhere to national standards published by the Ministry of Public Security:

- **Circular 24/2023/TT-BCA**: Standard civilian passenger vehicle rectangular one-line plates:
  - Physical plate dimensions: $110\text{ mm} \times 470\text{ mm}$ (aspect ratio $4.27:1$).
  - Border: 5 mm raised black border with rounded corners ($R = 10\text{ mm}$).
  - Reflective white background with national circular emblem stamped between province code and series letter.
  - Character stroke width and height: Standard height 75 mm, stroke width 14 mm.
- **Circular 79/2024/TT-BCA & Circular 51/2025/TT-BCA**: Standardized province coding rules covering all 34 restructured administrative divisions and registered vehicle classes.

### 9.2. Two-Stage Rendering Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                 SYNTHETIC PLATE DATA GENERATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ Stage 1: Vector Layout & Typographic Synthesis                              │
│ • Uniform character sampling across all 30 statutory glyphs (zero blind spot)│
│ • Statutory letter spacing, stroke kerning, and national seal rendering     │
│ • Open-source licensed font (OFL / Apache 2.0 compliant typeface)           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                      │ (High-resolution clean SVG / Canvas) │
│                                      ▼                                      │
│ Stage 2: Photorealistic Domain Randomization (Augmentations)                │
│ • 3D Projective transformations: Yaw (±25°), Pitch (±20°), Roll (±10°)      │
│ • Optical blur: Gaussian motion blur (speed simulation), defocus blur       │
│ • Environmental lighting: Specular flash reflection glare, harsh sun shadow │
│ • Weather & surface noise: Rain streaks, mud/dirt spatter, salt-and-pepper │
│ • Sensor simulation: Downscaling to native resolution (103x31) + Bilinear   │
│   upscaling to 64x128 + JPEG compression quality jitter (Q ∈ [30, 85])      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                      │                                      │
│                                      ▼                                      │
│                Standardized 64x128 RGB Training Crop Tensor                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Typographic Synthesis & Font Licensing Safeguards**:
   - Proprietary road fonts (e.g. copyrighted commercial signage typefaces) are strictly forbidden to eliminate copyright infringement liability.
   - The generator must utilize an open-source font licensed under the SIL Open Font License (OFL) or Apache 2.0 (e.g. open-licensed sans-serif font derivatives or bespoke in-house vector glyphs designed from statutory dimensions).
2. **Photorealistic Augmentation Engine**:
   - Random projective transformations simulating barrier camera angles.
   - Non-uniform specular glare simulating night camera flash bounce.
   - Resolution-matching degradation: Synthetically downsampling high-resolution renders to the candidate median of $103 \times 31$ pixels before upsampling to $64 \times 128$, training the model to be robust against interpolation blur.

### 9.3. Controlled Kaggle GPU Ablation Experiment Design

All model training and large-scale image rendering must occur exclusively on remote Kaggle GPU hardware (zero image generation or training on local laptops):

| Experiment ID | Training Dataset Composition | Sample Count | Objective / Hypothesis | Evaluation Benchmark |
|---|---|---|---|---|
| **EXP-01** | Real-Only Baseline (Group A Clean Pool) | 2,391 crops | Baseline transfer learning performance from `cct_xs_v2_global`. Expected to fail on rare letters (`H, B, C, K, M`). | 322 Frozen Test + Rare Slice Benchmark |
| **EXP-02** | Synthetic-Only Baseline | 50,000 crops | Evaluate whether photorealistic synthetic data alone can generalize to real vehicle cameras without real training data. | 322 Frozen Test + Rare Slice Benchmark |
| **EXP-03** | Mixed Curriculum Pre-Training | 100k Synthetic + 2.3k Real | Pre-train on 100,000 balanced synthetic crops to learn universal character geometry, followed by fine-tuning on real crops. | 322 Frozen Test + Rare Slice Benchmark |

---

## 10. Data Hygiene, Manifest Schema & Regulatory Compliance

### 10.1. Manifest Schema & Data Contract (`manifest.schema.json`)

All training manifests ingested into `plate_training` must validate against JSON Schema Draft 2020-12 at `training/data/manifest.schema.json`:

- Required fields: `image_path`, `sha256`, `plate_text`, `split`, `provenance`, `license`.
- Conditional requirement: `group_id` strictly required for `train` and `val` splits to guarantee group-disjoint isolation.
- Quality categorization: `readable`, `ambiguous`, `unreadable`.

### 10.2. Cryptographic Leakage Prevention Flowchart

```text
[Candidate Ingestion Batch]
            │
            ▼
┌────────────────────────────────────────┐
│  Exact SHA-256 Duplicate Screening     │  Match against frozen-test?
│  hash(raw_image_bytes)                 │  ──> YES: ROUTE TO QUARANTINE
└────────────────────────────────────────┘
            │ NO
            ▼
┌────────────────────────────────────────┐
│  Perceptual Hash (pHash) Screening     │  Hamming Distance <= 4?
│  64-bit DCT perceptual fingerprint     │  ──> YES: ROUTE TO QUARANTINE
└────────────────────────────────────────┘
            │ NO
            ▼
┌────────────────────────────────────────┐
│  Multi-Frame Group Isolation (group_id)│  Same vehicle across splits?
│  Deterministic connected components    │  ──> YES: ALLOCATE TO SINGLE SPLIT
└────────────────────────────────────────┘
            │ PASS
            ▼
    [Admitted to Manifest]
```

### 10.3. Decree 13/2023/ND-CP Personal Data Protection

Under Articles 2, 3, and 24 of Decree No. 13/2023/ND-CP of the Government of Vietnam:

- **Personal Data Status**: Vehicle license plate numbers constitute personal data (*dữ liệu cá nhân*) when linked with facility entry timestamps and camera location.
- **Data Minimization**: Full vehicle chassis, driver faces, bystander pedestrians, and GPS EXIF metadata must be stripped. Only tightly cropped bounding boxes ($64 \times 128$) containing strictly the plate characters are admitted.
- **Repository Hygiene**: Real license plate strings must never be committed to git or printed in unmasked reports. All documentation utilizes counts, hashes, and synthetic examples.
- **DPIA Obligation**: The enterprise operating the ALPR deployment must maintain a Data Protection Impact Assessment (DPIA) file for submission to the Ministry of Public Security (Department A05).

### 10.4. Kaggle Cloud Governance & Privacy Invariants

- **Mandatory Private Setting**: Any dataset uploaded to Kaggle must declare `"isPrivate": true` in `dataset-metadata.json`.
- **Air-Gapped Notebook Execution**: Training notebooks must declare `"enable_internet": false` in `kernel-metadata.json` to prevent outbound data exfiltration.
- **Zero Secret Exposure**: Credentials (`kaggle.json`) and tokens (`.env`) are strictly excluded via `.gitignore` and `.dockerignore`.

---

## 11. Dataset Maintenance, Errata & Governance Log

### 11.1. Errata & Known Limitations Log

- **Benchmark Row 102 Label Defect**: Benchmark index 102 (test table row 267 [photo SHA-256: `5425ce2473621a7341ed48724c0d695f80407e4c6b04f872fc5686c9a4ef905d`]) carries an erroneous 9-character label with 6 trailing digits produced by TrOCR repetition hallucination. Evaluated under dual Clean and Conservative reporting standards.
- **Small Native Resolution**: 90.32% of candidate crops are smaller than $64 \times 128$ in both width and height (median $103 \times 31$ px). Upscaling blur requires resolution-aware synthetic training.
- **Extreme Letter Skew**: 14 of 20 statutory letters have fewer than 30 real instances in the candidate pool (letter `H` has 0 instances). Balanced synthetic generation is mandatory for generalized recognition.
- **Geographic Bias**: 85.32% of candidate crops originate from Ho Chi Minh City (`50/51/52`), requiring geographic balancing prior to nationwide production deployment.

### 11.2. Maintenance & Revision History

| Date | Specification Version | Summary of Dataset Governance Changes | Governance Authority |
|---|---|---|---|
| 2026-04-06 | 0.9.0 | Initial baseline architecture in ADR-0007 | System Architecture Team |
| 2026-10-24 | 0.9.5 | Baseline reproduction & SHA-256 verification | ML Engineering Team |
| 2026-10-25 | 1.0.0 | Enterprise Data Card baseline & Decree 13/2023 compliance | Data Governance Lead |
| 2026-10-26 | 1.1.0 | Full integration of candidate pool (2,826), quarantine (257), 3-way triage (2,391 Group A), resolution percentiles (103x31), character/province distributions, `smoke_128` specification, and synthetic rendering pipeline | Lead Data Governance Specialist |
