# Vietnamese License Plate Labeling and Quality Assurance Guide

Comprehensive annotation guidelines, three-way quality triage protocol, Wilson score interval sample size derivation, and double-labeling verification standards for Vietnamese license-plate crop datasets.

## 1. Objective & Scope

This guide defines transcription rules, quality assurance standards, and review workflows for preparing training, validation, and golden benchmark evaluation datasets for the Compact Convolutional Transformer (CCT) model in `plate_training`.

Target quality benchmarks:

- Double-labeling consensus: Character Error Rate (CER) $\le 0.5\%$ (at least 99.5% character agreement).
- Exact sequence consensus: $\ge 98.0\%$ agreement between independent annotators.
- Inter-annotator reliability: Cohen's kappa $\kappa \ge 0.90$ on exact string transcription.
- Decree 13/2023/ND-CP Compliance: Zero personally identifiable information (PII) stored in public repository code; strict data minimization (tight bounding box crops only, no vehicle occupant faces, no scene landmarks).
- Multi-Frame Grouping: Mandatory `group_id` tagging for multi-frame captures of the same vehicle encounter to prevent cross-split leakage.

## 2. Character Transcription Rules

All ground truth plate annotations must strictly match the normalized uppercase alphanumeric format used by the backend database (`normalize_plate`).

### 2.1. Valid Character Set

The recognition alphabet contains exactly 36 alphanumeric characters:

- Digits: `0`, `1`, `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`
- Uppercase Latin letters: `A` through `Z`

### 2.2. Stripped Delimiters & Formatting

Annotators must NEVER transcribe punctuation marks, separators, or whitespace:

- Strip hyphens (`-`)
- Strip periods and dots (`.`)
- Strip slashes (`/`)
- Strip spaces (` `)
- Strip underscores (`_`)

### 2.3. Transcription Standard

| Visual Plate Pattern | Correct Transcription | Format Requirement |
|---|---|---|
| Standard Civilian 5-Digit | 2 digits + 1 series letter + 5 digits | Punctuation stripped, uppercase alphanumeric |
| Legacy Civilian 4-Digit | 2 digits + 1 series letter + 4 digits | Hyphens stripped, uppercase alphanumeric |
| Joint Venture (`LD`) | 2 digits + `LD` + 5 digits | Punctuation stripped, uppercase alphanumeric |
| Diplomatic (`NG`) | 2 digits + `NG` + 5 digits | Separators stripped, uppercase alphanumeric |

## 3. Plate Orientation Conventions

### 3.1. One-Line (Long Format) Plates

Transcribe characters strictly from left to right.

### 3.2. Two-Line (Square Format) Plates

Transcribe the top line first, immediately followed by the bottom line without spaces or newline characters.

### 3.3. Multi-Frame Group Identifier (`group_id`)

When annotating multiple video frames or burst shots of the same vehicle encounter:

- Annotators must preserve or assign an identical `group_id` to all crops belonging to that vehicle encounter.
- **Reason**: Enforces the fail-closed group leakage guard in `plate_training.split.detect_group_leakage`. Images sharing a `group_id` are strictly prohibited from crossing between `train` and `val` splits.

## 4. Visual Quality Classification

Each sample in the dataset must be tagged with a quality level:

1. **`readable`** (100% Confident):
   - Every character is clearly discernible without ambiguity.
   - Eligible for train, val, and golden benchmark splits.

2. **`ambiguous`** (Context-assisted Deciphering):
   - Characters partially obscured by glare, mud, or angle, but decipherable using statutory Vietnamese vehicle syntax (Circular 24/2023/TT-BCA and Circular 51/2025/TT-BCA: province codes `11`-`99`, series letters `A` through `Z` excluding `I, J, O, Q, R, W`).
   - If characters cannot be verified with certainty, annotators must REJECT the crop rather than guess.
   - Excluded from golden test sets.

3. **`unreadable`** (Unidentifiable):
   - Severely damaged, blurred, or occluded (> 50% missing).
   - Must be flagged as `unreadable` and discarded from all training and evaluation splits.

## 5. Three-Way Label Quality Triage & Review Queue Organization

To maximize annotation efficiency and data reliability, all candidate instances are triaged against three independent readings:

1. **$R_1$**: Machine-generated dataset label (TrOCR output from upstream dataset).
2. **$R_2$**: Production backend dual-OCR ensemble (`FastAlprPlateRecognizer`).
3. **$R_3$**: Published CCT-XS benchmark model (`cct_xs_v2_global`).

### 5.1. Triage Categories

