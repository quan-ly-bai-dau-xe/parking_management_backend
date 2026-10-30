# Promotion Gate Specification for Fine-Tuned License Plate Models

This document defines the formal promotion criteria, statistical verification gates, and emergency rollback procedures governing whether a fine-tuned optical character recognition (OCR) candidate model trained on Kaggle GPU infrastructure qualifies for promotion to the production backend `parking_management_backend`.

---

## 1. Governance & Core Principles

### 1.1. Immutable Gating Principles

Every candidate model produced by Kaggle fine-tuning (Phase 1 Pipeline) must pass all required criteria in this Promotion Gate before being deployed to `PARKING_OCR_MODELS_DIR`.

1. **Automated, Objective Verification**: All criteria are evaluated via automated scripts yielding a binary status: `PROMOTED` or `REJECTED`.
2. **Production Safeguard Invariant**: If a candidate model fails any single mandatory criterion, promotion is blocked immediately and automated tripwires trigger the quarantine procedure.
3. **Mandatory Proposal Tagging**: All target numbers representing proposed candidate requirements in this document are derived from empirical baseline measurements and must explicitly bear the **`[PROPOSAL]`** tag.

---

## 2. Production Baseline Grounding (Empirical Measurements)

All quantitative `[PROPOSAL]` thresholds are grounded in empirical measurements on the sacred 322-row frozen test dataset (SHA-256 `843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b`, verified in ADR-0007 with $\Delta = 0.00\%$ on Intel Core i7-12700H, single thread):

| Benchmark Partition | Measured Metric | Actual Baseline Value | Wilson 95% Confidence Interval | Technical Context & Grounding |
|---|---|---|---|---|
| **Full 322 Rows** | Exact Match (CCT-XS Standalone) | **94.72%** (305 / 322) | **[91.71%, 96.68%]** (CC: [91.52%, 96.80%]) | Pretrained fast-plate-ocr weights (3,344,292 bytes, 791,700 params) |
| | Exact Match (Production Ensemble + Policy) | **95.96%** (309 / 322) | **[93.22%, 97.63%]** (CC: [93.03%, 97.74%]) | Dual-OCR ensemble with positional grammar correction |
| | Automated Throughput (AUTO Coverage) | **93.48%** (301 / 322) | **[90.24%, 95.70%]** (CC: [90.05%, 95.82%]) | At locked minimum character confidence threshold 0.90 |
| | Clean Wrong-in-AUTO Rate (Clean WIA) | **0.997%** (3 / 301) | 1-Sided 95% Upper Bound: **2.47%** (CC: **2.70%**; 2-sided: [0.34%, 2.89%]) | Excluding Row 102 dirty label (requires new holdout to certify <= 1.0%) |
| | Conservative Wrong-in-AUTO Rate | **1.33%** (4 / 301) | 1-Sided 95% Upper Bound: **2.93%** (CC: **3.15%**; 2-sided: [0.52%, 3.37%]) | Penalizing Row 102 dirty label as OCR error |
| **Set 1 (Rows 0..99)** | Exact Match % (Production Pipeline) | **96.00%** (96 / 100) | [90.19%, 98.43%] | Character Accuracy 99.37% (improved by ensemble grammar) |
| **Set 2 (Rows 100..199)** | Exact Match % (Production Pipeline) | **97.00%** (97 / 100) | [91.55%, 98.99%] | Character Accuracy 99.50% (improved by ensemble grammar) |
| **Tuning Split (161 Even Rows)**| AUTO Coverage % / Wrong-in-AUTO % | **93.17%** / **2.67%** | [88.16%, 96.17%] / [1.05%, 6.67%] | Hyperparameter tuning split (ADR-0007) |
| **Test Split (161 Odd Rows)** | AUTO Coverage % / Wrong-in-AUTO % | **95.03%** / **0.65%** | [90.48%, 97.47%] / [0.12%, 3.63%] | Held-out evaluation at locked threshold (consumed in ADR-0007) |
| **CPU Inference Latency** | Standalone CCT-XS ONNX Latency | **Median 3.79 ms / P95 6.16 ms** | $\sigma = 0.00\%$ EM spread over 5 runs | Intel i7-12700H, single thread (replaces legacy unverified estimate) |
| | Full Production Pipeline Latency | **Median 49.35 ms / P95 86.88 ms**| Mean 46.83 ms $\pm$ 1.99 ms (CV = 4.25%) | YOLOv9-t 384 detector + Dual-OCR recognizers |

