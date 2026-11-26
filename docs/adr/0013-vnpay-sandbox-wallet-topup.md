# ADR-0013: Stateless VNPAY v2.1.0 Sandbox Wallet Top-Up

- **Status**: Accepted
- **Date**: 2026-11-23
- **Deciders**: Owner, Team Lead, Backend & Frontend Engineers
- **Technical Context**: Round 93 Milestone WP6 (R6 / D7), VNPAY Payment Gateway v2.1.0 (Sandbox), Stateless Signed `vnp_TxnRef`, Frozen PostgreSQL 18.6 Schema (`30` tables / `8` views), Pure Stdlib Integration

---

## 1. Context & Problem Statement

In Milestone WP3 (`ADR-0012`), customer wallet self-top-up (`POST /api/v1/me/wallet/topups/`) only supported a local simulated VietQR flow gated by `WALLET_SIMULATED_TOPUP_ENABLED`. For Round 93 (`R6 / D7`), customers need a real-gateway-compatible **VNPAY Sandbox** top-up workflow (including direct *"pay the missing amount"* shortcuts from `WALLET_INSUFFICIENT` exit alerts and ticket purchases) under strict constraints:

1. **Frozen Database Schema**: Zero changes to `db/01-schema.sql`, `db/02-seed.sql`, `models`, or `migrations` (`30` tables, `8` views, `38` unmanaged models).
2. **Zero New Dependencies**: No additions to `requirements/*.txt` or `package.json`.
3. **Zero Committed Secrets**: Repository configuration templates, compose files, tests, and documentation must never contain real or fake VNPAY merchant credentials (`VNPAY_TMN_CODE`, `VNPAY_HASH_SECRET`).
4. **Trust & Idempotency**: Browser return redirects can be forged or replayed and must never credit a wallet; only server-to-server IPN callbacks verified with constant-time HMAC-SHA512 may mutate the wallet ledger.

---

## 2. Decision Outcome

### 2.1. Stateless Signed `vnp_TxnRef` Token (`<= 94` Characters)

Because no new `payment_intent` table may be added to the frozen schema, `apps/payments/services/vnpay_client.py` encodes order metadata directly inside `vnp_TxnRef` using URL-safe base36 and an HMAC-SHA256 authentication tag (domain-separated key derived from `VNPAY_HASH_SECRET`):

```text
VP1-<customer_id_b36>-<amount_vnd_b36>-<created_ts_b36>-<nonce12hex>-<hmac32hex>
```

- Uses only `[0-9a-z-]`, unaffected by `urllib.parse.quote_plus`.
- Length stays well under `94` characters so `idempotency_key = f"vnpay-{txn_ref}"` fits inside `wallet_transaction.idempotency_key VARCHAR(100)`.
- `verify_and_parse_txn_ref` enforces canonical base36 round-trip and constant-time `hmac.compare_digest` verification.

### 2.2. Pure Stdlib VNPAY v2.1.0 Client & Canonical Signing

`apps/payments/services/vnpay_client.py` implements VNPAY v2.1.0 using only Python standard library modules (`hmac`, `hashlib`, `urllib.parse`, `unicodedata`, `secrets`, `zoneinfo`):

- Sorts all `vnp_*` parameters (non-empty, excluding `vnp_SecureHash` and `vnp_SecureHashType`) ascending by key.
- Encodes both keys and values with `urllib.parse.quote_plus`, joined with `&`.
- Signs with `HMAC-SHA512` lowercase hex digest (`128` hex characters).
- Verification requires strictly `128` lowercase hex characters and constant-time `hmac.compare_digest`.
- Uses `Asia/Ho_Chi_Minh` (`GMT+7`) for `vnp_CreateDate` and `vnp_ExpireDate` (with an injectable `now_fn` for boundary testing).
- Normalizes `vnp_OrderInfo` to diacritic-free ASCII within `255` characters.

### 2.3. Endpoint Split & Atomic Ledger Reuse

`apps/payments/` exposes four endpoints mounted under `/api/v1/`:

