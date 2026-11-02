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

### 8.1 Retrieve Gate List (`GET /api/v1/parking/gates/`)

- **Purpose**: Retrieve barrier gate list to populate entry/exit gate dropdown selectors.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**:
  - `direction` (optional): Filter by gate direction (`IN` or `OUT`).
  - `is_active` (optional): Filter active gates (`true` or `false`).
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
      "is_active": true
    },
    {
      "id": 2,
      "lot_id": 1,
      "code": "IN_02",
      "name": "Cổng vào 2",
      "direction": "IN",
      "camera_status": "ONLINE",
      "is_auto_scan": true,
      "is_active": true
    }
  ]
  ```

### 8.2 License Plate Recognition Scan (`POST /api/v1/parking/plate-scans/`)

- **Purpose**: Recognize license plates from camera feed or uploaded files, automatically apply Position-Aware Corrections, evaluate `AUTO` / `NEEDS_REVIEW` policy, look up registered vehicle records, and provide nearest plate `suggestions`.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Request Format**: `multipart/form-data` (with `X-CSRFToken` header).
- **Form Fields**:
  - `image` (required): Plate image file (JPEG, PNG, WebP; max size 5MB).
  - `gate_id` (optional): ID of barrier gate submitting the scan.

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
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Required Headers**: `X-CSRFToken`.
- **Input Rules**:
  - Provide exactly **one of two criteria**: `session_code` OR `license_plate`.
  - Exit gate `exit_gate_id` must have attribute `direction="OUT"` (selecting an `IN` gate returns error `PROP-4.5.1-P12`).
  - If transient parking fee is `> 0`, `payment_method` is mandatory (`CASH` or `VIETQR`).
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

---