---

## 3. Formal Promotion Gate Rules

A fine-tuned candidate model must satisfy **all 7 mandatory criteria** simultaneously:

### 3.1. Criterion 1: Absolute String Accuracy & Paired McNemar Gate

- **Verification Rule 1A (Sanity & Regression Guard on 322 Parquet Rows)**:
  $$\text{Exact Match}_{\text{Candidate, 322}} \ge 95.0\%\text{ [PROPOSAL]}$$
  (Equivalent to at least 306 / 322 exact matches, ensuring zero catastrophic forgetting on established benchmark).
  - *Arithmetic Correction*: $309 / 322 = 95.9627\% < 96.0000\%$. To achieve $\ge 96.0\%$, at least $310 / 322 = 96.2733\%$ is required.
  - *Demotion Justification*: The 322-row set is demoted to a sanity guard because 161 odd rows were already consumed in ADR-0007, and $n=322$ has sampling standard error $\text{SE} \approx 1.10\%$ ($1\text{ image} = 0.31\%$), giving a 95% margin of error $\pm 2.15\%$ that exceeds the $+1.28\%$ target margin. Statistical power to detect $\Delta = 1.0\%$ on $n=322$ is merely $17.7\% - 24.4\%$.

- **Verification Rule 1B (NEW Blind Holdout Promotion Gate)**:
  $$\text{Exact Match}_{\text{Candidate, Holdout}} - \text{Exact Match}_{\text{Baseline, Holdout}} \ge +1.0\%\text{ [PROPOSAL]}$$
  with **Paired McNemar Test** achieving statistical significance:
  $$p_{\text{McNemar}} < 0.05\text{ [PROPOSAL]}$$
  - Evaluated on a **NEW blind holdout dataset** ($N \ge 2,000$ images `[PROPOSAL]`) collected by the Owner from real parking cameras, double-annotated with inter-annotator agreement $\text{CER} \le 0.5\%$.
  - Sample size $N=2,000$ is strictly grounded in statistical power analysis ($\alpha = 0.05, 1 - \beta = 0.80$) on discordant pairs ($p_{01}, p_{10}$).

### 3.2. Criterion 2: Wrong-in-AUTO Rate Ceiling (One-Sided 95% Wilson Upper Bound)

- **Verification Rule**:
  $$\text{WIA}_{\text{upper, 95\%}} \le 1.0\%\text{ [PROPOSAL]}$$
  evaluated as the **one-sided 95% Wilson score upper confidence bound** at locked production confidence threshold $\tau_{\text{lock}} = 0.90$.
- **Technical Grounding**:
  - Point estimate evaluation is statistically unsafe: With $n=301$ and 3 errors, the point estimate is $0.997\%$, but the true population error rate upper bound is $2.47\%$ (one-sided 95% Wilson) or $2.70\%$ (with continuity correction).
  - Enforcing $\text{WIA}_{\text{upper, 95\%}} \le 1.0\%\text{ [PROPOSAL]}$ guarantees with 95% statistical confidence that the operational error rate will not breach commercial safety limits.
  - On the NEW Blind Holdout ($N_{\text{AUTO}} \approx 1,860$ samples), meeting this criterion requires observing $\le 10$ errors in the automated stream ($\hat{p} = 0.538\%$, upper bound $= 0.897\% \le 1.0\%$).

### 3.3. Criterion 3: Automated Throughput Floor (AUTO Coverage)

- **Verification Rule**:
  $$\text{AUTO Coverage} \ge 93.0\%\text{ [PROPOSAL]}$$
  at locked production confidence threshold $\tau_{\text{lock}} = 0.90$.
- **Technical Grounding**:
  - If a model is overly conservative resulting in reduced automated throughput (e.g., $< 90.0\%$ `[PROPOSAL]`), the volume of scans routed to `NEEDS_REVIEW` surges, creating vehicle queues at barrier gates and operator overload during peak hours.
  - Actual S4 baseline coverage is 93.17% on Tuning Split, 95.03% on Test Split, and 93.48% across all 322 rows.
  - The $\ge 93.0\%$ `[PROPOSAL]` floor ensures operational throughput remains seamless.

