# Kaggle Runbook & Security Operations Guide

Enterprise Runbook for Remote Fine-Tuning of Vietnamese License Plate Text Recognizers on Kaggle GPU Infrastructure.

---

## Executive Overview

This runbook defines the standard operational procedures (SOP), security governance, resource budgeting, and execution workflows for fine-tuning Vietnamese license-plate optical character recognition (OCR) models on Kaggle GPU infrastructure.

The project enforces a strict engineering constraint: **ZERO model training occurs on local development workstations** (0 epochs, 0 weight updates). All local verification is strictly confined to CPU baseline evaluations, schema integrity checks, and dry-run static proofs. Real fine-tuning commences exclusively on remote Kaggle cloud accelerators.

This runbook bridges local dataset preparation with remote cloud execution while guaranteeing:

1. **Regulatory Compliance**: Full adherence to Vietnam's Decree 13/2023/ND-CP (Nghị định 13/2023/NĐ-CP) regarding vehicle license plates as protected Personal Data.
2. **Credential Isolation**: Zero storage or exposure of Kaggle API tokens (`kaggle.json`) or environment secrets inside git repositories.
3. **Reproducible Pipeline**: Deterministic dataset versioning with SHA-256 manifest pinning and air-gapped offline package management.
4. **Resilient Execution**: Automatic checkpoint resumption across Kaggle's session duration limits (up to 12 hours [UNVERIFIED - Platform Dependent]).
5. **Fail-Safe Deployment**: Promotion gates and automated rollback procedures preserving the ADR-0007 production baseline.

---

## Section 1: Account Setup & SMS/Phone Verification

Kaggle enforces account tier controls based on mobile phone SMS verification [UNVERIFIED - Platform & Account Dependent]. Unverified accounts cannot access hardware accelerators (NVIDIA GPUs or TPUs) or enable outbound internet connections [UNVERIFIED - Platform Policy]. Verification is performed via the web interface at `https://www.kaggle.com/settings/account`.

### 1.1. Phone Verification Workflow

1. Log in to the designated Kaggle organization or engineer account at `https://www.kaggle.com`.
2. Navigate to **Account Settings**: `https://www.kaggle.com/settings/account`.
3. Scroll to the **Phone Verification** section.
4. Select country code **Vietnam (+84)** and input the official authorized mobile phone number.
5. Solve the visual CAPTCHA challenge and request an SMS One-Time Password (OTP).
6. Enter the 6-digit OTP received via SMS to complete verification.

### 1.2. Platform Quotas and Capabilities Unlocked `[UNVERIFIED - Account & UI Dependent]`

> **OPERATIONAL VERIFICATION NOTICE**:
> Platform quotas, hardware availability, and reset schedules on Kaggle are dynamically managed per account tier and platform load. The parameters listed below reflect documented platform baselines and are designated as **`[UNVERIFIED - Account & UI Dependent]`**. The account owner must verify these values directly within their personal Kaggle account before scheduling production runs.

- **Weekly GPU Allocation**: ~30 hours of complimentary GPU execution time per rolling week `[UNVERIFIED - Platform Dependent]`.
  - *Quota Verification Procedure*: Open any Kaggle Notebook, navigate to the right sidebar (**Notebook Settings** -> **Accelerator**), select a GPU accelerator (e.g., GPU T4 x2), and hover over the quota indicator text (e.g., `GPU quota: X / 30 hrs`) to inspect the exact remaining balance and countdown timer to quota reset.
- **Hardware Accelerators**:
  - **NVIDIA Tesla T4 x2** (Accelerator ID: `NvidiaTeslaT4`): Dual Turing GPUs (default GPU accelerator).
  - **NVIDIA Tesla P100** / **NVIDIA L4** (availability subject to platform regional allocation).
- **Network Access Toggle**: Ability to enable outbound internet access (`"enable_internet": true` in `kernel-metadata.json`) when explicitly authorized. For air-gapped runs, enforce `"enable_internet": false`.
- **Execution Session Caps `[UNVERIFIED - Platform Dependent]`**:
  - Headless batch execution via `kaggle kernels push`: Configurable via CLI flag `-t, --timeout <SECONDS>` (verified in `kaggle kernels push --help`). Platform default cap is up to **12 hours (720 minutes)** `[UNVERIFIED - Platform Dependent]`.
  - Interactive browser sessions: Up to **9 hours** continuous execution with an idle timeout after **60 minutes** of inactivity `[UNVERIFIED - Platform Dependent]`.
  - Ephemeral scratch disk space: Up to **20 GB** in `/kaggle/working` `[UNVERIFIED - Platform Dependent]`.

### 1.3. Verification Troubleshooting

- If SMS delivery fails, wait at least 15 minutes before re-requesting. Do not exceed 3 attempts within 24 hours to prevent telecom security blacklisting.
- Confirm carrier spam filters do not block international application-to-person (A2P) SMS shortcodes.
- If issues persist, submit a support ticket via Kaggle Help Center (`support@kaggle.com`).

---

## Section 2: Kaggle API Token Setup & Workstation Security

The Kaggle API token grants administrative access to the user account, including creating private datasets, launching remote GPU kernels, and pulling proprietary model artifacts.

### 2.1. Generating API Credentials (Official Kaggle Documentation Citation)

According to official Kaggle documentation in `Kaggle/kaggle-api` (`https://raw.githubusercontent.com/Kaggle/kaggle-api/main/docs/README.md`, accessed 2026-10-25):
> *"After login, you can download your Kaggle API credentials at <https://www.kaggle.com/settings/api> by clicking on the 'Generate New Token' button under the 'API' section."*  
> *"Option 4: Legacy API credentials file: From your Kaggle account API tokens settings page (<https://www.kaggle.com/settings/api>), under 'Legacy API Credentials', click on the 'Create Legacy API Key' button to generate a kaggle.json file and store it at ~/.kaggle/kaggle.json."*

1. Navigate to `https://www.kaggle.com/settings/api`.
2. Under the **API** or **Legacy API Credentials** section, click **Create Legacy API Key** (or **Generate New Token**).
3. The browser downloads the authentication JSON file named `kaggle.json`.
4. Inspect the downloaded file structure without committing or copying it into any repository:

```json
{
  "username": "<KAGGLE_USERNAME>",
  "key": "0123456789abcdef0123456789abcdef"
}
```

### 2.2. Workstation Storage and File Permissions

Under no circumstances may `kaggle.json` be placed within this repository or any tracked directory. The file must reside exclusively in the operating system user profile directory with restricted access permissions.

#### POSIX (Linux / macOS) Installation & Hardening

```bash
# Create target directory in user home
mkdir -p ~/.kaggle

# Move downloaded token from Downloads
mv ~/Downloads/kaggle.json ~/.kaggle/kaggle.json

# Restrict permissions: Read and Write ONLY by the file owner
chmod 600 ~/.kaggle/kaggle.json

# Verify file ownership and permissions
ls -l ~/.kaggle/kaggle.json
# Expected output: -rw------- 1 username username ... /home/username/.kaggle/kaggle.json
```

#### Windows PowerShell Installation & Hardening

```powershell
# Create target directory in user profile
$KaggleDir = Join-Path $env:USERPROFILE ".kaggle"
if (!(Test-Path $KaggleDir)) {
    New-Item -ItemType Directory -Path $KaggleDir -Force | Out-Null
}

# Move downloaded token
Move-Item -Path "$env:USERPROFILE\Downloads\kaggle.json" -Destination "$KaggleDir\kaggle.json" -Force

# Lock down NTFS access control: disable inheritance and grant R/W strictly to current user
icacls "$KaggleDir\kaggle.json" /inheritance:r /grant:r "$($env:USERNAME):(R,W)"

# Verify ACL permissions
Get-Acl "$KaggleDir\kaggle.json" | Format-List AccessToString
```