1. **`POST /api/v1/me/wallet/topups/vnpay/`** (`IsAuthenticated`, `IsCustomer`):
   - Rejects with `503 PROP-VNPAY-DISABLED` when `VNPAY_TMN_CODE` or `VNPAY_HASH_SECRET` is empty.
   - Enforces per-customer rate limiting (`VnpayTopupLimiter`, `429 PROP-VNPAY-RATE-LIMITED` + `Retry-After`).
   - Validates active customer (`403 PROP-CUSTOMER-INACTIVE`), active wallet (`409 PROP-WALLET-LOCKED`), and strict integer VND within `[VNPAY_TOPUP_MIN, VNPAY_TOPUP_MAX]` (`400 PROP-VNPAY-AMOUNT-RANGE`).
   - Extracts client IP via `get_client_ip(request)` honoring `settings.NUM_PROXIES`.
2. **`GET /api/v1/me/wallet/topups/vnpay/<str:txn_ref>/`** (`IsAuthenticated`, `IsCustomer`):
   - Verifies `txn_ref` signature and ownership (`parsed.customer_id == customer.id`; otherwise `404 MSG-4.4.1-M01`).
   - Polled by the frontend return page to determine `PENDING` vs `CREDITED`.
3. **`GET /api/v1/payments/vnpay/ipn/`** (`AllowAny`, `authentication_classes = []`):
   - Verifies `vnp_SecureHash` **first** with zero DB queries (`RspCode="97"` on failure).
   - Validates `vnp_TmnCode`, `vnp_TxnRef`, and non-deleted `Customer` (`"01"`), then `vnp_Amount == amount_vnd * 100` (`"04"`).
   - Inside `transaction.atomic()`, acquires `ensure_wallet_for_customer` + `Wallet.objects.select_for_update()`:
     - Existing `idempotency_key = f"vnpay-{txn_ref}"` -> `"02"` (`"Order already confirmed"`).
     - Non-`"00"` `vnp_ResponseCode` or `vnp_TransactionStatus` -> logs sanitized status and returns `"00"` without crediting.
     - Both `"00"` -> delegates to `credit_wallet(..., kind="TOPUP_VIETQR", idempotency_key=f"vnpay-{txn_ref}")` -> `"00"`.
4. **`GET /api/v1/payments/vnpay/return/`** (`AllowAny`, `authentication_classes = []`):
   - **Never mutates database state**.
   - Verifies signature + `txn_ref` and redirects (`302`) to validated `VNPAY_FRONTEND_RESULT_URL` (default `/wallet/vnpay-return`) with only `?status=pending|failed|invalid_signature&txn_ref=...&code=...`.

### 2.4. Configuration, OpenAPI Hook & Production Guard

- `config/settings/base.py`, `.env.example`, and `docker-compose.yml` declare all 9 `VNPAY_*` keys identically (`VNPAY_TMN_CODE`, `VNPAY_HASH_SECRET`, `VNPAY_PAYMENT_URL`, `VNPAY_RETURN_URL`, `VNPAY_FRONTEND_RESULT_URL`, `VNPAY_TOPUP_MIN`, `VNPAY_TOPUP_MAX`, `VNPAY_TIMEOUT_MINUTES`, `VNPAY_ALLOW_SANDBOX_IN_PRODUCTION`), with credentials defaulting to empty strings.
- `config/settings/production.py` raises `ImproperlyConfigured` if both credentials are set, `VNPAY_PAYMENT_URL` contains `sandbox.vnpayment.vn`, and `VNPAY_ALLOW_SANDBOX_IN_PRODUCTION` is `False`.
- `apps/payments/openapi.py` registers `postprocess_vnpay_public_security` in `SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"]` to mark the IPN and Return endpoints public (`security: []`) without editing `apps/core/openapi.py`.
- `GET /api/v1/me/wallet/` exposes read-only `topup_channels` metadata so the frontend enables/disables VNPAY dynamically without receiving any credentials.

---

## 3. Alternatives Considered & Rejected

