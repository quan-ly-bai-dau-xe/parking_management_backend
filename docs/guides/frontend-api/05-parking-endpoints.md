# Frontend API Guide — Parking Endpoints

[← Previous: 04-conventions.md](04-conventions.md) | [↑ Back to Index](../01-frontend-api-guide.md) | [Next: 06-vehicle-endpoints.md →](06-vehicle-endpoints.md)

## 8. Details of All 8 Parking Endpoints

All parking module endpoints require staff or manager authentication (`IsEmployeeOrManager`). Customer accounts (`CUSTOMER`) receive `403 Forbidden` (`MSG-4.2-M01`):

```http
GET /api/v1/parking/gates/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "MSG-4.2-M01",
  "message": "Bạn không có quyền thực hiện thao tác này.",
  "details": {
    "detail": "Bạn không có quyền thực hiện thao tác này."
  }
}
```

### 8.1 Retrieve Gate List & Worker Telemetry (`GET /api/v1/parking/gates/`)

- **Purpose**: Retrieve barrier gate list to populate entry/exit gate selectors and monitor server-side `gate-worker` process telemetry (`worker_online`, `last_auto_event`).
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**:
  - `direction` (optional): Filter by gate direction (`IN` or `OUT`).
  - `is_active` (optional): Filter active gates (`true` or `false`).
- **Response Fields**:
  - `id` (integer): Gate primary key.
  - `lot_id` (integer): Linked parking lot ID.
  - `code` (string): Unique gate identifier (e.g., `"IN_01"`, `"OUT_01"`).
  - `name` (string): Human-readable gate label.
  - `direction` (string): Gate traffic direction (`"IN"` or `"OUT"`).
  - `camera_status` (string): Camera connection health (`"ONLINE"`, `"DEGRADED"`, `"OFFLINE"`, or `"LOW_LIGHT"`). Dynamically mapped to `"OFFLINE"` on read (zero DB `UPDATE`, preserving `row_version`) whenever `worker_online` is `false`.
  - `is_auto_scan` (boolean): Whether automated plate detection is enabled for this gate.
  - `is_active` (boolean): Operational status of the gate.
  - `worker_online` (boolean, TL-70, TL-72, TL-80, TL-86): Whether a background `gate-worker` process currently holds the PostgreSQL session-level advisory lock for this gate in `pg_locks` (`locktype='advisory'`, `classid=1195463749`, `objsubid IN (1, 2)`, `granted=true`).
    - **Database Isolation Filter (TL-80, G9d)**: The underlying SQL query explicitly filters `d.datname = current_database()` by joining `pg_database` on `l.database = d.oid`. This prevents advisory locks of the same classid in a different database on the same shared PostgreSQL server from falsely marking gates online.
    - When `true`: Frontend modal switches to **Viewer Mode** (displays live stream and server-side automated events; client-side auto-apply is disabled to prevent duplicate check-ins).
    - When `false`: Frontend modal operates in **Browser Mode** (uses webcam or uploaded frames, client-side auto-apply policy runs with toggle banner).
    - Before the first status poll resolves, Frontend holds an **Unknown** state (`workerOnline = null`) and suppresses client auto-apply (TL-76).
    - **Polling Error Tolerance (TL-86, G8b)**: If a status poll fails (e.g., transient network blip, 401, 500), `gateService` returns an error distinguishable from an actual offline response (`worker_online: false`). The frontend modal retains its previous `workerOnline` value (viewer stays viewer, unknown stays unknown), preventing accidental flip to browser mode and avoiding HTTP 409 double-submit storms. Only after 3 consecutive failed polls does the modal show a subtle "status unavailable" note, and it still does not start auto-applying if the prior state was viewer or unknown.
  - `last_auto_event` (object or `null`, TL-70, TL-72, TL-73, TL-82): Summary of the most recent automated decision event queried solely from `activity_log`:
    - **Single Decision Row & Action Filter (TL-82, G7)**: To maintain audit row integrity and ensure N decisions produce exactly N decision rows, `last_auto_event` is chosen strictly from the four definitive decision actions (`"GATE_AUTO_CHECK_IN"`, `"GATE_AUTO_CHECK_OUT"`, `"GATE_AUTO_NEEDS_STAFF"`, `"GATE_AUTO_PAYMENT_REQUIRED"`). It never selects snapshot failure rows as the primary decision.
    - `action` (string): Automated action code (`"GATE_AUTO_CHECK_IN"`, `"GATE_AUTO_CHECK_OUT"`, `"GATE_AUTO_NEEDS_STAFF"`, `"GATE_AUTO_PAYMENT_REQUIRED"`).
    - `license_plate_masked` (string): Plate formatted with privacy masking (e.g., `"51A-***.14"` or `"30A***35"`).
    - `reason` (string): Technical decision reason code (e.g., `"VALID_REGISTERED"`, `"VALID_FEE_ZERO"`, `"UNREGISTERED_VEHICLE"`, `"FEE_PAYMENT_REQUIRED"`, `"NO_AVAILABLE_SLOT"`, `"BLACKLISTED"`, `"OPEN_SESSION_ALREADY_EXISTS"`, `"NO_OPEN_SESSION"`, `"NEEDS_REVIEW"`, `"EXECUTION_FAILED"`).
    - `occurred_at` (string, ISO 8601): UTC timestamp of the automated decision.
    - `snapshot_error` (string or `null`): Sanitized failure reason if the asynchronous background snapshot upload failed or timed out (`null` when upload succeeded or is not applicable). When an upload fails, the worker records a distinct `GATE_AUTO_SNAPSHOT_FAILED` row; the serializer queries any subsequent `GATE_AUTO_SNAPSHOT_FAILED` row for the gate and attaches its reason here, providing frontend observability without duplicating decision rows or altering the decision action.
  - **Pending Vehicle Liveness & "Still-Seen" Rule (`TL-103`)**: When `gate-worker` holds an unregistered entry (`UNREGISTERED_VEHICLE`) or an insufficient-wallet exit (`WALLET_INSUFFICIENT`), it re-evaluates the pending item every `GATE_WORKER_PENDING_RECHECK_SECONDS` (`5.0`s default) only while the vehicle remains "still seen" (`now - last_seen_at <= GATE_WORKER_PENDING_SEEN_SECONDS`, default `20`s) and executes the auto check-in/check-out only on a fresh sighting. If the plate temporarily drops out in `(20s, 60s]`, the worker waits silently with zero DB queries/logs/actions; if unseen for `> 3 * GATE_WORKER_PENDING_SEEN_SECONDS` (`60`s) or pending longer than `GATE_WORKER_PENDING_MINUTES` (`15`m / `900`s) from `first_seen_at`, the item is evicted so vehicles that already left the lane are never auto-processed upon late registration or top-up.