- **Group A (High Confidence Consensus)**:
  $R_1 == R_2 == R_3$ and the reading strictly satisfies Vietnamese civilian car one-line syntax (Circular 79/2024/TT-BCA and Circular 51/2025/TT-BCA).
  Eligible for provisional training workflows subject to statistical quality assurance.
- **Group B (Disagreements & Recoverable)**:
  Any discrepancy between $R_1$, $R_2$, and $R_3$, where at least one reading presents a plausible or recoverable civilian car plate.
  Requires 100% human double-annotation before inclusion in training datasets.
- **Group C (Invalid or Out-of-Scope)**:
  Non-civilian or invalid formats (military series, special series `LD`/`NG`, central agency code `80`, motorbike syntax, unreadable crops).
  Permanently excluded from training datasets.

### 5.2. Risk-Ordered Review Batches (Label Studio Kit)

Label Studio review tasks are organized into three sequential batches ordered strictly by quality risk:

1. **Batch 0 (GOLD Benchmark Test Set)**:
   All 322 frozen-test benchmark images. Evaluated first with 100% double-annotation to establish ground truth calibration.
2. **Batch 1 (Group B Disagreements)**:
   100% of candidate pool instances displaying reading discrepancies.
3. **Batch 2 (Group A Statistical QA Sample)**:
   A statistically sized random sample of Group A ($n \ge 381$) to empirically bound the residual error rate of the automated consensus.

## 6. Mathematical Derivation of Group A Sample Size ($n \ge 381$)

When accepting Group A instances based on 3-way machine consensus, we require statistical assurance that the residual error rate $p$ is bounded below $1\%$ ($p < p_{\text{target}} = 0.01$) at a $95\%$ confidence level ($\alpha = 0.05$).

### 6.1. Wilson Score Interval Formulation

For a binomial parameter $p$ observed in a sample of size $n$ with sample proportion $\hat{p} = x / n$, the Wilson score interval derives from the Wald score test inversion:

$$\frac{|\hat{p} - p|}{\sqrt{\frac{p(1-p)}{n}}} \le z$$

Squaring both sides yields the quadratic inequality in $p$:

$$(\hat{p} - p)^2 \le z^2 \frac{p(1-p)}{n}$$

$$\left(1 + \frac{z^2}{n}\right) p^2 - 2\left(\hat{p} + \frac{z^2}{2n}\right) p + \hat{p}^2 \le 0$$

The general upper bound $p_U$ of this interval is:

$$p_U = \frac{\hat{p} + \frac{z^2}{2n} + z \sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$

### 6.2. Analytical Derivation Under Zero Observed Errors

When the human audit of the random sample discovers **zero errors** ($x = 0 \implies \hat{p} = 0 / n = 0$):

1. **Numerator Simplification**:
   $$\text{Numerator} = 0 + \frac{z^2}{2n} + z \sqrt{0 + \frac{z^2}{4n^2}} = \frac{z^2}{2n} + z \left(\frac{z}{2n}\right) = \frac{z^2}{2n} + \frac{z^2}{2n} = \frac{z^2}{n}$$

2. **Denominator Simplification**:
   $$\text{Denominator} = 1 + \frac{z^2}{n} = \frac{n + z^2}{n}$$

3. **Closed-form Upper Bound**:
   $$p_U = \frac{\frac{z^2}{n}}{\frac{n + z^2}{n}} = \frac{z^2}{n + z^2}$$

### 6.3. Exact Sample Size Calculation

To guarantee that the upper bound remains strictly below $p_{\text{target}} = 0.01$:

$$\frac{z^2}{n + z^2} < p_{\text{target}}$$

$$z^2 < p_{\text{target}} (n + z^2)$$

$$z^2 (1 - p_{\text{target}}) < p_{\text{target}} \cdot n$$

$$n > z^2 \left(\frac{1}{p_{\text{target}}} - 1\right)$$

Substituting standard statistical constants:

- Confidence level $95\%$ ($\alpha = 0.05$, two-tailed): standard normal quantile $z = \Phi^{-1}(0.975) = 1.959964$.
  $$z^2 = (1.959964)^2 = 3.841459$$
- Target maximum error rate: $p_{\text{target}} = 0.01 \implies \frac{1}{0.01} - 1 = 100 - 1 = 99$.

Computing the exact product:

$$n > 3.841459 \times 99 = 380.3044$$

Rounding up to the nearest integer:

$$\mathbf{n \ge 381}$$

*(Note on Rule-of-Three: The heuristic rule $3/n < 0.01 \implies n > 300$ underestimates the required sample size because it approximates the Poisson tail. The Wilson score formulation provides the exact binomial boundary).*

## 7. Double-Labeling Protocol & Inter-Annotator Metrics

To eliminate human error, all review batches enforce independent double-annotation:

```text
       [Cropped License Plate Image]
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   [Annotator A1]          [Annotator A2]
         │                       │
         └───────────┬───────────┘
                     ▼
         [Automated Parity Check]
                     │
           A1 == A2 (CER <= 0.5%)?
          /                      \
        YES                       NO
        /                          \
   [Consensus Approved]     [Dispute Arbitration by Lead CV Engineer]
        │                                  │
        └────────────────┬─────────────────┘
                         ▼
             [Dataset Manifest Commit]
```

### 7.1. Quality Metrics & Acceptance Thresholds

1. **Character Error Rate (CER)**:
   Normalized Levenshtein edit distance over total reference character length:

   $$\text{CER}(A_1, A_2) = \frac{\sum_{i=1}^N \text{Levenshtein}(A_{1,i}, A_{2,i})}{\sum_{i=1}^N \text{len}(A_{1,i})}$$

   **Acceptance Target**: $\text{CER} \le 0.5\%$ (character concordance $\ge 99.5\%$).

2. **Exact Sequence Agreement ($P_o$)**:
   Fraction of plates where Annotator 1 and Annotator 2 match character-for-character:

   $$P_o = \frac{1}{N} \sum_{i=1}^N \mathbb{I}(A_{1,i} == A_{2,i})$$

   **Acceptance Target**: $P_o \ge 98.0\%$.

3. **Cohen's Kappa ($\kappa$)**:
   Chance-corrected inter-annotator agreement coefficient on sequence transcription:

   $$\kappa = \frac{P_o - P_e}{1 - P_e}$$

   where $P_e$ is the expected chance agreement.
   **Acceptance Target**: $\kappa \ge 0.90$ (indicating almost perfect agreement).

## 8. Disagreement Arbitration Rules

When Annotator $A_1$ and Annotator $A_2$ produce conflicting transcriptions:

1. **Automated Quarantine**: The item is routed to the arbitration queue.
2. **Context Inspection**: The Lead Annotator or Senior Computer Vision Engineer inspects the crop alongside high-resolution vehicle context.
3. **Ambiguity Handling**:
   - If a character cannot be conclusively determined (e.g. mud splatter obscuring `8` vs `B` or glare obscuring `0` vs `D`), the crop is marked `ambiguous` or `unreadable`.
   - Guessing is strictly prohibited. Unreadable crops are dropped from training splits.
4. **Resolution Recording**: The arbitrated ground truth is finalized, and error patterns are catalogued to improve annotator training.

## 9. Annotator-Hours Estimate

Effort estimation is derived directly from physical item counts across the three review batches.

### 9.1. Baseline Assumptions

- Standard review & transcription confirmation: **10 seconds per item**.
- Disagreement inspection & lead arbitration: **30 seconds per item**.
- Double-labeling factor: **2 annotators per item**.

### 9.2. Item Breakdown & Resource Calculation

| Batch | Description | Items | Annotations ($2\times$) | Review Time (10s) | Est. Disputes | Arbitration Time (30s) | Subtotal Hours |
|---|---|---|---|---|---|---|---|
| **Batch 0** | Frozen Test GOLD | 322 | 644 | 6,440 s (1.79 h) | ~17 (5.3%) | 510 s (0.14 h) | **1.93 h** |
| **Batch 1** | Group B Pool Disputes | 121 | 242 | 2,420 s (0.67 h) | ~24 (19.8%) | 720 s (0.20 h) | **0.87 h** |
| **Batch 2** | Group A Statistical Sample | 381 | 762 | 7,620 s (2.12 h) | ~3 (0.8%) | 90 s (0.03 h) | **2.14 h** |
| **Total** | Full Review Campaign | **824** | **1,648** | **16,480 s (4.58 h)** | **~44** | **1,320 s (0.37 h)** | **4.94 h** |

**Summary**: The full human review campaign comprises **824 unique items** requiring **1,648 primary annotation actions** and approximately **44 arbitration actions**, totaling **4.94 person-hours** (~5 person-hours, or ~2.5 calendar hours for a two-person annotation team).

## 10. Label Studio Integration

The review kit uses the standardized Label Studio template configuration in `training/docs/label-studio-template.xml`:

- Pre-annotated tasks are generated via `plate_training.triage.generate_label_studio_tasks`.
- Completed annotations are converted to manifest schema format via `plate_training.triage.convert_label_studio_export`.
- Tasks present reference suggestions from automated readings to accelerate transcription while preserving blind verification integrity.