1. **Adding a `vnpay_transaction` table**: Rejected because the Round 93 schema is frozen at `30` tables / `8` views (`db/**` immutable).
2. **Crediting the wallet in the browser Return URL**: Rejected due to client-side tampering and network drop risks.
3. **Installing a third-party `vnpay` PyPI package**: Rejected by the zero-new-dependency constraint and because the official VNPAY sample code required hardening (`hmac.compare_digest`, `quote_plus` canonicalization, no secret logging).

---

## 4. Consequences & Trade-offs

- **Positive**: Zero DB migrations, race-free idempotent wallet crediting via `credit_wallet`, strict separation of Return vs IPN trust boundaries, and zero credentials in source control.
- **Trade-off**: Because transactions are stateless until IPN arrival, there is no pre-IPN `PENDING` list persisted in PostgreSQL; once IPN arrives, `wallet_transaction` records the permanent ledger entry with `idempotency_key = vnpay-{txn_ref}`.
- **Verification Boundary**: Real VNPAY sandbox gateway checkout and real VNPAY server-to-server IPN callbacks remain `UNVERIFIED` until the Owner configures sandbox merchant credentials; all local flows are verified via unit/concurrency tests and `.agents/93-tools/vnpay_ipn_inject.py` (`REAL+INJECTION`).


---

## 5. Round 94 Amendment (WP1 / Decision B / D1 — `TOPUP_VNPAY` Ledger Kind)

- **Date**: 2026-11-24
- **Context**: In Round 93 (`Section 2.3` bullet 4 above), VNPAY IPN credits temporarily reused `kind="TOPUP_VIETQR"` because the Round 93 schema was frozen. As a result, `wallet_transaction` and `GET /api/v1/reports/statistics/summary/` mixed VNPAY top-ups into the VietQR bucket.
- **Decision (Team Lead Decision B / D1)**:
  1. **Additive Schema Extension**: `ck_wallet_tx_kind_enum` and `COMMENT ON COLUMN wallet_transaction.kind` in `db/01-schema.sql` (and idempotent upgrade `db/upgrades/0013-wallet-kind-vnpay.sql`) are extended with `'TOPUP_VNPAY'`. Structural parity remains `"30 8 73 0 92 23"`.
  2. **Ledger & Channel Separation**: `apps/payments/services/topup.py` now calls `credit_wallet(..., kind="TOPUP_VNPAY", ...)` (`KIND_CHOICES` / `CREDIT_KINDS` in `apps/wallet/`), while the local simulated VietQR endpoint (`simulated_vietqr_topup`) explicitly stays on `kind="TOPUP_VIETQR"`.
  3. **No Historical Data Migration**: Because `wallet_transaction` is strictly append-only (`trg_block_wallet_transaction_mutations` blocks `UPDATE`/`DELETE`) and no real VNPAY gateway transactions existed in the Owner database prior to this amendment, no historical ledger rows are rewritten.
  4. **Statistics Contract**: `non_revenue` in `GET /api/v1/reports/statistics/summary/` exposes `topup_vnpay_total` (`Decimal`) alongside `topup_cash_total` and `topup_vietqr_total`, all summed into `wallet_topup_total`.

---

## 6. Round 94 Amendment (WP5 / L6 / D5 — VNPAY Signature Compatibility, Contradictions & HPP Hardening)

- **Date**: 2026-11-24
- **Context**: Without live sandbox merchant credentials (`VNPAY_TMN_CODE` / `VNPAY_HASH_SECRET` remain empty in source control), compatibility of `verify_vnpay_signature` with real VNPAY v2.1.0 IPN callbacks had to be established directly from official VNPAY documentation and sample kits, and raw HTTP query parsing had to be hardened against HTTP Parameter Pollution (HPP) and malformed percent-encoding.

### 6.1. Official VNPAY Sources Inspected (Accessed `2026-11-24`)