- **Live Stack Example**:

  ```http
  GET /api/v1/parking/gates/?direction=IN HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  [
    {
      "id": 1,
      "lot_id": 1,
      "code": "IN_01",
      "name": "Cổng vào 1",
      "direction": "IN",
      "camera_status": "ONLINE",
      "is_auto_scan": true,
      "is_active": true,
      "worker_online": true,
      "last_auto_event": {
        "action": "GATE_AUTO_CHECK_IN",
        "license_plate_masked": "51A-***.14",
        "reason": "VALID_REGISTERED",
        "occurred_at": "2026-11-08T06:00:00Z",
        "snapshot_error": null
      }
    },
    {
      "id": 2,
      "lot_id": 1,
      "code": "IN_02",
      "name": "Cổng vào 2",
      "direction": "IN",
      "camera_status": "OFFLINE",
      "is_auto_scan": true,
      "is_active": true,
      "worker_online": false,
      "last_auto_event": null
    }
  ]
  ```

### 8.2 License Plate Recognition Scan (`POST /api/v1/parking/plate-scans/`)

- **Purpose**: Recognize license plates from camera feed or uploaded files, automatically apply Position-Aware Corrections, evaluate `AUTO` / `NEEDS_REVIEW` policy, look up registered vehicle records, and provide nearest plate `suggestions`.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Request Format**: `multipart/form-data` (with `X-CSRFToken` header).
- **Form Fields**:
  - `image` (required): Plate image file (JPEG, PNG, WebP; max size 5MB).
  - `gate_id` (optional, positive integer): ID of barrier gate submitting the scan. Forwarded to service execution and tracked in request observability logs (`_obs_gate_id`). Invalid values (non-numeric, <= 0) return HTTP 400 Bad Request with code `PROP-GEN-P01`.
  - `preview` (optional, boolean string `"true"` or `"false"`, default: `false`):
    - When `true`: Run image decode, OCR, position-aware corrections, review policy evaluation, and vehicle/session/blacklist lookups without uploading the image to Cloudinary; returns `"image_url": null`. Optimized for continuous camera auto-detection loops.
    - When `false` or omitted: Authoritative scan mode, uploads image to Cloudinary and returns permanent HTTPS image URL.
    - Note: Invalid values trigger HTTP 400 Bad Request with code `PROP-GEN-P01`.

#### Example 1: Successful Automatic Approval (`review_status: "AUTO"`)

When AI confidence is high and conforms to Vietnamese vehicle plate standards (`43K-860.50` owned by customer `Trịnh Xuân Trường`):