### 3.4. Criterion 4: Slice Regression Tolerance

- **Verification Rule**:
  $$\Delta_{\text{slice}} = \text{Exact Match}_{\text{Baseline, slice}} - \text{Exact Match}_{\text{Candidate, slice}} \le 1.5\%\text{ [PROPOSAL]}$$
  across all evaluation slices: Set 1 (0..99), Set 2 (100..199), 8-character plates, 9-character plates, and regional strata.
- **Technical Grounding**:
  - Deep neural network fine-tuning carries risk of catastrophic forgetting—excelling on newly trained features while degrading on established plate patterns.
  - Enforcing a maximum regression tolerance of $\le 1.5\%$ `[PROPOSAL]` (no more than 1-2 misread samples per 100-sample slice) guarantees uniform quality across all customer segments.

### 3.5. Criterion 5: CPU Inference Latency Budget

- **Verification Rule**:
  - Single-crop recognizer CPU latency:
    $$\text{Latency}_{\text{OCR, CPU}} \le 10.0\text{ ms [PROPOSAL]}$$
    (Baseline measured: Standalone CCT-XS median 3.79 ms, P95 6.16 ms on Intel i7-12700H, single thread).
  - Total end-to-end ALPR pipeline budget:
    $$\text{Latency}_{\text{Total, CPU}} \le 55.0\text{ ms [PROPOSAL]}$$
    (Baseline measured: Full pipeline median 49.35 ms, P95 86.88 ms, mean 46.83 ms $\pm$ 1.99 ms).
- **Technical Grounding**:
  - Pretrained standalone CCT-XS executes with median 3.79 ms on standard CPU.
  - Setting a ceiling of $10.0\text{ ms}$ `[PROPOSAL]` provides headroom for architectural fine-tuning while guaranteeing that full pipeline processing (Detection median ~43.7 ms + Recognition ~4.6 ms + Business Logic ~1 ms) remains under $55.0\text{ ms}$ `[PROPOSAL]`.
  - Conformance ensures deployment on cost-effective CPU servers or edge appliances without requiring dedicated GPU hardware.

### 3.6. Criterion 6: ONNX Numerical Parity

- **Verification Rule**:
  Maximum absolute difference between Keras 3 forward pass and exported ONNX Runtime forward pass on identical input batches:
  $$\max |Y_{\text{ONNX}} - Y_{\text{Keras}}| \le 10^{-4}\text{ [PROPOSAL]}$$
  (Satisfies `atol = 1e-4` and `rtol = 1e-4`).
- **Technical Grounding**:
  - Models are trained using Keras 3 on Kaggle GPU and exported to ONNX for CPU production serving.
  - This check (implemented in `plate_training.onnx_parity.check_onnx_parity`) guarantees graph optimization (`onnxslim`) and operator conversions preserve numerical fidelity.

### 3.7. Criterion 7: Zero Data Leakage

- **Verification Rule**:
  - Exact SHA-256 byte matches between `frozen-test` and `train`/`val`:
    $$\text{Exact SHA-256 Duplicates} = 0\text{ [PROPOSAL]}$$
  - Perceptual hash (pHash) near-duplicates with Hamming distance $\le 4$:
    $$\text{Near-Duplicate Visual Duplicates} = 0\text{ [PROPOSAL]}$$
- **Technical Grounding**:
  - Contaminating training data with test samples invalidates generalization metrics and creates false confidence.
  - Verified via the red-then-green tests in `test_split_leakage.py`. Any violation triggers an immediate `DataLeakageError`.

---

## 4. Promotion Decision Matrix