1. **`https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html`** (`92,867` bytes, accessed `2026-11-24T08:25:08Z`):
   - **Sample Payment URL** (`pay.html:423`): uses `+` for spaces and uppercase `%3A` / `%2F` (`vnp_OrderInfo=Thanh+toan+don+hang+%3A5`, `vnp_ReturnUrl=https%3A%2F%2Fdomainmerchant.vn%2FReturnUrl`).
   - **Sample IPN & ReturnUrl** (`pay.html:1663`, `pay.html:2727`): uses `+` for spaces, uppercase `%3A`, and 128-character lowercase hex `vnp_SecureHash` (`vnp_OrderInfo=Thanh+toan+don+hang+thoi+gian%3A+2023-12-07+17%3A00%3A44`).
   - **IPN Retry Policy** (`pay.html:1874-1878`): `"RspCode: 00, 02 là mã lỗi IPN của merchant phản hồi đã cập nhật được tình trạng giao dịch. VNPAY kết thúc luồng"` and `"RspCode: 01, 04, 97, 99 hoặc IPN timeout là mã lỗi IPN merchant không cập nhật được tình trạng giao dịch. VNPAY bật cơ chế retry IPN"` (max `10` retries, `5` minutes apart).
   - **PHP IPN Sample (`#ipn_payment_php`)**: `"ksort($inputData);"` ... `"$hashData = $hashData . '&' . urlencode($key) . \"=\" . urlencode($value);"` ... `"$secureHash = hash_hmac('sha512', $hashData, $vnp_HashSecret);"`, checking `"if ($inputData['vnp_ResponseCode'] == '00' || $inputData['vnp_TransactionStatus'] == '00')"`.
   - **Java Samples (`#init_payment_java`, `#return_payment_java`)**: `"if ((fieldValue != null) && (fieldValue.length() > 0))"` ... `"hashData.append(URLEncoder.encode(fieldValue, StandardCharsets.US_ASCII.toString()));"` (note: the `#ipn_payment_java` tab in `pay.html` is HTML-truncated mid-loop; the complete handler appears in `#return_payment_java`).
   - **C# IPN Sample (`#ipn_payment_csharp`)**: `"if (vnp_ResponseCode == \"00\" && vnp_TransactionStatus == \"00\")"` and `"bool checkSignature = vnpay.ValidateSignature(vnp_SecureHash, vnp_HashSecret);"`.
   - **Python IPN Sample (`#ipn_payment_python`)**: `"vnp.responseData = inputData.dict()"` and `"if vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):"`.
   - **NodeJS Sample (`#init_payment_nodejs`, `#ipn_payment_nodejs`, `#return_payment_nodejs`)**: `"var signData = querystring.stringify(vnp_Params, { encode: false });"` and `"var signed = hmac.update(new Buffer(signData, 'utf-8')).digest(\"hex\");"`.
2. **`https://sandbox.vnpayment.vn/apis/files/VNPAY%20Payment%20Gateway_Techspec%20Post%20method%202.1.0-VN.pdf`** (`1,069,436` bytes, `39` pages, accessed `2026-11-24T08:26:00Z`):
   - **Section `2.5.3.2` (p. 15)**: `"Quy tắc và Phương thức sử dụng giống với bước merchant gửi sang VNPAY"`.
   - **IPN Result Table (p. 35)**: `"00"`, `"01"`, `"02"`, `"03"`, `"97"`, `"99"`.
   - **Section `2.5.8` (pp. 37–39)**: Legacy 2.0.x snippets state `"băm với giải thuật MD5"` immediately above `Config.hmacSHA512(...)`, and construct `hashData` / `signData` / `$hashdata` without URL-encoding (`fieldName + '=' + fieldValue`).
3. **`https://sandbox.vnpayment.vn/apis/downloads/`** (`7,484` bytes, accessed `2026-11-24T08:25:24Z`): lists Techspec PDFs and mobile SDKs only (no downloadable web sample `.zip` archive).
4. **`https://sandbox.vnpayment.vn/apis/vnpay-demo/`** (`12,399` bytes, accessed `2026-11-24T08:25:24Z`): documents sandbox demo test cards (including NCB `9704198526191432198`, `NGUYEN VAN A`, `07/15`, OTP `123456`).