```http
POST /api/v1/parking/plate-scans/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

[Multipart Form Data: image=car_43k86050.jpg (image/jpeg), gate_id=1]

HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: 53b70530673b41b8a7a4d75de93bf5e2

{
  "plate_raw": "43K-860.50",
  "plate_final": "43K86050",
  "candidates": [
    {
      "plate_text": "43K-860.50",
      "plate_normalized": "43K86050",
      "confidence": 98.5,
      "char_confidences": [
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5
      ],
      "min_char_confidence": 98.5,
      "bounding_box": {
        "x1": 50,
        "y1": 50,
        "x2": 350,
        "y2": 150
      }
    }
  ],
  "best_candidate": {
    "plate_text": "43K86050",
    "plate_normalized": "43K86050",
    "confidence": 98.5,
    "char_confidences": [
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5
    ],
    "min_char_confidence": 98.5,
    "bounding_box": {
      "x1": 50,
      "y1": 50,
      "x2": 350,
      "y2": 150
    }
  },
  "image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729238400/parking_scans/2026/10/22/3b571536e9084d9f8bc679f027904cee.jpg",
  "vehicle_lookup": {
    "vehicle": {
      "id": 1,
      "code": "XE0001",
      "license_plate": "43K-860.50",
      "license_plate_norm": "43K86050",
      "model_name": "Vios 1.5G",
      "brand": "Toyota",
      "color": "Trắng",
      "vehicle_type": "Ô tô",
      "vehicle_type_code": "CAR"
    },
    "customer": {
      "id": 16,
      "code": "KH0001",
      "full_name": "Trịnh Xuân Trường",
      "phone": "0868851325",
      "is_anonymized": false
    },
    "parking_position": {
      "slot_id": 1,
      "slot_code": "A-01",
      "zone_code": "A",
      "floor_code": "B1",
      "floor_name": "Tầng B1",
      "display_text": "Tầng B1 - Zone A - A-01"
    },
    "active_ticket": {
      "id": 1,
      "code": "VT0001",
      "ticket_type_name": "Vé tháng",
      "price": "500000.00",
      "effective_from": "2026-03-31T17:00:00+00:00",
      "effective_to": "2026-11-30T17:00:00+00:00",
      "status": "ACTIVE"
    },
    "open_session": {
      "id": 37,
      "session_code": "#PK-20261017-037",
      "entry_time": "2026-10-17T00:20:00+00:00",
      "entry_gate_name": "Cổng vào 1",
      "entry_image_url": null,
      "recognition_source": "AI",
      "ai_confidence": 97.1,
      "review_status": "MATCHED"
    },
    "is_blacklisted": false
  },
  "is_blacklisted": false,
  "open_session": {
    "id": 37,
    "session_code": "#PK-20261017-037",
    "entry_time": "2026-10-17T00:20:00+00:00",
    "entry_gate_name": "Cổng vào 1",
    "entry_image_url": null,
    "recognition_source": "AI",
    "ai_confidence": 97.1,
    "review_status": "MATCHED"
  },
  "engine_name": "dummy",
  "latency_ms": 1.0,
  "review_status": "AUTO",
  "review_reasons": [],
  "corrections": [],
  "suggestions": []
}
```

#### Example 2: Operator Review Required (`review_status: "NEEDS_REVIEW"`)

When image has low confidence or positional character correction was applied (`43K-86O.59` with `O` at pos 5 corrected to `0` -> `43K86059`, suggesting registered plate `43K-860.50`):

```http
POST /api/v1/parking/plate-scans/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

[Multipart Form Data: image=car_review.jpg (image/jpeg), gate_id=1]

HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: d50c117a75c14f67a35af4e14c93ffc5

{
  "plate_raw": "43K-86O.59",
  "plate_final": "43K86059",
  "candidates": [
    {
      "plate_text": "43K-86O.59",
      "plate_normalized": "43K86O59",
      "confidence": 78.0,
      "char_confidences": [
        78.0,
        78.0,
        78.0,
        78.0,
        78.0,
        78.0,
        78.0,
        78.0
      ],
      "min_char_confidence": 78.0,
      "bounding_box": {
        "x1": 50,
        "y1": 50,
        "x2": 350,
        "y2": 150
      }
    }
  ],
  "best_candidate": {
    "plate_text": "43K86059",
    "plate_normalized": "43K86059",
    "confidence": 78.0,
    "char_confidences": [
      78.0,
      78.0,
      78.0,
      78.0,
      78.0,
      78.0,
      78.0,
      78.0
    ],
    "min_char_confidence": 78.0,
    "bounding_box": {
      "x1": 50,
      "y1": 50,
      "x2": 350,
      "y2": 150
    }
  },
  "image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729238400/parking_scans/2026/10/22/a98af4bc71a941d2a79cac484d323ab9.jpg",
  "vehicle_lookup": null,
  "is_blacklisted": false,
  "open_session": null,
  "engine_name": "dummy",
  "latency_ms": 1.0,
  "review_status": "NEEDS_REVIEW",
  "review_reasons": [
    "LOW_CHAR_CONFIDENCE",
    "POSITION_CORRECTED"
  ],
  "corrections": [
    {
      "position": 5,
      "from": "O",
      "to": "0",
      "rule": "number_group_digit_fix_pos_5",
      "reason": "Positional grammar requires digit at position 5; corrected 'O' to '0'",
      "original_char": "O",
      "corrected_char": "0"
    }
  ],
  "suggestions": [
    "43K-860.50"
  ]
}
```

