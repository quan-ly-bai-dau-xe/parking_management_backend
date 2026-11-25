# ADR-0011: Background Gate Worker Process Architecture for Headless Stream Processing and Automated Barrier Control

- **Status**: Accepted
- **Date**: 2026-11-08
- **Deciders**: Owner, Team Lead, Backend & Computer Vision Engineers
- **Technical Context**: Round 88 Headless Gate Automation, OpenCV VideoCapture Stream Ingestion, Pure Decision Policy, Dual-Mode Barrier UI, PostgreSQL Session Advisory Locks

---

## 1. Context & Problem Statement

Prior to Round 88 (PR #48 backend, PR #38 frontend), license plate recognition and barrier management operated strictly through a browser-driven, human-in-the-loop workflow:
1. An operator kept a browser tab open (`/camera-scanner` or `GateCameraControlModal`), which grabbed camera frames (~1 frame/second) and uploaded them as multipart payloads to `POST /api/v1/parking/plate-scans/?preview=true`.
2. The browser ran a 3-of-4 frame voting filter, and an operator manually clicked "Áp dụng" followed by "Xác nhận vào/ra" to complete check-in or check-out.

**Operational & Architectural Deficiencies**:
- **Lack of Autonomy (No Headless Mode)**: The facility could not operate 24/7 without an active browser tab open on an operator's workstation.
- **Latency & Worker Pool Contention**: Continuous frame uploads over HTTP consumed substantial web server CPU (47–63 CPU-ms per scan; saturation knee point at 60–70 scans/sec under Gunicorn 4 workers x 4 threads, p95 latency 0.7–1.4s). Camera traffic directly risked starving user-facing Web API endpoints (HTTP 503).
- **Manual Overhead for Registered Vehicles**: Monthly and subscription ticket holders (`ACTIVE`) required manual operator clicks, creating barrier bottlenecks during rush hours.

**Round 88 Objectives & Empirical Outcomes (Retained in Round 89 & Round 90)**:
- **R-A (Lower Latency & Higher Capacity)**: **PARTIAL** (Measured knee point at 16 cameras per worker process: Round 88 baseline p95 = 1714ms, exceeding 1500ms target; Round 90 3-run benchmark range: p50: 1112.47–1144.49 ms, p95: 1217.23–1304.13 ms, median p95 = 1226.98 ms; 32 cameras collapse at p95 ~95.3s; status strictly retained as PARTIAL).
  - At 1 camera: $p50 = 1098$ms, $p95 = 1122$ms, 0 missed vehicles.
  - At 8 cameras: $p50 = 1103$ms, $p95 = 1198$ms, 0 missed vehicles.
  - At 16 cameras: Round 88 baseline $p50 = 1221$ms, $p95 = 1714$ms (exceeds 1500ms target by +214ms), 0 missed vehicles, CPU 552%. Round 90 3-run range (3x >= 3 min): $p50 = 1112.47\text{–}1144.49$ ms, $p95 = 1217.23\text{–}1304.13$ ms, median $p95 = 1226.98$ ms, 0 missed vehicles.
  - At 32 cameras: Single process collapses ($p50 = 34$s, $p95 \approx 95.3$s, 130 of 160 vehicles missed, CPU 704%).
- **R-B (Headless Operation)**: **DONE** (Autonomous stream ingestion and barrier decision without browser UI).
- **R-C (Auto-Apply Policy)**: **DONE** (Pure decision function with 0-click check-in for subscribers, fee 0 check-out, staff hold for payment/unregistered).
- **R-D (Architecture Splitting)**: **DONE** (Split by process role within single codebase via `python manage.py run_gate_worker` under `gate-worker` compose profile).

---

## 2. Decision Outcome

We decided to **split the system by Process Role** within the existing repository and container image, introducing a dedicated, long-running `gate-worker` process, and reject a separate network microservice.

### 2.1. Process-Role Split & Compose Profile (`gate-worker`)

- **Unified Codebase & Image**: Implemented as a Django management command `python manage.py run_gate_worker` residing in `apps/parking/management/commands/run_gate_worker.py`. It uses the exact same Docker image, dependencies, models, and PostgreSQL 18.6 database as the Web API.
- **Docker Compose Profile**: Declared in `docker-compose.yml` under `profiles: ["gate-worker"]`. The default command `docker compose up` remains strictly unchanged (launching only `db` and `web`). The worker is started explicitly via `docker compose --profile gate-worker up`.
- **Resource Isolation**: Isolates CPU-heavy ONNX runtime execution from Gunicorn web workers. Heavy camera streams cannot degrade Web API responsiveness, and web traffic spikes cannot starve camera processing.

### 2.2. Camera Stream Ingestion & Zero-Credential Persistence

- **Native OpenCV Ingestion**: The worker pulls camera streams directly via `cv2.VideoCapture` from `opencv-python-headless` (v5.0.0.93), already provided by `fast-alpr[onnx]==0.4.0`. Supports HTTP MJPEG streams (e.g. DroidCam `http://HOST:PORT/video`) and RTSP streams without adding any new dependency.
- **Credential Protection**: The mapping from gate code to stream URL is configured exclusively via an environment variable (`GATE_WORKER_STREAMS` in JSON format). Stream URLs containing credentials (basic auth, local IPs) are **never stored in PostgreSQL, never logged, and never exposed via any API endpoint**.

### 2.3. High-Throughput & Low-Latency Stream Architecture

1. **Newest-Frame-Wins**: Each camera is assigned an independent reader thread maintaining a single-frame buffer (`latest frame only`). Outdated frames are overwritten immediately, eliminating backlog queues and latency spikes.
2. **Cheap Motion Pre-filter**: Before invoking OCR, the worker calculates the Mean Absolute Difference (MAD) against a 64x64 grayscale downscaled thumbnail. If pixel difference is below threshold (`MAD < 5.0`), OCR inference is bypassed. OCR frequency is capped per stream (default 2–3 fps).
3. **Shared ONNX Runtime Session**: A single `PlateRecognizer` instance per worker process is shared behind a concurrency semaphore (`PARKING_OCR_CONCURRENCY_LIMIT = 4`), configured with `ONNX_INTRA_OP_THREADS = 1`, `ONNX_INTER_OP_THREADS = 1`, and `ONNX_ALLOW_SPINNING = 0` to prevent CPU core starvation.
4. **Stable Temporal Voting**: Requires 3 identical normalized license plates out of the last 4 consecutive recognized frames before making a decision.
5. **Decoupled Snapshot Uploads**: The database transaction executes on the critical path. Snapshot uploads to Cloudinary are dispatched asynchronously via `SnapshotUploader` (`ThreadPoolExecutor`, bounded JPEG `<= 1280`px quality 85, `5.0`s timeout; TL-73); on success `entry_image_url`/`exit_image_url` is updated on the session, and on failure it stays empty while appending a separate failure event with action `GATE_AUTO_SNAPSHOT_FAILED` and sanitized `snapshot_error` reason to `activity_log` (preserving single decision row invariant, TL-82) without delaying the barrier.
6. **Optimized Browser Mode**: When operating via the browser fallback, frames use `MAX_LONG_SIDE = 960` (`JPEG_QUALITY = 0.85`) with adaptive polling intervals — empirically verified across all 4 real barrier/bike clips based on the 99-frame human-annotated ground truth of Round 90 (TL-85) where 960px @ 0.85 achieved 94/99 ground-truth accuracy with a 20% size reduction and 21.7% latency speedup over the 1280px setting of Round 89.

### 2.4. Per-Camera State Machine

Each managed camera stream executes through a deterministic state machine:

```
                               +------------------+
                               |     OFFLINE      |<-----------------------+
                               +------------------+                        |
                                 |              ^                          |
                    (connect ok) |              | (reconnect fail > Ns)    |
                                 v              |                          |
                               +------------------+                        |
               +---------------|     STREAMING    |                        |
               |               +------------------+                        |
               |                 |              ^                          |
               |    (motion/OCR) |              | (cooldown expires)       |
               |                 v              |                          |
(stream read   |               +------------------+                        |
 error / frame |               | DECIDED_COOLDOWN |                        |
 timeout)      |               +------------------+                        |
               |                 |                                         |
               |                 | (stream read error / frame timeout)     |
               |                 v                                         |
               |               +------------------+                        |
               +-------------->|     DEGRADED     |------------------------+
                               +------------------+ (backoff reconnects)
```

- **`OFFLINE`**: No stream connection or no active worker holding the gate's PostgreSQL session advisory lock.
- **`STREAMING`**: Camera stream active, reader thread ingesting frames, motion pre-filter evaluating.
- **`DECIDED_COOLDOWN`**: Decision reached and applied. Cooldown period (30s normal, 60s on `EXECUTION_FAILED` per TL-74) active to prevent repeated duplicate event emission while vehicle is stationary. Cooldown is tracked in-process by `PlateVoter` per `(gate_id, normalized_plate)` pair; the camera reader thread continues ingesting and evaluating subsequent vehicles without pausing the stream.
- **`DEGRADED`**: Stream disconnected or frame read error (triggered directly from `STREAMING` or from `DECIDED_COOLDOWN`). Worker attempts exponential backoff reconnection (`initial=2s`, `max=30s`).

#### Pending Vehicle Liveness & Still-Seen Hysteresis (TL-103)

To prevent phantom check-ins or phantom wallet debits after a held vehicle leaves the barrier, `GateWorkerCoordinator` tracks monotonic `first_seen_at` and `last_seen_at` per `(gate_id, normalized_plate)` inside `_pending_entries` (walk-in `UNREGISTERED_VEHICLE`) and `_pending_exits` (`WALLET_INSUFFICIENT`), protected by a `threading.RLock` (`_pending_lock`, never held across DB or OCR I/O) and bounded to `DEFAULT_MAX_PENDING_PER_GATE = 50` items per gate (evicting expired entries first, then oldest by `(last_seen_at, first_seen_at)`):

1. **Continuous Sighting Refresh**: Every normalized OCR plate reading at that gate—including readings skipped by `PlateVoter` cooldown, partial `< 3/4` votes, repeated `HOLD` evaluations, and periodic stationary `NO_MOTION` presence-probe OCR frames (`>= GATE_WORKER_PENDING_RECHECK_SECONDS`)—refreshes `last_seen_at` without resurrecting expired items.
2. **Active Re-check Window (`<= GATE_WORKER_PENDING_SEEN_SECONDS`, default `20`s)**: Re-evaluation queries run every `GATE_WORKER_PENDING_RECHECK_SECONDS` (`5.0`s default) only while `now - last_seen_at <= 20s`, and autonomous `check_in_vehicle` / `check_out_vehicle` execution re-verifies freshness plus per-key `in_flight` right before the atomic DB transaction (where `check_out_vehicle` also re-locks the open session via `select_for_update()` and recomputes the tariff).
3. **Silent Hysteresis Wait (`(20s, 60s]`)**: When `20s < now - last_seen_at <= 60s`, re-check skips immediately with zero DB queries, zero log entries, and zero actions while keeping the pending item alive in case of brief occlusion.
4. **Dual Eviction Limits**: Pending entries/exits are evicted when **either** `now - last_seen_at > GATE_WORKER_PENDING_SEEN_SECONDS * 3` (`60`s unseen) **or** `now - first_seen_at > GATE_WORKER_PENDING_MINUTES * 60` (`900`s total wait). Subsequent reappearance starts a fresh pending cycle.

### 2.5. Pure Auto-Apply Decision Matrix (`decide_gate_action`)

The core business logic is encapsulated in a pure, side-effect-free function `decide_gate_action(...)`, mirrored identically on backend and frontend:

| ID | Direction | Gate Active & Auto | 3/4 Stable | Review Status | AI Conf $\ge 90\%$ | Blacklisted | Registered | Open Session | Slot Available | Fee Preview | Action (`action`) | Audit Action (`audit_action`) | Reason Code |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **1** | Any | False | * | * | * | * | * | * | * | * | `HOLD` | `None` | `GATE_INACTIVE` / `AUTO_SCAN_DISABLED` |
| **2** | Any | True | False | * | * | * | * | * | * | * | `HOLD` | `None` | `PLATE_UNSTABLE` |
| **3** | Any | True | True | != AUTO | * | * | * | * | * | * | `HOLD` | `GATE_AUTO_NEEDS_STAFF` | `NEEDS_REVIEW` |
| **4** | Any | True | True | AUTO | False | * | * | * | * | * | `HOLD` | `None` | `LOW_CONFIDENCE` |
| **5** | Any | True | True | AUTO | True | True | * | * | * | * | `HOLD` | `GATE_AUTO_NEEDS_STAFF` | `BLACKLISTED` |
| **6** | `IN` | True | True | AUTO | True | False | * | True | * | * | `HOLD` | `GATE_AUTO_NEEDS_STAFF` | `OPEN_SESSION_ALREADY_EXISTS` |
| **7** | `IN` | True | True | AUTO | True | False | False | False | * | * | `HOLD` | `GATE_AUTO_NEEDS_STAFF` | `UNREGISTERED_VEHICLE` |
| **8** | `IN` | True | True | AUTO | True | False | True | False | False | * | `HOLD` | `GATE_AUTO_NEEDS_STAFF` | `NO_AVAILABLE_SLOT` |
| **9** | `IN` | True | True | AUTO | True | False | True | False | True | * | **`AUTO_CHECK_IN`** | **`GATE_AUTO_CHECK_IN`** | `VALID_REGISTERED` |
| **10**| `OUT`| True | True | * | * | * | * | False | * | * | `HOLD` | `GATE_AUTO_NEEDS_STAFF` | `NO_OPEN_SESSION` |
| **11a**| `OUT`| True | True | AUTO | >= thresh | False | * | True | * | > 0.00 (ví đủ & ACTIVE) | **`AUTO_CHECK_OUT`** | **`GATE_AUTO_CHECK_OUT`** | `VALID_WALLET_PAID` |
| **11b**| `OUT`| True | True | AUTO | >= thresh | False | * | True | * | > 0.00 (có ví nhưng thiếu/khóa) | `HOLD` | **`GATE_AUTO_PAYMENT_REQUIRED`** | `WALLET_INSUFFICIENT` |
| **11c**| `OUT`| True | True | AUTO | >= thresh | False | * | True | * | > 0.00 (không có ví) | `HOLD` | **`GATE_AUTO_PAYMENT_REQUIRED`** | `FEE_PAYMENT_REQUIRED` |
| **12**| `OUT`| True | True | * | * | * | * | True | * | == 0.00 | **`AUTO_CHECK_OUT`** | **`GATE_AUTO_CHECK_OUT`** | `VALID_FEE_ZERO` |

*Note on Audit Logging*: Transient voting states (`PLATE_UNSTABLE`, `LOW_CONFIDENCE`) and inactive gates record `Audit Action: None` to prevent spamming `activity_log` on noisy intermediate video frames. All definitive automated decisions resulting in `HOLD` (`NEEDS_REVIEW`, `BLACKLISTED`, `OPEN_SESSION_ALREADY_EXISTS`, `UNREGISTERED_VEHICLE`, `NO_AVAILABLE_SLOT`, `NO_OPEN_SESSION`) record `GATE_AUTO_NEEDS_STAFF` with their distinct `Reason Code`, fulfilling Decision 4 and ensuring the telemetry API `last_auto_event` alerts operators in Viewer Mode.

### 2.6. Audit Logging & Concurrency Control

- **Headless Audit**: Automated actions populate `recognition_source = 'AI'`, `entry_handled_by = NULL`, `exit_handled_by = NULL` in `vehicle_entry_exit_log`.
- **Immutable Activity Log**: Automated decisions append an entry to `activity_log` with `actor_account_id = NULL` and masked license plates (e.g. `30A***35`).
- **Single-Worker Gate Ownership**: To prevent race conditions across multiple worker replicas, each gate is protected by a PostgreSQL session advisory lock:
  ```sql
  SELECT pg_try_advisory_lock(1195463749, gate_id);
  ```
  (`1195463749` is `'GATE'` in ASCII). If a replica fails to acquire the lock, it skips that gate and logs a notice.
- **Worker Liveness & Cacheless Telemetry (TL-72, TL-80)**: Because web and worker processes run in separate containers without a shared cache, `GET /api/v1/parking/gates/` queries `pg_locks` (`locktype = 'advisory'`, `classid = 1195463749`, `objsubid IN (1, 2)`, `granted = true`) in a single batch query to determine `worker_online`. To prevent cross-database interference on shared PostgreSQL instances where another database might hold locks of the same classid, the query joins `pg_database` with `d.datname = current_database()` (TL-80, G9d). Per PostgreSQL documentation (`https://www.postgresql.org/docs/18/explicit-locking.html`, `https://www.postgresql.org/docs/18/view-pg-locks.html`, accessed 2026-11-12: *"Once acquired at session level, an advisory lock is held until explicitly released or the session ends."*), any `SIGKILL` or container crash immediately closes the dedicated TCP socket and releases the lock, causing the API to report `worker_online: false` and pure-read map `camera_status: "OFFLINE"` without mutating `parking_gate.row_version`. `last_auto_event` is queried solely from `activity_log` via `DISTINCT ON (entity_id)`.
- **Dynamic Gate Config Refresh & Full Reconciliation (TL-75, TL-80)**: Every 10s (`GATE_WORKER_CONFIG_REFRESH_INTERVAL`), the worker refreshes `is_active`, `is_auto_scan`, and `direction` for all managed gates and executes full gate reconciliation (TL-80) in a single batch query without restarting the worker process:
  - **Dynamic Acquisition**: Any gate matching the stream configuration and gate filter that is active (`is_active=True`) but not yet managed is dynamically acquired (acquires advisory lock, launches reader thread, initializes motion filter, sets `camera_status="ONLINE"`).
  - **Dynamic Release**: Any managed gate that is deactivated (`is_active=False`) or soft-deleted is cleanly released (reader thread terminated, advisory lock explicitly released, sets `camera_status="OFFLINE"`) so that `worker_online` immediately becomes `false`, allowing the browser fallback to take over.
  - **Re-activation**: If an inactive gate is later re-activated, it is dynamically re-acquired on the subsequent refresh tick without restarting the worker.
  - **Multi-Replica Exclusion**: Gates held by another worker replica are skipped quietly and retried on subsequent cycles.

### 2.7. Multi-Replica Horizontal Scaling & Gate Subset Partitioning (`--gate`)

Since a single worker process exhibits an empirical saturation knee at 16 cameras (Round 88 baseline: $p95 = 1714$ms; Round 90 3-run benchmark range: $p50 = 1112.47\text{–}1144.49$ ms, $p95 = 1217.23\text{–}1304.13$ ms, median $p95 = 1226.98$ ms) and collapses completely at 32 cameras ($p50 = 34$s, $p95 \approx 95.3$s, 130/160 missed vehicles), scaling a parking facility beyond 16 camera streams requires horizontal partitioning across multiple worker replicas.

- **Gate Subset Filtering**: The management command supports partitioning gates via `--gate`:
  ```bash
  # Single gate
  python manage.py run_gate_worker --gate IN_01
  # Comma-separated gate codes
  python manage.py run_gate_worker --gate IN_01,IN_02
  # Gate IDs
  python manage.py run_gate_worker --gate 1,2
  ```
- **Mutual Exclusion & Advisory Locks**: Each replica independently acquires PostgreSQL session advisory locks (`pg_try_advisory_lock(1195463749, gate_id)`) only for its managed gates. If two replicas are erroneously configured with overlapping subsets, PostgreSQL advisory locks prevent concurrent duplicate stream processing.
- **Docker Compose Multi-Replica Architecture**:
  ```yaml
  services:
    gate-worker-in:
      profiles: ["gate-worker"]
      build:
        context: .
        dockerfile: Dockerfile
        target: runtime
      command: ["python", "manage.py", "run_gate_worker", "--gate", "IN_01,IN_02"]
      environment:
        - DJANGO_SETTINGS_MODULE=config.settings.production
      depends_on:
        db:
          condition: service_healthy

    gate-worker-out:
      profiles: ["gate-worker"]
      build:
        context: .
        dockerfile: Dockerfile
        target: runtime
      command: ["python", "manage.py", "run_gate_worker", "--gate", "OUT_01,OUT_02"]
      environment:
        - DJANGO_SETTINGS_MODULE=config.settings.production
      depends_on:
        db:
          condition: service_healthy
  ```

---

## 3. Alternatives Considered & Rejected

### Alternative A: Standalone Network OCR Microservice (gRPC / HTTP REST)
- *Concept*: Run OCR in a separate microservice container; the API or camera reader sends frames over HTTP/gRPC.
- *Rejected*: Introduces an extra network hop (adding 10–25ms per frame), requires JPEG encoding/decoding overhead, demands a second deployable container and CI pipeline, and duplicates domain models. At our scale (16–32 cameras), in-process ONNX execution within a process-split worker is vastly more efficient.

### Alternative B: Celery / Redis Task Queue Ingestion
- *Concept*: Push frames into a Redis queue; Celery workers pull and process frames.
- *Rejected*: Task queues are designed for durable job execution, not live video pipelines. At 30 fps across multiple cameras, video frames cause massive memory consumption (buffer bloat) in Redis, and any transient processing slowdown creates cascading queue backlog rather than bounded latency.

### Alternative C: Retaining Pure Browser-Based Client Scanning
- *Concept*: Rely on the operator's browser to execute scanning.
- *Rejected*: Violates requirement R-B (Headless Operation). Completely stalls barrier operations when workstations sleep, close tabs, or experience network drops.

---

## 4. Consequences & Trade-offs

### 4.1. Positive Consequences
- **True Headless Operation**: The parking facility operates autonomously without human intervention for all registered subscribers.
- **Zero Web API Degradation**: Moving camera ingestion and OCR inference into `gate-worker` isolates web workers, maintaining sub-100ms API response times.
- **Bounded Latency**: Newest-frame-wins and cheap motion pre-filtering ensure the decision pipeline evaluates only fresh frames, targeting $p95 \le 1.5$s.
- **Zero Schema Migrations**: Fully compatible with frozen PostgreSQL schema (`db/01-schema.sql`).

### 4.2. Liabilities & Operational Requirements
1. **Worker Memory Footprint**: Each `gate-worker` instance requires ~250–350 MiB RSS for OpenCV and ONNX runtime models.
2. **Dedicated DB Connection for Advisory Locks**: Session-level advisory locks require stable, dedicated PostgreSQL connections that must not be abruptly recycled by short `CONN_MAX_AGE` poolers.
3. **Stream Reliability & Network Segmentation**: Camera RTSP/MJPEG streams must be accessible from the worker container network, requiring appropriate firewall and Docker network routing.

---

## 5. Measured Revisit Triggers

The decision to retain an in-process, process-split worker should be formally revisited if any of the following conditions occur:

1. **Scale Knee Point (> 16 Cameras per Worker Process)**: Empirical measurements proved that a single worker process operates near saturation at 16 cameras (Round 88 baseline: $p95 = 1714$ms; Round 90 3-run load benchmark range: $p50 = 1112.47\text{–}1144.49$ ms, $p95 = 1217.23\text{–}1304.13$ ms, median $p95 = 1226.98$ ms vs 1500 ms target) and collapses completely at 32 cameras ($p50 = 34$s, $p95 \approx 95.3$s, 130/160 missed vehicles). If a facility exceeds 16 cameras, workload must be partitioned across multiple worker replicas via `--gate <subset>`. If total facility cameras exceed host hardware limits (aggregate 32–64 cameras across all containers on a single host), offloading OCR to dedicated GPU inference clusters (Alternative A) or edge appliances (Alternative C) becomes mandatory.
2. **Dedicated GPU Acceleration Cluster**: If moving to heavy deep-learning video analytics (e.g. multi-camera vehicle tracking, color/make classification) necessitating centralized GPU inference clusters (such as NVIDIA Triton Inference Server via gRPC).
3. **Multi-Site Distributed Edge Gate Architecture**: If the company deploys edge compute hardware (e.g. Raspberry Pi 5 / NVIDIA Jetson) at geographically isolated parking lots with intermittent wide-area internet connectivity, requiring decentralized edge decision nodes.