### 6.2. Documented Contradictions in Official VNPAY Sources

1. **URL-Encoded vs. Unencoded `hashData`**: `pay.html` sample URLs (`+`, `%3A`, `%2F`), PHP `urlencode()`, Java `URLEncoder.encode()`, and Techspec p. 15 use URL-encoded `hashData`, whereas `pay.html` NodeJS (`{ encode: false }`) and Techspec pp. 37–39 legacy snippets do not URL-encode `hashData`.
2. **Empty Parameter Values**: Java (`fieldValue.length() > 0`) and C# (`!string.IsNullOrEmpty`) exclude empty parameters from `hashData`, whereas `#ipn_payment_php` iterates `$_GET` without filtering `""`.
3. **Success Condition (`&&` vs `||`)**: `#ipn_payment_csharp` and Techspec p. 15 require both `vnp_ResponseCode == "00"` and `vnp_TransactionStatus == "00"`, whereas `#ipn_payment_php` uses `||`.
4. **`~` and `*` Encoding**: Python `urllib.parse.quote_plus` leaves `~` unencoded and encodes `*` as `%2A`; PHP `urlencode` encodes both (`%7E`, `%2A`); Java `URLEncoder` encodes `~` as `%7E` and leaves `*` unencoded. On outbound `build_payment_url`, `sanitize_order_info` restricts `vnp_OrderInfo` to `[A-Za-z0-9 .:-]`, guaranteeing identical hashes across Python, PHP, and Java.

### 6.3. Safer Reading & HPP / Strict Query Hardening

- **Single Canonical Verification Rule (No Signature Weakening)**: `verify_vnpay_signature` continues to accept ONLY HMAC-SHA512 over `canonical_vnpay_query` (`quote_plus`, ascending key sort, excluding empty values, `vnp_SecureHash`, and `vnp_SecureHashType`). Unencoded (NodeJS), `%20`-encoded (`urllib.parse.quote`), PHP empty-included, Java unencoded-`*`, and lowercase-`%xx` hash variants are strictly rejected (`RspCode="97"`). Transport-level wire equivalents that decode to the same UTF-8 values (`+` vs `%20`, `%3a` vs `%3A`, non-alphabetical key order) are normalized deterministically after strict decoding and accepted iff the canonical signature matches.
- **Strict Raw `QUERY_STRING` Extraction & HPP Guard (`extract_vnpay_query_params`)**: `VnpayIpnView` and `VnpayReturnView` pass raw `request.META["QUERY_STRING"]` to `process_vnpay_ipn` and `verify_vnpay_return`. `extract_vnpay_query_params` parses with `urllib.parse.parse_qsl(..., keep_blank_values=True, encoding="utf-8", errors="strict")` and returns `None` (failing closed to `"97"` with `0` DB queries in IPN, and `status=invalid_signature&code=97` without `txn_ref` in Return) on any `UnicodeDecodeError` (e.g. `%FF%FE`) or ANY duplicate `vnp_*` parameter (including `vnp_SecureHash` and `vnp_SecureHashType`). `verify_vnpay_signature` also enforces single-value checks if called directly with a Django `QueryDict`.
- **Both Status Codes Required**: `process_vnpay_ipn` continues to require `vnp_ResponseCode == "00"` **and** `vnp_TransactionStatus == "00"` before crediting the wallet.
- **`UNVERIFIED` Until Live Sandbox Keys**: Because real `VNPAY_TMN_CODE` and `VNPAY_HASH_SECRET` are absent, live VNPAY Sandbox gateway behavior (specifically whether the live gateway omits or includes empty values such as `vnp_BankTranNo=`, or sends `~`/`*` in gateway-added fields) remains `UNVERIFIED`. The Owner runbook instructs operators to inspect the raw `QUERY_STRING` against Contradiction #1–#4 first if the first live sandbox IPN returns `RspCode="97"`.