#### Example 3: License Plate Not Detected in Image (HTTP `422 Unprocessable Content`)

```http
POST /api/v1/parking/plate-scans/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

[Multipart Form Data: image=empty_scan.jpg (image/jpeg), gate_id=1]

HTTP/1.1 422 Unprocessable Content
Content-Type: application/json
X-Request-ID: bb89b602b5694d7fb7c66f7158faf1ec

{
  "code": "PROP-4.5.1-P06",
  "message": "Không nhận diện được biển số xe từ hình ảnh đã cung cấp.",
  "details": {}
}
```

#### Example 4: Continuous Camera Preview Scan (`preview: "true"`, `image_url: null`)

Used by the laptop webcam continuous detection loop to obtain OCR recognition, review status, and vehicle lookup without persisting images to Cloudinary:

```http
POST /api/v1/parking/plate-scans/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

[Multipart Form Data: image=frame_preview.jpg (image/jpeg), gate_id=1, preview="true"]

HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: e12d8a901f4c478bb2f3e8b0918c4621

{
  "plate_raw": "43K-860.50",
  "plate_final": "43K86050",
  "candidates": [
    {
      "plate_text": "43K-860.50",
      "plate_normalized": "43K86050",
      "confidence": 98.5,
      "char_confidences": [
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5
      ],
      "min_char_confidence": 98.5,
      "bounding_box": {
        "x1": 50,
        "y1": 50,
        "x2": 350,
        "y2": 150
      }
    }
  ],
  "best_candidate": {
    "plate_text": "43K86050",
    "plate_normalized": "43K86050",
    "confidence": 98.5,
    "char_confidences": [
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5
    ],
    "min_char_confidence": 98.5,
    "bounding_box": {
      "x1": 50,
      "y1": 50,
      "x2": 350,
      "y2": 150
    }
  },
  "image_url": null,
  "vehicle_lookup": {
    "vehicle": {
      "id": 1,
      "code": "XE0001",
      "license_plate": "43K-860.50",
      "license_plate_norm": "43K86050",
      "model_name": "Vios 1.5G",
      "brand": "Toyota",
      "color": "Trắng",
      "vehicle_type": "Ô tô",
      "vehicle_type_code": "CAR"
    },
    "customer": {
      "id": 16,
      "code": "KH0001",
      "full_name": "Trịnh Xuân Trường",
      "phone": "0868851325",
      "is_anonymized": false
    },
    "parking_position": {
      "slot_id": 1,
      "slot_code": "A-01",
      "zone_code": "A",
      "floor_code": "B1",
      "floor_name": "Tầng B1",
      "display_text": "Tầng B1 - Zone A - A-01"
    },
    "active_ticket": {
      "id": 1,
      "code": "VT0001",
      "ticket_type_name": "Vé tháng",
      "price": "500000.00",
      "effective_from": "2026-03-31T17:00:00+00:00",
      "effective_to": "2026-11-30T17:00:00+00:00",
      "status": "ACTIVE"
    },
    "open_session": null,
    "is_blacklisted": false
  },
  "is_blacklisted": false,
  "open_session": null,
  "engine_name": "dummy",
  "latency_ms": 1.0,
  "review_status": "AUTO",
  "review_reasons": [],
  "corrections": [],
  "suggestions": []
}
```

#### Table of 9 Review Reason Codes (`ReviewReasonCode` in `apps/parking/enums.py`)

| Reason Code (`review_reasons`) | Technical Meaning | Recommended UI Action |
|---|---|---|
| `MODEL_DISAGREEMENT` | The two AI OCR models yielded differing plate recognition outputs. | Display both candidates side-by-side so operator can select correct plate. |
| `LOW_CHAR_CONFIDENCE` | One or more characters fall below confidence threshold (< 90.0%). | Highlight low-confidence characters with yellow alert badge on UI. |
| `INVALID_FORMAT` | Recognized plate string does not conform to Vietnamese motor vehicle standards. | Prompt operator to inspect and verify plate structure. |
| `UNKNOWN_PLATE_PATTERN` | Unconventional plate format not cataloged in standard rules. | Provide manual text input field for operator verification. |
| `NO_DETECTION_RETRY` | Primary detector missed plate, triggered fallback crop. | Alert that camera angle or lighting may be suboptimal. |
| `LOW_DETECTION_CONFIDENCE` | License plate bounding box confidence is `< 80.0%`. | Warn that vehicle may not be aligned with optimal detection zone. |
| `IRREGULAR_ASPECT_RATIO` | Plate aspect ratio is irregular (`< 1.3` or `> 6.0`). | Warn that plate angle is excessively skewed or distorted. |
| `LOW_IMAGE_SHARPNESS` | Low image sharpness score (Laplacian variance `< 30.0`, blurry image). | Notify that image is blurry due to vehicle motion or adverse weather. |
| `POSITION_CORRECTED` | Positional grammar rule correction applied (e.g., letter `O` corrected to digit `0`). | Display `corrections` list for operator confirmation. |