### 2.3. Defense-in-Depth Git Exclusion Strategy

To prevent accidental credential leaks across multi-developer environments, the project enforces a 4-layer gitignore architecture:

1. **Root `.gitignore`** (Repository Root): Excludes `kaggle.json`, `.kaggle/`, `.env`, `.env.*`.
2. **Root `.dockerignore`**: Excludes `kaggle.json`, `.kaggle/`, `training/` from Docker build context.
3. **Subproject `training/.gitignore`**: Excludes `kaggle.json`, `.kaggle/`, checkpoints, and model binaries.
4. **Local Git Exclude (`.git/info/exclude`)**: Developer machine-level exclusion barrier.

Always verify exclusion prior to staging changes:

```bash
git check-ignore -v kaggle.json
# Expected output: .gitignore:170:kaggle.json    kaggle.json
```

### 2.4. Mandatory Identifier Placeholder

All configuration templates, documentation examples, and kernel metadata files committed to the repository must use the placeholder `<KAGGLE_USERNAME>` instead of real account usernames.

---

## Section 3: Private Dataset Upload (`kaggle datasets create/version`)

All license plate crop images collected for training or validation represent personal data under Vietnamese law. Consequently, every dataset uploaded to Kaggle must be explicitly configured as private (`"isPrivate": true`).

### 3.1. Staging Directory Layout

Prepare an isolated staging directory outside the git repository (e.g., `~/staging/vietnamese-plate-manifest`):

```text
staging_dataset/
├── dataset-metadata.json
├── manifest.json
├── manifest.json.sha256
├── README.md
└── images/
    ├── crop_000001.jpg
    ├── crop_000002.jpg
    └── crop_000003.jpg
```

### 3.2. Dataset Metadata Specification

Create `dataset-metadata.json` inside the staging root:

```json
{
  "title": "Vietnamese License Plate Manifest Dataset",
  "id": "<KAGGLE_USERNAME>/vietnamese-license-plate-manifest",
  "licenses": [
    {
      "name": "other"
    }
  ],
  "isPrivate": true
}
```

### 3.3. Integrity Verification via Manifest SHA-256

Prior to uploading, execute integrity verification using the `plate_training` subproject CLI to confirm that every image on disk matches its recorded SHA-256 hash in `manifest.json`:

```bash
# Verify dataset manifest schema and physical image SHA-256 hashes (64KB block reads)
python -m plate_training.cli validate-manifest \
  --manifest staging_dataset/manifest.json \
  --verify-hashes \
  --base-dir staging_dataset/

# Compute SHA-256 checksum of the manifest itself (Linux / macOS)
sha256sum staging_dataset/manifest.json > staging_dataset/manifest.json.sha256

# Verify manifest checksum
sha256sum -c staging_dataset/manifest.json.sha256
```

```powershell
# Verify dataset manifest schema and physical image SHA-256 hashes (Windows PowerShell)
python -m plate_training.cli validate-manifest `
  --manifest staging_dataset\manifest.json `
  --verify-hashes `
  --base-dir staging_dataset\

# Compute SHA-256 checksum of the manifest itself (Windows PowerShell)
Get-FileHash -Algorithm SHA256 staging_dataset\manifest.json |
  ForEach-Object { "$($_.Hash.ToLower())  manifest.json" } > staging_dataset\manifest.json.sha256

# Verify manifest checksum (Windows PowerShell)
$expected = (Get-Content staging_dataset\manifest.json.sha256).Split(" ")[0]
$actual = (Get-FileHash -Algorithm SHA256 staging_dataset\manifest.json).Hash.ToLower()
if ($expected -eq $actual) { Write-Host "Manifest checksum OK" } else { Write-Error "Checksum mismatch" }
```

### 3.4. Uploading via Kaggle CLI

Because a license-plate dataset comprises thousands of small JPEG files, always specify `--dir-mode tar` to package the directory into a single tar archive during upload. This avoids HTTP connection throttling and file dropouts.

```bash
# Initial creation of the Private Dataset
kaggle datasets create -p staging_dataset/ --dir-mode tar

# Publishing an updated version with new verified crops
kaggle datasets version -p staging_dataset/ -m "Append 1200 validated motorcycle plate crops" --dir-mode tar
```

---

## Section 4: Kaggle Kernels CLI Operations

Training runs are initiated, monitored, and retrieved purely via the official Kaggle CLI. This enables fully automated, headless CI/CD execution without manual browser interaction.

### 4.1. Kernel Configuration Metadata

The subproject provides the canonical kernel metadata template at `training/notebooks/kernel-metadata.json`:

```json
{
  "id": "<KAGGLE_USERNAME>/vietnamese-plate-cct-training",
  "title": "Vietnamese License Plate CCT-XS Training",
  "code_file": "kaggle_train.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_tpu": "false",
  "enable_internet": "false",
  "dataset_sources": [
    "<KAGGLE_USERNAME>/vietnamese-license-plate-manifest",
    "<KAGGLE_USERNAME>/plate-training-wheels"
  ],
  "competition_sources": [],
  "kernel_sources": []
}
```

Key configuration flags:

- `"enable_gpu": "true"`: Requests NVIDIA GPU accelerator (T4 x2 or P100).
- `"enable_internet": "false"`: Guarantees air-gapped security, preventing outbound data exfiltration.
- `"is_private": "true"`: Ensures the notebook and its generated logs remain strictly confidential.
- `"dataset_sources"`: Mounts the private manifest images and offline Python wheels under `/kaggle/input/`.

### 4.2. CLI Command Lifecycle

#### Step 1: Pushing and Launching Remote Execution

```bash
# Push notebook and trigger remote GPU container build
kaggle kernels push -p training/notebooks
```

#### Step 2: Automated Status Polling

Monitor kernel execution state using CLI polling. Kaggle kernel statuses transition through `queued` -> `running` -> `complete` (or `error` / `cancelAcknowledged`).

**Linux / macOS Bash Polling Script**:

```bash
#!/usr/bin/env bash
set -euo pipefail

KERNEL_ID="<KAGGLE_USERNAME>/vietnamese-plate-cct-training"
POLL_INTERVAL=120
MAX_WAIT_HOURS=12
MAX_ITERATIONS=$(( (MAX_WAIT_HOURS * 3600) / POLL_INTERVAL ))

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Commencing polling for kernel: ${KERNEL_ID}"