| # | Evaluation Gate | Baseline Value (S2) | Candidate Requirement | Rigor Level | Action on Failure |
|:---:|---|:---:|:---:|:---:|---|
| **1A** | Regression Guard (322 Rows Parquet) | 94.72% (Standalone) / 95.96% (Ensemble) | **$\ge 95.0\%$ `[PROPOSAL]`** | Hard Block | Reject candidate, retain baseline |
| **1B** | NEW Blind Holdout Gate ($N \ge 2,000$) | Paired Baseline Comparison | **$\Delta \ge +1.0\%$ ($p_{\text{McNemar}} < 0.05$) `[PROPOSAL]`** | Hard Block | Reject candidate, retain baseline |
| **2** | Wrong-in-AUTO (1-Sided 95% Wilson Upper Bound) | 0.997% (Upper Bound: 2.47%) | **$\text{WIA}_{\text{upper, 95\%}} \le 1.0\%$ `[PROPOSAL]`** | Hard Block | Trigger emergency rollback |
| **3** | AUTO Coverage % ($\tau = 0.90$) | 93.48% (301 / 322) | **$\ge 93.0\%$ `[PROPOSAL]`** | Hard Block | Reject candidate |
| **4** | Slice Regression ($\Delta_{\text{slice}}$) | 0.00% | **$\le 1.5\%$ `[PROPOSAL]`** | Hard Block | Quarantine and Root Cause Analysis |
| **5A** | Single-Crop CPU Latency | Median 3.79 ms (P95 6.16 ms) | **$\le 10.0\text{ ms}$ `[PROPOSAL]`** | Hard Block | Reject candidate; optimize architecture |
| **5B** | Full Pipeline CPU Latency | Median 49.35 ms (P95 86.88 ms) | **$\le 55.0\text{ ms}$ `[PROPOSAL]`** | Hard Block | Reject candidate; optimize pipeline |
| **6** | Numerical Parity (ONNX vs Keras) | $1.86 \times 10^{-8}$ | **$\le 10^{-4}$ `[PROPOSAL]`** | Hard Block | Reject ONNX artifact; audit export |
| **7** | Test Split Leakage (SHA-256 / pHash / group_id) | 0 matches | **Exactly 0 matches `[PROPOSAL]`** | Hard Block | Invalidate training dataset; audit splits |

---

## 5. 5-Step Tripwire & Emergency Rollback Workflow

If a candidate model breaches any of the 7 criteria, the automated pipeline triggers the 5-step tripwire protocol in accordance with [Kaggle Runbook Section 8](../../training/docs/kaggle-runbook.md):

```text
[Tripwire Violation Detected]
          │
          ▼
[Step 1: Halt Promotion Gate & Dump regression_analysis.json]
          │
          ▼
[Step 2: Maintain & Lock ADR-0007 Production Baseline]
          │
          ▼
[Step 3: Quarantine Failed Artifacts]
          │
          ▼
[Step 4: Root Cause Analysis (RCA)]
          │
          ▼
[Step 5: Corrective Re-experimentation in Isolated Branch]
```

### Procedure Details

1. **Step 1: Halt Promotion Gate**: Evaluation script aborts with exit code `1` and exports `regression_analysis.json` recording failing metrics.
2. **Step 2: Maintain Production Baseline**: System locks production models:
   - Primary: `cct_xs_v2_global.onnx` (SHA-256 `8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44`).
   - Secondary: `global_mobile_vit_v2_ocr.onnx` (SHA-256 `e2fe5946c02e73901f73d21b3b7223a0c3e3b02059d4964fbf279b01af38d63c`).
   - Zero files copied to `PARKING_OCR_MODELS_DIR`.
3. **Step 3: Quarantine Failed Artifacts**: Move all `.onnx`, `.keras`, and `.yaml` files from the failed run to `training/outputs/quarantine/candidate_YYYYMMDD_HHMMSS/`.
4. **Step 4: Root Cause Analysis (RCA)**: Investigate four primary causes: annotation noise (CER), excessive augmentation distortion, catastrophic forgetting, or learning rate divergence.
5. **Step 5: Corrective Re-experimentation**: Adjust hyperparameters in an isolated branch prior to triggering subsequent Kaggle runs.

---

## 6. Promotion Checklist

Before submitting a promotion pull request to the backend:

- [ ] Calculate and verify SHA-256 hashes for candidate `*.onnx` and `*_plate_config.yaml`.
- [ ] Update Model Card (`training/docs/model-card.md`) with verified empirical metrics.
- [ ] Execute test loading via `PARKING_OCR_MODELS_DIR` in a clean CI environment with zero changes to `apps/parking/services/ocr.py`.
- [ ] Verify 100% pass rate across all 1217 backend Django regression tests.
- [ ] Submit standalone PR containing verified Promotion Gate scorecard.