#### UI Handling Guidelines for `NEEDS_REVIEW`

When `review_status === "NEEDS_REVIEW"`:

1. **Warning Badge**: Display yellow/amber badge "Review Required" next to plate number.
2. **Enable Editing**: Provide text input enabling gate operator to correct the plate based on camera image shown on screen.
3. **Show Suggestions**: Render `suggestions` list as quick-selection action buttons for one-touch operator confirmation.
4. **Do Not Open Barrier Automatically**: Never auto-trigger barrier gate opening until the operator clicks "Confirm Check-In".

### 8.3 Lookup Vehicle by Plate Number (`GET /api/v1/parking/vehicle-lookup/`)

- **Purpose**: Instantly retrieve vehicle specifications, customer details, assigned slot, active monthly pass, active session, and blacklist status upon gate approach.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameter**: `license_plate` (license plate string, required).
- **Live Stack Example When Vehicle Found (`43K-860.50`)**:

  ```http
  GET /api/v1/parking/vehicle-lookup/?license_plate=43K-860.50 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "vehicle": {
      "id": 1,
      "code": "XE0001",
      "license_plate": "43K-860.50",
      "license_plate_norm": "43K86050",
      "model_name": "Vios 1.5G",
      "brand": "Toyota",
      "color": "Trắng",
      "vehicle_type": "Ô tô",
      "vehicle_type_code": "CAR"
    },
    "customer": {
      "id": 16,
      "code": "KH0001",
      "full_name": "Trịnh Xuân Trường",
      "phone": "0868851325",
      "is_anonymized": false
    },
    "parking_position": {
      "slot_id": 1,
      "slot_code": "A-01",
      "zone_code": "A",
      "floor_code": "B1",
      "floor_name": "Tầng B1",
      "display_text": "Tầng B1 - Zone A - A-01"
    },
    "active_ticket": {
      "id": 1,
      "code": "VT0001",
      "ticket_type_name": "Vé tháng",
      "price": "500000.00",
      "effective_from": "2026-03-31T17:00:00+00:00",
      "effective_to": "2026-11-30T17:00:00+00:00",
      "status": "ACTIVE"
    },
    "open_session": {
      "id": 37,
      "session_code": "#PK-20261017-037",
      "entry_time": "2026-10-17T00:20:00+00:00",
      "entry_gate_name": "Cổng vào 1",
      "entry_image_url": null,
      "recognition_source": "AI",
      "ai_confidence": 97.1,
      "review_status": "MATCHED"
    },
    "is_blacklisted": false
  }
  ```

- **Live Stack Example When Not Found** (HTTP `404 Not Found` with code `MSG-4.5.1-M01`):

  ```http
  GET /api/v1/parking/vehicle-lookup/?license_plate=99Z-999.99 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 404 Not Found
  Content-Type: application/json

  {
    "code": "MSG-4.5.1-M01",
    "message": "Không tìm thấy dữ liệu trùng khớp",
    "details": {}
  }
  ```

### 8.4 Multi-Criteria Vehicle Search (`GET /api/v1/parking/vehicle-search/`)

- **Purpose**: Assist staff in locating parked vehicles for customers or looking up vehicle history across multiple search criteria.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**:
  - `q` (optional): Unified search keyword (automatically matches customer name, phone number, or plate; minimum 2 characters).
  - `customer_name` (optional): Filter by customer name.
  - `phone` (optional): Filter by phone number (supports `+84` and `0` formats).
  - `license_plate` (optional): Filter by license plate.
  - `page` / `page_size`: Pagination parameters.
- **Example 1: Matching Search Results (`?q=43K-860`)**:

  ```http
  GET /api/v1/parking/vehicle-search/?q=43K-860 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "count": 1,
    "total_pages": 1,
    "current_page": 1,
    "page_size": 20,
    "next": null,
    "previous": null,
    "results": [
      {
        "vehicle": {
          "id": 1,
          "code": "XE0001",
          "license_plate": "43K-860.50",
          "license_plate_norm": "43K86050",
          "model_name": "Vios 1.5G",
          "brand": "Toyota",
          "color": "Trắng",
          "vehicle_type": "Ô tô",
          "vehicle_type_code": "CAR"
        },
        "customer": {
          "id": 16,
          "code": "KH0001",
          "full_name": "Trịnh Xuân Trường",
          "phone": "0868851325",
          "is_anonymized": false
        },
        "parking_position": {
          "slot_id": 1,
          "slot_code": "A-01",
          "zone_code": "A",
          "floor_code": "B1",
          "floor_name": "Tầng B1",
          "display_text": "Tầng B1 - Zone A - A-01"
        },
        "active_ticket": {
          "id": 1,
          "code": "VT0001",
          "ticket_type_name": "Vé tháng",
          "price": "500000.00",
          "effective_from": "2026-03-31T17:00:00+00:00",
          "effective_to": "2026-11-30T17:00:00+00:00",
          "status": "ACTIVE"
        },
        "open_session": {
          "id": 37,
          "session_code": "#PK-20261017-037",
          "entry_time": "2026-10-17T00:20:00+00:00",
          "entry_gate_name": "Cổng vào 1",
          "entry_image_url": null,
          "recognition_source": "AI",
          "ai_confidence": 97.1,
          "review_status": "MATCHED"
        },
        "is_blacklisted": false,
        "currently_parked": true
      }
    ],
    "message": null
  }
  ```