for ((i=1; i<=MAX_ITERATIONS; i++)); do
    STATUS_OUTPUT=$(kaggle kernels status "${KERNEL_ID}")
    CURRENT_STATUS=$(echo "${STATUS_OUTPUT}" | awk '{print $NF}')
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iteration ${i}/${MAX_ITERATIONS}: Status is '${CURRENT_STATUS}'"

    if [[ "${CURRENT_STATUS}" == *"complete"* ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Kernel execution finished successfully."
        exit 0
    elif [[ "${CURRENT_STATUS}" == *"error"* ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Kernel execution failed."
        exit 1
    elif [[ "${CURRENT_STATUS}" == *"cancel"* ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: Kernel was cancelled."
        exit 2
    fi

    sleep "${POLL_INTERVAL}"
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] TIMEOUT: Reached maximum polling duration."
exit 3
```

**Windows PowerShell Polling Script**:

```powershell
$KernelId = "<KAGGLE_USERNAME>/vietnamese-plate-cct-training"
$PollIntervalSec = 120
$MaxWaitHours = 12
$MaxIterations = ($MaxWaitHours * 3600) / $PollIntervalSec
$Iteration = 0

Write-Host "Commencing polling for kernel: $KernelId"

while ($Iteration -lt $MaxIterations) {
    $Iteration++
    $StatusOutput = (kaggle kernels status $KernelId | Out-String).Trim()
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$Timestamp] Iteration $Iteration/${MaxIterations}: $StatusOutput"

    if ($StatusOutput -match "complete") {
        Write-Host "[$Timestamp] Kernel execution finished successfully."
        exit 0
    }
    elseif ($StatusOutput -match "error") {
        Write-Error "[$Timestamp] Kernel execution terminated with an error."
        exit 1
    }
    elseif ($StatusOutput -match "cancel") {
        Write-Warning "[$Timestamp] Kernel was cancelled."
        exit 2
    }

    Start-Sleep -Seconds $PollIntervalSec
}

Write-Error "Timeout waiting for kernel completion."
exit 3
```

#### Step 3: Downloading Outputs and Artifacts

Upon completion, retrieve all exported artifacts (ONNX model, metrics, config, checkpoints) to `training/outputs/`:

```bash
mkdir -p training/outputs
kaggle kernels output <KAGGLE_USERNAME>/vietnamese-plate-cct-training -p training/outputs/
```

---

## Section 5: Kaggle GPU Benchmark Protocol & Kaggle Smoke Run Specification

> **MODEL COMPLEXITY BASELINE**:
> Theoretical throughput estimates are never assumed without empirical verification.
>
> **Verified Model Complexity**:
>
> - Architecture: Compact Convolutional Transformer (CCT-XS) with 18 top-level layers in the full published model (15 top-level layers after dropping 3 region-head layers: `region_pre_pool_transformer_block_1`, `region_seq_pool`, `region`). It features a `CCTTokenizer` (`patch_extractor` Conv2D + MaxPool) and **7 `TransformerBlock`s** (`transformer_block_1..3`, `post_reduce_transformer_block_1..3`, and `region_pre_pool_transformer_block_1` in the 2-head checkpoint; 6 plate-path `TransformerBlock`s active after region-head slicing).
> - Parameter Counts & Initializer Sizes:
>   1. Published 2-head Keras model (`cct_xs_v2_global.keras`): **644,215 parameters** (`643,351` trainable + `864` non-trainable blur kernels).
>   2. Region-free Vietnam single-head Keras model (`drop_region_head=True`): **581,458 parameters** (`62,757` region-head parameters sliced off with `0.0` plate logit difference).
>   3. Production 2-head ONNX model (`cct_xs_v2_global.onnx`): **791,700 float32 initializer values** (differs from 644,215 because the ONNX export unrolls the `patch_extractor` `2x2x96x384` convolution into `147,456` static weights plus graph constants; the single-head ONNX produced by `training/scripts/export_model.py` (with `onnxslim`) has `574,053` initializer values in `68` tensors and is `2,377,330` bytes, measured with the `onnx` package on the exported file).
> - Storage Footprint: Exactly **3,344,292 bytes** (~3.34 MB) for the production 2-head ONNX model.
> - Execution Status: Local execution is strictly non-training (`DRY_RUN = True`). Real remote training execution (`DRY_RUN = False`) on Kaggle GPU hardware is designated as **`[UNVERIFIED]`** until empirically measured via the Kaggle smoke run.

### 5.1. Repeatable GPU Measurement Protocol

Execution throughput (seconds per epoch, samples per second, and peak memory allocation) must be measured dynamically using a dedicated timing callback in `kaggle_train.ipynb`:

```python
import time
import keras


class EpochTimingCallback(keras.callbacks.Callback):
    """Measures exact wall-clock seconds per epoch and logs GPU memory utilization."""

    def on_train_begin(self, logs=None):
        self.epoch_times = []
        self.train_start_time = time.perf_counter()

    def on_epoch_begin(self, epoch, logs=None):
        self.epoch_start = time.perf_counter()

    def on_epoch_end(self, epoch, logs=None):
        elapsed = time.perf_counter() - self.epoch_start
        self.epoch_times.append(elapsed)
        print(f"[BENCHMARK] Epoch {epoch + 1}: {elapsed:.3f} seconds")

    def on_train_end(self, logs=None):
        total_time = time.perf_counter() - self.train_start_time
        avg_epoch = sum(self.epoch_times) / max(len(self.epoch_times), 1)
        print(
            f"[BENCHMARK] Total Training Time: {total_time:.2f}s | "
            f"Mean Epoch Duration: {avg_epoch:.3f}s"
        )
```

### 5.2. Kaggle Smoke Run Technical Specification

The objective of the **Kaggle Smoke Run** is to empirically validate the complete end-to-end execution of the remote training pipeline (`DRY_RUN = False`) on Kaggle GPU infrastructure without depleting weekly compute quotas.

#### 1. Smoke Run Execution Parameters

| Parameter | Specification | Operational Justification |
|---|---|---|
| **Dataset Scale** | Exactly **128 image crops** (64 `train`, 64 `val`) | Minimal footprint (~3 MB RAM); eliminates CPU loading bottleneck; executes in < 5 seconds. |
| **Manifest Compliance** | Validated per `manifest.schema.json` with mandatory `group_id` | Enforces fail-closed validation via `validate_splits` before training commences. |
| **Training Epochs** | Exactly **1 epoch** (`initial_epoch = 0`, `epochs = 1`) | Validates forward pass, backward pass, loss computation, and metric logging without quota waste. |
| **Batch Size** | **64** | Exactly 1 training step and 1 validation step per epoch. |
| **Hardware Accelerator** | **NVIDIA Tesla T4 x2** (Primary) or **NVIDIA Tesla P100** (Fallback) | Turing architecture with Tensor Cores (T4 x2); requested via `--accelerator NvidiaTeslaT4`. |
| **Precision Policy** | `mixed_float16` on T4 x2; strict `float32` on P100 | Leverages Tensor Cores on Turing; avoids software emulation / underflow on Pascal. |
| **Network Setting** | `"enable_internet": "false"` (Air-gapped offline mode) | Complies with Decree 13/2023/ND-CP; uses pre-staged `plate-training-wheels` dataset. |
| **Expected Total Wall Time** | Less than **3 minutes** total session duration | Includes container boot, wheel install, 1 epoch execution, and ONNX export. |

#### 2. Network Setting Trade-off Analysis & Operational Justification

- **Air-Gapped Offline Mode (`"enable_internet": "false"`) [Standard Operational Policy]**:
  - *Mechanism*: Pre-compiled binary wheels (`fast-plate-ocr`, `keras`, `albumentations`, `onnxslim`) and pretrained weights (`cct_xs_v2_global.keras`) are mounted from private Kaggle datasets under `/kaggle/input/`.
  - *Justification*: Guarantees zero data exfiltration risk under Vietnam's Decree 13/2023/ND-CP; provides 100% deterministic, immutable environment independent of upstream PyPI availability; protects against supply-chain tampering.
- **Online Bootstrap Mode (`"enable_internet": "true"`) [Controlled Diagnostic Exception]**:
  - *Mechanism*: Outbound network access enabled to directly download packages via pip.
  - *Justification*: Serves strictly as a diagnostic fallback if offline wheels encounter missing C-library runtime dependencies (e.g., `libGL.so.1`) in an updated Kaggle base image. Once exact pinned wheels are identified and bundled into the private wheel dataset, the pipeline reverts permanently to air-gapped execution.

#### 3. Step-by-Step Smoke Run Execution Workflow

1. **Package the Smoke Dataset**:
   Assemble 128 verified non-frozen plate crops into `staging_smoke_dataset/` with valid `manifest.json` and compute its SHA-256 checksum:

   ```bash
   python -m plate_training.cli validate-manifest \
     --manifest staging_smoke_dataset/manifest.json \
     --verify-hashes \
     --base-dir staging_smoke_dataset/
   ```

2. **Publish the Private Smoke Dataset**:

   ```bash
   kaggle datasets create -p staging_smoke_dataset/ --dir-mode tar
   ```

3. **Configure Kernel Metadata (`training/notebooks/kernel-metadata.json`)**:

   ```json
   {
     "id": "<KAGGLE_USERNAME>/vietnamese-plate-cct-smoke",
     "title": "Vietnamese License Plate CCT-XS Smoke Run",
     "code_file": "kaggle_train.ipynb",
     "language": "python",
     "kernel_type": "notebook",
     "is_private": "true",
     "enable_gpu": "true",
     "enable_tpu": "false",
     "enable_internet": "false",
     "dataset_sources": [
       "<KAGGLE_USERNAME>/vietnamese-plate-smoke-manifest",
       "<KAGGLE_USERNAME>/plate-training-wheels"
     ],
     "competition_sources": [],
     "kernel_sources": []
   }
   ```

4. **Launch Execution via Kaggle CLI**:
   Set `DRY_RUN = False` in `kaggle_train.ipynb`, strip notebook outputs, and push:

   ```bash
   jupyter nbconvert --ClearOutputPreprocessor.enabled=True --inplace training/notebooks/kaggle_train.ipynb
   kaggle kernels push -p training/notebooks -t 600 --accelerator NvidiaTeslaT4
   ```

5. **Poll Kernel Status**:

   ```bash
   kaggle kernels status <KAGGLE_USERNAME>/vietnamese-plate-cct-smoke
   ```

6. **Retrieve and Verify Smoke Artifacts**:

   ```bash
   kaggle kernels output <KAGGLE_USERNAME>/vietnamese-plate-cct-smoke -p training/outputs/smoke_run/
   ```

#### 4. Expected Outputs & Verification Metrics

Upon completion, `/kaggle/working/` (downloaded to `training/outputs/smoke_run/`) must contain:

1. `checkpoints/epoch_001.keras`: Keras 3 format archive containing trained weights, architecture, and AdamW optimizer states (~10.8 MB).
2. `checkpoints/checkpoint_metadata.json`: Metadata tracking epoch count, loss, and accuracy metrics.
3. `exported_models/cct_xs_v2_vn.onnx`: Exported ONNX model graph (single-head, with `onnxslim`: 574,053 float32 initializer values, about 2.38 MB; the published 2-head production file has 791,700 values and is 3,344,292 bytes).
4. `exported_models/cct_xs_v2_vn_plate_config.yaml`: Canonical OCR inference configuration.
5. `run_summary.json`: Verifiable JSON metrics record:

   ```json
   {
     "run_type": "kaggle_smoke_run",
     "accelerator": "NvidiaTeslaT4",
     "epochs_completed": 1,
     "train_samples": 64,
     "val_samples": 64,
     "batch_size": 64,
     "epoch_1_duration_sec": 2.45,
     "train_loss": 0.1245,
     "val_loss": 0.1180,
     "val_plate_acc": 0.9531,
     "val_char_acc": 0.9922,
     "onnx_export_success": true,
     "onnx_parity_max_abs_diff": 1.86e-07,
     "peak_vram_mb": 1150
   }
   ```

#### 5. Empirical Throughput Measurement Log (Post-Smoke Run Template)

| Dataset Scale | Batch Size | Hardware Accelerator | Backend (`KERAS_BACKEND`) | Measured Sec/Epoch `[TO BE MEASURED]` | Peak VRAM `[TO BE MEASURED]` | Verified Parity Diff `[TO BE MEASURED]` |
|---|---|---|---|---|---|---|
| **128 crops (Kaggle Smoke Run)** | 64 | NVIDIA Tesla T4 | `torch` | *Pending Owner Run* | *Pending Owner Run* | *Pending Owner Run* |
| **128 crops (Kaggle Smoke Run)** | 64 | NVIDIA Tesla T4 | `tensorflow` | *Pending Owner Run* | *Pending Owner Run* | *Pending Owner Run* |
| **Target Fine-Tuning Pool** | 64 | NVIDIA Tesla T4 | *Best Backend* | *Projected from Smoke Run* | *Projected from Smoke Run* | *Projected from Smoke Run* |

### 5.3. Diagnostic Runbook: Failure Signatures & Troubleshooting Procedures

If the remote execution fails, inspect the kernel log (`kaggle kernels output`) and apply the structured diagnosis below:

#### Failure Signature 1: CUDA Out-Of-Memory (OOM)

- **Verbatim Error Signature**:

  ```text
  torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 128.00 MiB (GPU 0; 14.75 GiB total capacity; ... free)
  ```

  or Keras / TensorFlow equivalent:

  ```text
  ResourceExhaustedError: OOM when allocating tensor with shape [64, ...]
  ```

- **Root Cause**: Batch size is too large for device memory, or lingering tensors retain computation graphs across iterations.
- **Remediation Procedure**:
  1. Reduce `batch_size` in training config from `64` to `32` or `16`.
  2. Confirm mixed precision is active on Tesla T4: `keras.mixed_precision.set_global_policy("mixed_float16")`.
  3. Ensure gradient arrays are cleared before validation steps.

#### Failure Signature 2: Missing Offline Wheel / Shared C-Library Error

- **Verbatim Error Signature**:

  ```text
  ModuleNotFoundError: No module named 'fast_plate_ocr'
  ```

  or runtime shared library missing:

  ```text
  ImportError: libGL.so.1: cannot open shared object file: No such file or directory
  ```

- **Root Cause**: Offline wheel bundle is missing an indirect dependency, or `opencv-python` was included instead of headless variant requiring X11/OpenGL libraries.
- **Remediation Procedure**:
  1. Ensure wheel bundle uses `opencv-python-headless` instead of `opencv-python`.
  2. Verify wheel ABI compatibility: download wheels targeting `manylinux_2_28_x86_64` and matching Kaggle container Python version (`cp310` or `cp311`).
  3. In `kaggle_train.ipynb`, verify the wheel installation cell executes `pip install --no-index --find-links=/kaggle/input/plate-training-wheels ...` before any library imports.

#### Failure Signature 3: Dataset Mount Path & Input Slug Mismatch

- **Verbatim Error Signature**:

  ```text
  FileNotFoundError: [Errno 2] No such file or directory: '/kaggle/input/vietnamese-plate-manifest/manifest.json'
  ```

- **Root Cause**: The dataset folder name mounted under `/kaggle/input/` differs from the slug declared in `kernel-metadata.json` (Kaggle strips username prefixes and replaces underscores with hyphens).
- **Remediation Procedure**:
  1. Use dynamic path discovery in `kaggle_train.ipynb`:

     ```python
     from pathlib import Path

     input_dir = Path("/kaggle/input")
     manifest_candidates = list(input_dir.glob("**/manifest.json"))
     assert manifest_candidates, (
         f"No manifest.json found under {input_dir}! Contents: {list(input_dir.iterdir())}"
     )
     manifest_path = manifest_candidates[0]
     ```

  2. Inspect directory layout via `ls -la /kaggle/input/`.

#### Failure Signature 4: Data Leakage Guard Hard Failure (`DataLeakageError`)

- **Verbatim Error Signature**:

  ```text
  plate_training.split.DataLeakageError: Split leakage detected! 1 samples match frozen test registry by SHA-256 or pHash Hamming distance <= 4.
  ```

- **Root Cause**: One or more image crops in the smoke dataset originated from the sacred 322-row frozen test set (`sonnetechnology`).
- **Remediation Procedure**:
  1. Re-generate smoke dataset strictly using synthetic plates or independently collected captures.
  2. Execute local leakage check before uploading:

     ```bash
     python -m plate_training.cli validate-splits --manifest staging_smoke_dataset/manifest.json
     ```

#### Failure Signature 5: Corrupted Checkpoint Deserialization Error

- **Verbatim Error Signature**:

  ```text
  zipfile.BadZipFile: File is not a zip file
  ```

  or truncated checkpoint warning:

  ```text
  [WARN] Skipping undersized checkpoint epoch_001.keras (412 bytes <= 1024 bytes, likely aborted write)
  ```

- **Root Cause**: The kernel session was terminated abruptly by platform timeout while writing the `.keras` zip archive, producing an incomplete header.
- **Remediation Procedure**:
  1. The built-in `resolve_latest_checkpoint()` utility automatically filters out files $\le 1024$ bytes and tests zip CRC integrity via `zf.testzip()`.
  2. If all checkpoints in `/kaggle/working/checkpoints/` are invalid, fallback automatically to baseline weights `cct_xs_v2_global.keras` with `initial_epoch = 0`.

#### Failure Signature 6: ONNX Numerical Parity Discrepancy Failure

- **Verbatim Error Signature**:

  ```text
  AssertionError: ONNX parity check failed! max_abs_diff = 2.45e-03 exceeds tolerance 1e-04
  ```

- **Root Cause**: Mismatch between Keras model output scaling (e.g. logits vs softmax), custom layer tracing discrepancy, or dtype mismatch (FP16 output compared against FP32 reference).
- **Remediation Procedure**:
  1. Ensure model export script (`export_model.py`) forces FP32 outputs on the final layer.
  2. Verify input tensor normalizer layer (`[0.0, 1.0]` vs `uint8 [0, 255]`) matches the production configuration exactly.

#### Failure Signature 7: Kaggle API Authentication / Authorization Failure

- **Verbatim Error Signature**:

  ```text
  Unauthorized: 401 - Unauthorized
  ```

  or:

  ```text
  403 - Forbidden: You do not have permission to push kernels to this user account
  ```

- **Root Cause**: Missing or invalid `kaggle.json`, incorrect file permissions (POSIX requires `chmod 600 ~/.kaggle/kaggle.json`), or username slug mismatch between `kaggle.json` and `kernel-metadata.json`.
- **Remediation Procedure**:
  1. Test authentication: `kaggle models list --help`.
  2. Verify file permissions: `ls -l ~/.kaggle/kaggle.json` on Linux/macOS or `Get-Acl` on Windows.
  3. Confirm the `"id"` field in `kernel-metadata.json` matches the authorized account username `<KAGGLE_USERNAME>`.

### 5.4. Optimization and Efficiency Best Practices

To prevent GPU starvation caused by CPU data loading bottlenecks, apply the following optimizations:

#### 1. In-Memory Caching and Asynchronous Prefetching

Because cropped license plate images ($64 \times 128$ RGB) have a small total footprint (10,000 JPEG crops consume ~50 MB), the entire dataset easily fits into host RAM (Kaggle allocates 13–30 GB CPU RAM).

```python
# Keras / tf.data pipeline
dataset = dataset.map(load_and_decode, num_parallel_calls=tf.data.AUTOTUNE)
dataset = dataset.cache()  # Cache all decoded uncompressed arrays in RAM after epoch 1
dataset = dataset.map(augment, num_parallel_calls=tf.data.AUTOTUNE)
dataset = dataset.batch(batch_size).prefetch(buffer_size=tf.data.AUTOTUNE)
```

For PyTorch backend (`KERAS_BACKEND=torch`), configure `DataLoader` with `num_workers=4` and `pin_memory=True` to enable Direct Memory Access (DMA) transfer from host memory to GPU VRAM.

#### 2. Mixed Precision Policy Selection

- **On NVIDIA Tesla T4 x2 (Turing Architecture)**:
  Activate `mixed_float16` to leverage Turing Tensor Cores. This yields a **1.5x–1.8x speedup** with half the activation memory:

  ```python
  import keras

  keras.mixed_precision.set_global_policy("mixed_float16")
  ```

- **On NVIDIA Tesla P100 (Pascal Architecture)**:
  Retain standard `float32`. Pascal lacks dedicated half-precision Tensor Cores; running FP16 on Pascal requires software emulation and loss scaling that does not provide substantial speedups and introduces underflow risks.

#### 3. Early Stopping with Best Weights Restoration

Prevent redundant epochs after metric plateau by tracking full-plate accuracy:

```python
early_stopping = keras.callbacks.EarlyStopping(
    monitor="val_plate_acc",
    mode="max",
    patience=12,
    min_delta=0.001,
    restore_best_weights=True,
    verbose=1,
)
```

Early stopping typically saves **30% to 50% of total training time**, recovering precious weekly quota.

---

## Section 6: 12-Hour Session Limit & Checkpoint Resume

Kaggle enforces a platform ceiling of up to 12 hours (720 minutes) [UNVERIFIED - Platform Dependent] on non-interactive kernel runs. While CCT-XS fine-tuning finishes well within this limit, complex multi-stage architectures or hyperparameter sweeps may require checkpoint resumption across chained sessions.

### 6.1. Epoch Checkpointing Architecture

Configure the ModelCheckpoint callback to save model state, architecture, and AdamW optimizer moments at the end of every epoch into `/kaggle/working/checkpoints/`:

```python
checkpoint_cb = keras.callbacks.ModelCheckpoint(
    filepath="/kaggle/working/checkpoints/epoch_{epoch:03d}.keras",
    save_weights_only=False,
    save_freq="epoch",
    verbose=1,
)
```

Complement checkpoints with an atomic JSON metadata record `checkpoint_metadata.json`:

```json
{
  "last_epoch": 25,
  "best_epoch": 24,
  "best_val_plate_acc": 0.9860,
  "best_val_loss": 0.0385,
  "latest_checkpoint_file": "epoch_025.keras",
  "timestamp": "2026-10-25T04:15:00Z"
}
```

### 6.2. Multi-Session Chaining via `kernel_sources`

To resume from a previously completed or timed-out session:

1. Update `kernel-metadata.json` for the new run by adding the previous kernel slug to `"kernel_sources"`:

   ```json
   {
     "id": "<KAGGLE_USERNAME>/vietnamese-plate-cct-training-part2",
     "kernel_sources": [
       "<KAGGLE_USERNAME>/vietnamese-plate-cct-training"
     ]
   }
   ```

2. When mounted, Kaggle exposes output files from the parent kernel under:
   `/kaggle/input/vietnamese-plate-cct-training/checkpoints/`

### 6.3. Automated In-Notebook Resumption Logic

Place the following initialization logic in `kaggle_train.ipynb` prior to calling `model.fit()`:

```python
import os
import re
import zipfile
from pathlib import Path
import keras


def resolve_latest_checkpoint(
    search_directories: list[Path],
) -> tuple[Path | None, int]:
    """Scans directories for epoch_{epoch:03d}.keras, filters out empty/truncated
    files (st_size <= 1024 bytes), sorts descending by epoch, and tests archive integrity
    via zipfile, falling back to earlier epochs if the latest checkpoint is corrupted.
    """
    candidate_checkpoints: list[Path] = []
    for directory in search_directories:
        if directory.is_dir():
            for p in directory.glob("epoch_*.keras"):
                # Filter out aborted writes (0 bytes or partial headers <= 1024 bytes)
                if p.stat().st_size > 1024:
                    candidate_checkpoints.append(p)
                else:
                    print(
                        f"[WARN] Skipping undersized checkpoint {p.name} "
                        f"({p.stat().st_size} bytes <= 1024 bytes, likely aborted write)"
                    )

    if not candidate_checkpoints:
        return None, 0

    def extract_epoch(path: Path) -> int:
        match = re.search(r"epoch_(\d+)\.keras", path.name)
        return int(match.group(1)) if match else 0

    # Sort descending by epoch number to inspect newest candidates first
    sorted_candidates = sorted(candidate_checkpoints, key=extract_epoch, reverse=True)

    for candidate in sorted_candidates:
        try:
            # Verify zip archive integrity (.keras format is a zip container)
            with zipfile.ZipFile(candidate, "r") as zf:
                corrupted_member = zf.testzip()
                if corrupted_member is not None:
                    print(
                        f"[WARN] Checkpoint {candidate.name} has corrupted zip CRC in "
                        f"'{corrupted_member}'. Skipping to earlier epoch."
                    )
                    continue
            # Passed integrity check
            return candidate, extract_epoch(candidate)
        except (zipfile.BadZipFile, Exception) as exc:
            print(f"[WARN] Skipping corrupted checkpoint {candidate.name}: {exc}")
            continue

    print("[WARN] All candidate checkpoints were corrupted or unreadable.")
    return None, 0


search_paths = [
    Path("/kaggle/working/checkpoints"),
    Path("/kaggle/input/vietnamese-plate-cct-training/checkpoints"),
]

latest_ckpt, resume_epoch = resolve_latest_checkpoint(search_paths)

if latest_ckpt is not None:
    print(f"[RESUME] Found verified uncorrupted checkpoint: {latest_ckpt}")
    print(f"[RESUME] Resuming training from epoch {resume_epoch}...")
    try:
        model = keras.models.load_model(str(latest_ckpt))
        initial_epoch = resume_epoch
    except (zipfile.BadZipFile, Exception) as exc:
        print(f"[WARN] Deserialization failed for {latest_ckpt}: {exc}")
        print("[RESUME] Falling back to initial_epoch = 0 / baseline initialization.")
        model = None
        initial_epoch = 0
else:
    print(
        "[RESUME] No valid checkpoint found. Initializing model from scratch/pretrained baseline..."
    )
    initial_epoch = 0

# Pass initial_epoch to fit:
# history = model.fit(train_ds, validation_data=val_ds, epochs=TOTAL_EPOCHS, initial_epoch=initial_epoch, ...)
```

---

## Section 7: Air-Gapped Offline Wheel Installation & Dependency Management

To eliminate all risks of credential exposure, data leakage, and supply-chain tampering, training notebooks run with outbound internet disabled (`"enable_internet": "false"`). Dependency packages must be bundled as an air-gapped Kaggle Private Dataset.

### 7.1. Kaggle Base Image Environment & Lockfile Scope Clarification

> **CRITICAL ARCHITECTURAL DISTINCTION**:
>
> - `training/requirements-lock.txt`: Strictly hash-pinned lockfile for **34 lightweight packages** (`requirements-ci.txt`) designed solely for fast CPU-only CI gates (`.github/workflows/03-training-check.yml`). It does NOT contain PyTorch, CUDA, Keras, or deep learning libraries.
> - `training/requirements-train.txt`: The comprehensive, pinned specification (all exact `==` pins) governing the complete remote Kaggle GPU training, evaluation, and export stack.

Based on the official upstream container definition (`https://github.com/Kaggle/docker-python`), dependencies fall into two categories:

| Category | Packages | Operational Treatment on Kaggle |
|---|---|---|
| **Pre-Installed in Base Image** | `torch`, `onnx`, `opencv-python-headless`, `pillow`, `pyarrow`, `pandas`, `pydantic`, `jsonschema`, `click`, `PyYAML`, `ImageHash`, `numpy` | Ready out-of-the-box in `/opt/conda`. No internet re-download required. |
| **Must Install / Override via Offline Wheels** | `fast-plate-ocr==1.1.0`, `keras==3.15.1`, `albumentations==2.0.8`, `onnxslim==0.1.98`, `onnxruntime==1.30.0` | Packaged as private wheel dataset (`plate-training-wheels`) and installed with `--no-index`. |

### 7.2. Curating the Wheel Bundle on Workstation

On an internet-connected workstation, download exact binary wheels compiled for Kaggle's Linux container environment (Python 3.10 / manylinux):

```bash
mkdir -p plate-training-wheels
cd plate-training-wheels

# Download targeted wheels with exact pinned versions
pip download \
  --dest . \
  --only-binary=:all: \
  --platform manylinux_2_28_x86_64 \
  --python-version 310 \
  --implementation cp \
  fast-plate-ocr==1.1.0 \
  keras==3.15.1 \
  albumentations==2.0.8 \
  onnxslim==0.1.98 \
  onnxruntime==1.30.0

# Generate cryptographic manifest of all wheel artifacts
sha256sum *.whl > sha256sums.txt

# Inspect generated bundle
ls -la
cat sha256sums.txt
```

### 7.3. Uploading the Wheel Bundle to Kaggle

Initialize and publish the private wheel dataset:

```bash
# Initialize dataset metadata
kaggle datasets init -p .

# Edit dataset-metadata.json:
# Set "id": "<KAGGLE_USERNAME>/plate-training-wheels"
# Set "title": "Plate Training Offline Wheels"
# Set "isPrivate": true

kaggle datasets create -p .
```

### 7.4. Verified In-Notebook Installation

In `kaggle_train.ipynb`, execute the installation cell before importing third-party libraries:

```bash
%%bash
set -euo pipefail

WHEELS_DIR="/kaggle/input/plate-training-wheels"

echo "=== Verifying Wheel Checksums ==="
cd "${WHEELS_DIR}"
sha256sum -c sha256sums.txt

echo "=== Installing Offline Wheels ==="
pip install --no-index --find-links="${WHEELS_DIR}" \
  fast-plate-ocr keras albumentations onnxslim onnxruntime

echo "=== Verifying Package Installation ==="
python -c "import fast_plate_ocr, keras, albumentations, onnxslim, onnxruntime; print('All offline modules loaded successfully.')"
```

---

## Section 8: Rollback Procedure

Deploying a degraded model to production risks vehicle gate lockups, unreadable plates, and service outages. The promotion gate enforces automated tripwires; failing any criterion activates an immediate rollback.

### 8.1. Automated Gate Tripwires

A newly trained candidate model is automatically rejected if any of the following tripwires fire during evaluation:

1. **Exact-Match Accuracy Drop**: String accuracy on the sacred 322-row frozen test dataset falls below the ADR-0007 baseline threshold of **94.72%**.
2. **False Auto-Approval Spike (`wrong_in_auto`)**: Erroneously accepted plates at the production confidence threshold exceed **1.0%** (target: $\le 1.0\%$).
3. **Auto-Review Coverage Regression**: Automated gate throughput drops below **93.0%** (forcing excessive manual operator reviews).
4. **CPU Latency Regression**: Single-image ONNX Runtime inference latency on standard CPU exceeds **33 ms** (or regresses by more than 1.5x against the standalone CCT-XS baseline median of **3.79 ms**, measured on Intel Core i7-12700H, 1 thread; Full Dual-OCR pipeline median is **49.35 ms**).
5. **Numerical Parity Failure**: Maximum absolute error between Keras graph output and exported ONNX graph output exceeds tolerance:
   $$\max |y_{\text{onnx}} - y_{\text{keras}}| > 10^{-4}$$
6. **Data Leakage Detection**: Any sample from `train` or `val` matches a `frozen-test` sample by SHA-256 exact hash or perceptual hash (pHash Hamming distance $\le 4$).

### 8.2. Five-Step Rollback Workflow

```text
[Tripwire Activated]
         │
         ▼
[Step 1: Promotion Gate Halt] ──> Output regression_analysis.json
         │
         ▼
[Step 2: Maintain Production Baseline] ──> Retain ADR-0007 model (SHA-256: 8031afb5...)
         │
         ▼
[Step 3: Quarantine Failed Artifacts] ──> Move candidate to training/outputs/quarantine/
         │
         ▼
[Step 4: Root Cause Analysis] ──> Inspect CER, dirty labels, augmentations, overfit
         │
         ▼
[Step 5: Corrective Re-experimentation] ──> Hyperparameter tuning on isolated branch
```

#### Step 1: Promotion Gate Halt

The evaluation script immediately aborts the export pipeline, sets exit code 1, and writes an error diagnostic file `regression_analysis.json` recording verbatim metric deltas:

```json
{
  "gate_decision": "REJECTED",
  "timestamp": "2026-10-25T05:30:00Z",
  "candidate_exact_match": 0.9317,
  "baseline_exact_match": 0.9472,
  "delta": -0.0155,
  "failed_tripwires": [
    "exact_match_below_baseline_94.72%"
  ]
}
```

#### Step 2: Maintain Production Baseline

The production backend continues running unaffected on the locked ADR-0007 model weights:

- Primary Recognizer: `cct_xs_v2_global.onnx`
  - SHA-256: `8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44`
- Ensemble Secondary: `global_mobile_vit_v2_ocr.onnx`
  - SHA-256: `e2fe5946c02e73901f73d21b3b7223a0c3e3b02059d4964fbf279b01af38d63c`

No files are copied to `PARKING_OCR_MODELS_DIR`.

#### Step 3: Quarantine Failed Artifacts

Relocate candidate weights, configs, and logs to a timestamped quarantine directory:

```bash
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "training/outputs/quarantine/candidate_${TS}"
mv training/outputs/*.onnx training/outputs/*.keras training/outputs/regression_analysis.json \
   "training/outputs/quarantine/candidate_${TS}/"
```

#### Step 4: Root Cause Analysis (RCA)

Conduct structured diagnosis across four failure modes:

- **Label Noise**: Inspect annotator Character Error Rate (CER) on newly added crops. Check for ambiguous or mislabeled characters (e.g., `8` vs `B`, `0` vs `D`).
- **Over-Augmentation**: Determine if synthetic blur, perspective distortion, or cutout destroyed character strokes.
- **Catastrophic Forgetting**: Verify whether fine-tuning on regional license plates degraded performance on standard nationwide plates.
- **Learning Rate Divergence**: Check loss curves for gradient explosion or suboptimal warmup schedules.

#### Step 5: Remediation and Retraining

Adjust hyperparameters (e.g., lower learning rate $10^{-4} \to 3 \times 10^{-5}$, freeze initial tokenizer Conv layers, adjust label smoothing) and trigger a new isolated experiment run.

---

## Section 9: Threat Model & Regulatory Compliance

### 9.1. Legal Classification: Vehicle License Plates as Personal Data

Under **Article 2 of Decree 13/2023/ND-CP (Nghị định 13/2023/NĐ-CP)** of the Government of Vietnam on Personal Data Protection:

> *"Personal data refers to information in the form of symbols, letters, numbers, images, sounds, or equivalent forms in the electronic environment that is associated with a specific person or helps identify a specific person."*

Applied to automated license plate recognition:

- License plate numbers are linked to vehicle registration records containing vehicle owners' full names, national ID (CCCD/CMND), residential addresses, and contact details.
- When combined with capture timestamps and camera geolocation at parking lot entry/exit gates, license plate images allow tracing individuals' movements and physical habits.
- **Statutory Conclusion**: Vehicle license plate crops and transcribed alphanumeric plate strings constitute **Personal Data**.

### 9.2. Five Core Data Protection Principles

All training pipeline components must comply with Article 3 of Decree 13/2023/ND-CP:

| Principle | Legal Requirement | Technical Implementation in ALPR Pipeline |
|---|---|---|
| **1. Purpose Limitation** | Data processed solely for registered, declared purposes. | Data utilized strictly for parking lot access control and OCR accuracy optimization. Commercial redistribution or third-party transfer is strictly forbidden. |
| **2. Data Minimization** | Collect only data strictly necessary for processing. | Input images are tightly cropped to license plate bounding boxes ($64 \times 128$). Vehicle chassis, windshields, driver faces, and surrounding context are eliminated. |
| **3. Lawful Basis / Consent** | Processing requires explicit consent or statutory authorization. | Parking facility terms of service establish lawful processing. External research data must carry explicit commercial licenses (e.g., CC-BY-4.0). |
| **4. Transparency** | Data subjects informed of processing practices. | Processing operations are formally documented in Data Card (`training/docs/data-card.md`) and Model Card (`training/docs/model-card.md`). |
| **5. Security Measures** | Technical and organizational safeguards against data breach. | Air-gapped training (`"enable_internet": false`), private datasets (`"isPrivate": true`), SHA-256 pinning, and log masking (`mask_plate`). |

### 9.3. Data Protection Impact Assessment (DPIA)

In compliance with **Article 24 of Decree 13/2023/ND-CP**, the operating entity must maintain a written DPIA dossier from the commencement of processing and submit one copy to the Department of Cyber Security and High-Tech Crime Prevention (A05) of the Ministry of Public Security within 60 days.

DPIA dossier requirements for the ALPR pipeline:

1. **System Description**: Surveillance camera $\to$ YOLOv9 detector crop $\to$ local Label Studio annotation $\to$ tarball packaging $\to$ Kaggle Private Dataset $\to$ CCT-XS fine-tuning $\to$ ONNX export $\to$ backend integration.
2. **Impact Assessment**: Evaluation of potential harm from credential leakage or unintended plate disclosure.
3. **Mitigating Controls**: Token isolation, 4-tier gitignore protection, static notebook output zeroing, and production log masking (`51F-***.81`).
4. **Data Protection Officer (DPO)**: Contact details of the designated compliance officer.

### 9.4. Threat Vector Analysis & Security Defenses

#### Threat Vector 1: API Token & Credential Leakage

- **Threat**: Accidental commit of `kaggle.json` or inline API keys to public repositories or container images.
- **Impact**: Unauthorized account takeover, exhaustion of weekly GPU quotas, and unauthorized exfiltration of private customer plate datasets.
- **Mitigation Matrix**:
  - Store token exclusively at `~/.kaggle/kaggle.json` (POSIX) or `$env:USERPROFILE\.kaggle\kaggle.json` (Windows) with locked permissions (`chmod 600` / `icacls`).
  - Enforce 4-tier gitignore barriers across root `.gitignore`, root `.dockerignore`, `training/.gitignore`, and `.git/info/exclude`.
  - Use placeholder `<KAGGLE_USERNAME>` in all committed templates and documents.
  - Implement automated pre-commit secret detection matching Kaggle API token regexes:
    - `(?i)kaggle[_-]?(?:api|token|key)?\s*[:=]\s*["\x27][a-f0-9]{32}["\x27]`
    - `\{\s*"username"\s*:\s*"[^"]+"\s*,\s*"key"\s*:\s*"[a-f0-9]{32}"\s*\}`

#### Threat Vector 2: Supply-Chain Compromise & Model Weights Tampering

- **Threat**: Downloading unverified pretrained weights from third-party hubs exposes the pipeline to Trojan/backdoor attacks or remote code execution (RCE) via malicious pickle deserialization (`.pkl`, `.pt`).
- **Impact**: Backdoored models could intentionally misread attacker license plates as VIP/exempt vehicles, bypassing parking barrier access controls without payment.
- **Mitigation Matrix**:
  - Mandate safe serialization formats: **ONNX** (pure computation graph, immune to pickle execution) and **Keras v3 zip** (`.keras`).
  - Prohibit all unverified `.pkl`, `.pt`, and `.pth` weight files.
  - Strict SHA-256 checksum pinning for all baseline models:

| Model Artifact File | Size | Verified SHA-256 Checksum | Origin / License |
|---|---|---|---|
| `cct_xs_v2_global.onnx` | 3,344,292 bytes (~3.34 MB) | `8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44` | fast-plate-ocr (MIT), 791,700 float32 initializer values, float32 |
| `cct_xs_v2_global_plate_config.yaml` | ~2 KB | `0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6` | fast-plate-ocr (MIT) |
| `global_mobile_vit_v2_ocr.onnx` | ~21 MB | `e2fe5946c02e73901f73d21b3b7223a0c3e3b02059d4964fbf279b01af38d63c` | fast-plate-ocr (MIT) |
| `yolo-v9-t-384-license-plates-end2end.onnx` | ~9 MB | `888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8` | open-image-models (Apache-2.0) |

- Enforce numerical parity gate: $\max |y_{\text{keras}} - y_{\text{onnx}}| < 10^{-4}$.
- **PII Governance & Hash Registry Notice**:
  - In strict compliance with Decree 13/2023/ND-CP, no plain-text plate fixtures are committed to git tracking.
  - The split leakage guard registry `training/data/frozen_test_registry.json` operates strictly on a **Hash-Only** architecture, storing only `row_index`, raw image byte `sha256`, and 64-bit perceptual `phash`. Zero alphanumeric plate strings and zero image bitmaps are stored.
  - The existing backend test fixture `tests/parking/fixtures_322_metadata.py` remains the single authorized metadata reference for Django unit tests.

#### Threat Vector 3: Notebook Output & Visual Data Leakage

- **Threat**: Visualizing license plates in Jupyter Notebooks via `plt.imshow()` embeds unmasked images as base64-encoded PNG strings in the `.ipynb` JSON `outputs` array. Committing the notebook leaks private customer data onto public GitHub or Kaggle feeds.
- **Mitigation Matrix**:
  - Ban image rendering calls (`plt.imshow()`, `cv2.imshow()`) in the training notebook.
  - Implement CI static verification asserting zero cell outputs across all notebook cells:

  ```python
  import json
  from pathlib import Path


  def verify_notebook_zero_output(notebook_path: Path) -> None:
      with open(notebook_path, "r", encoding="utf-8") as f:
          nb = json.load(f)
      total_outputs = sum(len(cell.get("outputs", [])) for cell in nb.get("cells", []))
      assert total_outputs == 0, (
          f"Found {total_outputs} unstripped outputs in {notebook_path}!"
      )
  ```

  - Provide pre-commit sanitization command:

  ```bash
  jupyter nbconvert --ClearOutputPreprocessor.enabled=True --inplace training/notebooks/kaggle_train.ipynb
  ```

#### Threat Vector 4: Model Inversion & Membership Inference Attacks

- **Model Inversion Assessment**:
  - The CCT-XS architecture acts as an extreme information bottleneck: it compresses a continuous 24,576-dimensional input tensor ($64 \times 128 \times 3$) into 10 discrete categorical distributions over 37 character tokens ($10 \times 37$).
  - Background pixels, vehicle paint colors, lighting, and textures are discarded by convolutional downsampling and attention pooling.
  - As a purely discriminative model, practical reconstruction of raw vehicle images from model weights is **mathematically infeasible (near-zero practical risk)**.
- **Membership Inference Attacks (MIA)**:
  - Mitigated by heavy data augmentation (Albumentations motion blur, jitter, rotation, cutout) preventing memorization of specific image noise patterns.
  - Mitigated by regularization (Dropout 0.1, weight decay $10^{-4}$, early stopping).
  - Production backend enforces API response hardening: raw probability tensors `[10, 37]` are never exposed to clients; structured logs mask plate text (`mask_plate`).

---

## Section 10: Runbook Checklist & Verification Commands

### 10.1. Pre-Flight Operational Checklist

Before initiating remote GPU execution on Kaggle, complete this verification checklist:

- [ ] **Kaggle Account**: Phone/SMS verification completed; GPU quota confirmed available [UNVERIFIED - Platform Dependent].
- [ ] **Workstation Token**: `kaggle.json` installed at `~/.kaggle/kaggle.json` or `$env:USERPROFILE\.kaggle\kaggle.json` with permissions restricted (`chmod 600` / `icacls`).
- [ ] **Git Repository Check**: `git check-ignore -v kaggle.json` confirms token is excluded from tracking.
- [ ] **Dataset Privacy**: Staging `dataset-metadata.json` configured with `"isPrivate": true`.
- [ ] **Dataset Integrity**: All images verified against `manifest.json` via SHA-256 checksums.
- [ ] **Air-Gapped Wheel Bundle**: `plate-training-wheels` dataset uploaded with verified `sha256sums.txt`.
- [ ] **Kernel Metadata**: `training/notebooks/kernel-metadata.json` has `"enable_gpu": "true"`, `"enable_internet": "false"`, `"is_private": "true"`, and `<KAGGLE_USERNAME>` placeholders configured.
- [ ] **Zero Notebook Outputs**: `kaggle_train.ipynb` sanitized with `nbconvert --ClearOutputPreprocessor`.
- [ ] **Rollback Safeguard**: ADR-0007 baseline weights backed up and verified against SHA-256 catalog.

### 10.2. Command Verification Suite

Execute the following commands to confirm operational readiness:

```bash
# 1. Test Kaggle CLI connectivity
kaggle models list --help > /dev/null && echo "Kaggle CLI operational."

# 2. Verify git exclusion of credentials
git check-ignore -v kaggle.json
git check-ignore -v training/outputs/model.keras

# 3. Verify notebook sanitization (zero outputs)
python -c "
import json
nb = json.load(open('training/notebooks/kaggle_train.ipynb', encoding='utf-8'))
outputs = sum(len(c.get('outputs', [])) for c in nb['cells'])
assert outputs == 0, f'Violation: {outputs} outputs found in notebook'
print('Notebook sanitization verified: 0 outputs.')
"

# 4. Verify manifest schema and unit tests
pytest -c training/pyproject.toml training/tests/test_manifest.py -v
pytest -c training/pyproject.toml training/tests/test_split_leakage.py -v

# 5. Verify local dry-run execution (zero training)
pytest -c training/pyproject.toml training/tests/ -v
```

---

## Section 11: Primary Upstream References & Platform Specifications

1. **Kaggle Official CLI & API Repository**: <https://github.com/Kaggle/kaggle-api>
   - Verbatim CLI specification (`kaggle/cli.py`):
     `"-t, --timeout: Timeout in seconds for kernel execution (default 3600)"`
   - Private dataset specification (`kaggle/api/kaggle_api_extended.py`):
     `"isPrivate": true`
2. **Kaggle Container Environment (Docker Python)**: <https://github.com/Kaggle/docker-python>
   - Official runtime container images for CPU and GPU accelerators.
3. **Vietnam Personal Data Protection Decree**:
   - Decree No. 13/2023/ND-CP of the Government of Vietnam (effective July 1, 2023).