- **Example 2: No Matching Results (`200 OK` with `message`)**:

  ```http
  GET /api/v1/parking/vehicle-search/?q=99Z-999 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "count": 0,
    "total_pages": 0,
    "current_page": 1,
    "page_size": 20,
    "next": null,
    "previous": null,
    "results": [],
    "message": "Không tìm thấy dữ liệu trùng khớp"
  }
  ```

- **Example 3: Search Keyword Shorter Than 2 Characters (`400 Bad Request` with `PROP-GEN-P01`)**:

  ```http
  GET /api/v1/parking/vehicle-search/?q=a HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 400 Bad Request
  Content-Type: application/json

  {
    "code": "PROP-GEN-P01",
    "message": "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu",
    "details": {
      "q": [
        "Từ khóa tìm kiếm phải có độ dài tối thiểu 2 ký tự sau khi loại bỏ khoảng trắng."
      ]
    }
  }
  ```

### 8.5 Vehicle Check-In (`POST /api/v1/parking/sessions/check-in/`)

- **Purpose**: Record vehicle entry at the barrier gate, generating session code `#PK-YYYYMMDD-NNN`.
- **Required Permission**: `EMPLOYEE` or `MANAGER` (`override_blacklist=true` flag restricted to `MANAGER`).
- **Required Headers**: `X-CSRFToken`.
- **Body Fields**: `license_plate` (required), `entry_gate_id` (optional), `slot_id` (optional), `entry_image_url` (optional), `recognition_source` (`AI` or `MANUAL`), `ai_confidence` (0–100), `review_status` (`AUTO` or `NEEDS_REVIEW`), `override_blacklist` (`false` default), `notes` (optional).
- **Live Stack Example (HTTP `201 Created`)**:

  ```http
  POST /api/v1/parking/sessions/check-in/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]
  Content-Type: application/json

  {"license_plate": "29A-999.99", "entry_gate_id": 1, "recognition_source": "AI", "ai_confidence": 98.2, "slot_id": 6}

  HTTP/1.1 201 Created
  Content-Type: application/json
  X-Request-ID: 4ebeaa8918d84ad8a3673bf8b3d629ac

  {
    "session": {
      "id": 51,
      "session_code": "#PK-20261022-001",
      "vehicle_id": null,
      "slot_id": 6,
      "slot_display": "Tầng B1 - Zone A - A-06",
      "ticket_id": null,
      "entry_gate_id": 1,
      "entry_gate_name": "Cổng vào 1",
      "exit_gate_id": null,
      "exit_gate_name": null,
      "license_plate": "29A-999.99",
      "license_plate_norm": "29A99999",
      "ai_confidence": "98.20",
      "recognition_source": "AI",
      "review_status": "AUTO",
      "fee_amount": "0.00",
      "entry_time": "2026-10-22T15:00:27.280374Z",
      "exit_time": null,
      "duration_seconds": 0,
      "duration_text": "0 giây",
      "entry_image_url": null,
      "exit_image_url": null,
      "entry_handled_by": 5,
      "entry_handled_by_name": "Lương Thị Mai Phương",
      "exit_handled_by": null,
      "exit_handled_by_name": null,
      "notes": null,
      "created_at": "2026-10-22T15:00:27.293351Z"
    },
    "vehicle_lookup": null
  }
  ```

### 8.6 Vehicle Check-Out (`POST /api/v1/parking/sessions/check-out/`)

- **Purpose**: Conclude vehicle parking session at exit gate, automatically calculate parking fee (0 VND for `ACTIVE` monthly passes; otherwise calculated by hourly block: 10,000 VND/hour), and record payment record `payment`.
- **Required Permission**: `EMPLOYEE` or `MANAGER` (fee waiver restricted to `MANAGER` only).
- **Required Headers**: `X-CSRFToken`.
- **Input Rules**:
  - Provide exactly **one of two criteria**: `session_code` OR `license_plate`.
  - Exit gate `exit_gate_id` must have attribute `direction="OUT"` (selecting an `IN` gate returns error `PROP-4.5.1-P12`).
  - If transient parking fee is `> 0` and `waive_fee=false`, `payment_method` is mandatory (`CASH` or `VIETQR`).
  - **Fee Waiver (`waive_fee=true`)** (TL-58, TL-59):
    - Only `MANAGER` accounts are permitted. Calling as `EMPLOYEE` returns HTTP 403 `PROP-4.5.1-P18` (`"Chỉ Quản lý mới có quyền miễn cước phí đỗ xe."`).
    - `waiver_reason` is mandatory and cannot be empty/whitespace. Empty reason returns HTTP 400 `PROP-4.5.1-P19` (`"Vui lòng cung cấp lý do miễn cước đặc cách."`).
    - When waived: `fee_amount = 0.00`, `payment_method` is ignored, no `Payment` record is created. Audit note is appended to `session.notes` and immutable event is recorded in `ActivityLog` (`action="SESSION_CHECK_OUT_WAIVED"`).
- **Live Stack Example (HTTP `200 OK`)**:

  ```http
  POST /api/v1/parking/sessions/check-out/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]
  Content-Type: application/json

  {"session_code": "#PK-20261022-001", "exit_gate_id": 3, "payment_method": "CASH"}

  HTTP/1.1 200 OK
  Content-Type: application/json
  X-Request-ID: 090ff478119748eeabe0232654092df4

  {
    "session": {
      "id": 51,
      "session_code": "#PK-20261022-001",
      "vehicle_id": null,
      "slot_id": 6,
      "slot_display": "Tầng B1 - Zone A - A-06",
      "ticket_id": null,
      "entry_gate_id": 1,
      "entry_gate_name": "Cổng vào 1",
      "exit_gate_id": 3,
      "exit_gate_name": "Cổng ra 1",
      "license_plate": "29A-999.99",
      "license_plate_norm": "29A99999",
      "ai_confidence": "98.20",
      "recognition_source": "AI",
      "review_status": "AUTO",
      "fee_amount": "10000.00",
      "entry_time": "2026-10-22T15:00:27.280374Z",
      "exit_time": "2026-10-22T15:00:27.362731Z",
      "duration_seconds": 0,
      "duration_text": "0 giây",
      "entry_image_url": null,
      "exit_image_url": null,
      "entry_handled_by": 5,
      "entry_handled_by_name": "Lương Thị Mai Phương",
      "exit_handled_by": 5,
      "exit_handled_by_name": "Lương Thị Mai Phương",
      "notes": null,
      "created_at": "2026-10-22T15:00:27.293351Z"
    },
    "payment": {
      "id": 54,
      "code": "PAY-SES-PK-20261022-001",
      "amount": "10000.00",
      "method": "CASH",
      "status": "PAID",
      "paid_at": "2026-10-22T15:00:27.362731Z"
    },
    "vehicle_lookup": null
  }
  ```

### 8.6b Vehicle Fee Preview (`GET /api/v1/parking/sessions/fee-preview/`)

- **Purpose**: Real-time calculation of expected parking fee for an open session (`exit_time IS NULL`) before check-out confirmation (TL-57). Supports ExitLanePanel on both registered and unregistered vehicles.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**:
  - `license_plate`: string (optional, e.g. `51A-897.14`).
  - `session_code`: string (optional, e.g. `#PK-20261017-037`).
  - *Rule*: At least one parameter must be supplied. Missing both returns HTTP 400 `PROP-4.5.1-P11`.
- **Error Codes**:
  - `400 Bad Request` (`PROP-4.5.1-P11`): Missing both session identification criteria (`session_code` and `license_plate`).
  - `404 Not Found` (`PROP-4.5.1-P06`): Open parking session matching criteria not found.
- **Live Example (HTTP `200 OK`)**:

  ```http
  GET /api/v1/parking/sessions/fee-preview/?license_plate=51A-897.14 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "session_id": 123,
    "session_code": "#PK-20261106-001",
    "license_plate": "51A-897.14",
    "entry_time": "2026-11-06T08:00:00Z",
    "duration_minutes": 65,
    "duration_text": "1 giờ 5 phút",
    "fee_amount": 20000.0,
    "has_active_ticket": false,
    "ticket_code": null,
    "is_exempt": false,
    "hourly_rate": 10000.0
  }
  ```

### 8.7 List Parking Sessions (`GET /api/v1/parking/sessions/`)

- **Purpose**: Retrieve historical parking session log table for management and statistics.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**: `session_code`, `license_plate`, `status` (`open` or `closed`), `entry_time_from`, `entry_time_to`, `page`, `page_size`.
- **Live Stack Example**:

  ```http
  GET /api/v1/parking/sessions/?status=open&page=1&page_size=2 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "count": 15,
    "total_pages": 8,
    "current_page": 1,
    "page_size": 2,
    "next": "http://127.0.0.1:8000/api/v1/parking/sessions/?page=2&page_size=2&status=open",
    "previous": null,
    "results": [
      {
        "id": 51,
        "session_code": "#PK-20261022-001",
        "license_plate": "29A-999.99",
        "license_plate_norm": "29A99999",
        "entry_time": "2026-10-22T15:00:27.280374Z",
        "exit_time": null,
        "duration_seconds": 0,
        "duration_text": "0 giây",
        "fee_amount": "0.00",
        "entry_image_url": null,
        "exit_image_url": null,
        "entry_gate_name": "Cổng vào 1",
        "exit_gate_name": null,
        "ai_confidence": "98.20",
        "recognition_source": "AI",
        "review_status": "AUTO",
        "vehicle_model": null,
        "vehicle_brand": null,
        "customer_name": null,
        "customer_phone": null,
        "slot_code": "A-06"
      },
      {
        "id": 50,
        "session_code": "#PK-20261017-050",
        "license_plate": "30C-468.58",
        "license_plate_norm": "30C46858",
        "entry_time": "2026-10-17T05:28:00Z",
        "exit_time": null,
        "duration_seconds": 466347,
        "duration_text": "5 ngày 9 giờ 32 phút",
        "fee_amount": "30000.00",
        "entry_image_url": null,
        "exit_image_url": null,
        "entry_gate_name": "Cổng vào 2",
        "exit_gate_name": null,
        "ai_confidence": "97.30",
        "recognition_source": "AI",
        "review_status": "MATCHED",
        "vehicle_model": null,
        "vehicle_brand": null,
        "customer_name": null,
        "customer_phone": null,
        "slot_code": "C-01"
      }
    ]
  }
  ```

### 8.8 Parking Session Details (`GET /api/v1/parking/sessions/{id}/`)

- **Purpose**: View granular parking session details by integer ID (entry/exit timestamps, barrier camera photos, handling staff, slot assignment, billing).
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Live Stack Example When Found (`GET /api/v1/parking/sessions/51/`)**:

  ```http
  GET /api/v1/parking/sessions/51/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "id": 51,
    "session_code": "#PK-20261022-001",
    "vehicle_id": null,
    "slot_id": 6,
    "slot_display": "Tầng B1 - Zone A - A-06",
    "ticket_id": null,
    "entry_gate_id": 1,
    "entry_gate_name": "Cổng vào 1",
    "exit_gate_id": null,
    "exit_gate_name": null,
    "license_plate": "29A-999.99",
    "license_plate_norm": "29A99999",
    "ai_confidence": "98.20",
    "recognition_source": "AI",
    "review_status": "AUTO",
    "fee_amount": "0.00",
    "entry_time": "2026-10-22T15:00:27.280374Z",
    "exit_time": null,
    "duration_seconds": 0,
    "duration_text": "0 giây",
    "entry_image_url": null,
    "exit_image_url": null,
    "entry_handled_by": 5,
    "entry_handled_by_name": "Lương Thị Mai Phương",
    "exit_handled_by": null,
    "exit_handled_by_name": null,
    "notes": null,
    "created_at": "2026-10-22T15:00:27.293351Z"
  }
  ```

- **Live Stack Example When Not Found (`404 Not Found` with `MSG-4.4.1-M01`)**:

  ```http
  GET /api/v1/parking/sessions/999999/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 404 Not Found
  Content-Type: application/json

  {
    "code": "MSG-4.4.1-M01",
    "message": "Không tìm thấy dữ liệu",
    "details": {}
  }
  ```

### 8.9 Parking Structure & Slot Management (WP1)

- **`GET /api/v1/parking/structure/`** (`EMPLOYEE` or `MANAGER`): Retrieve hierarchical parking lot structure (lots, floors, zones).
- **`GET /api/v1/parking/slots/`** (`EMPLOYEE` or `MANAGER`): List active parking slots with filters (`status`, `floor`, `zone`, `vehicle_type`, `slot_kind`, `search`).
- **`POST /api/v1/parking/slots/`** (`MANAGER` + `X-CSRFToken`): Create a new parking slot (4.8.2).
- **`GET /api/v1/parking/slots/{id}/`** (`EMPLOYEE` or `MANAGER`): Retrieve slot detail including active session, ticket, and reservation (4.8.4).
- **`PATCH /api/v1/parking/slots/{id}/`** (`MANAGER` + `X-CSRFToken`): Update slot attributes or status with OCC `row_version` (4.8.3).
- **`DELETE /api/v1/parking/slots/{id}/`** (`MANAGER` + `X-CSRFToken`): Soft-delete slot guarded against occupied/charging/reserved/ticketed states (4.8.5).

### 8.10 Slot Reservations (4.5.2)

- **`POST /api/v1/parking/slots/{id}/reserve/`** (`CUSTOMER`, `EMPLOYEE`, or `MANAGER` + `X-CSRFToken`): Create a slot reservation ("Register Parking") for an `AVAILABLE` slot matching the vehicle's allowed type; enforces GiST overlap exclusion (`409` `PROP-4.5.2-P05`). `CUSTOMER` may only reserve for their own active vehicles.
- **`GET /api/v1/parking/reservations/`** (`CUSTOMER`, `EMPLOYEE`, or `MANAGER`): List reservations (`CUSTOMER` sees only their own reservations; staff sees all).
- **`POST /api/v1/parking/reservations/{id}/cancel/`** (`CUSTOMER`, `EMPLOYEE`, or `MANAGER` + `X-CSRFToken`): Cancel an active reservation (`CUSTOMER` may only cancel their own).

---
