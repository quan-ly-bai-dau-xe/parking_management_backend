# ADR-0012: Customer Prepaid Wallet, Immutable Append-Only Ledger, and Self-Service Portal

- **Status**: Accepted
- **Date**: 2026-11-18
- **Deciders**: Owner, Team Lead, Backend & Frontend Engineers
- **Technical Context**: Round 92 Milestone WP3 (Customer Wallet & Self-Service), PostgreSQL 18.6 Append-Only Financial Ledger, Idempotent Concurrency Locking, Self-Service `/api/v1/me/`

---

## 1. Context & Problem Statement

Prior to Milestone WP3, the system had no persistent prepaid customer wallet:
1. Customer self-service pages (`CustomerProfilePage`, `CustomerVehiclePage`, `CustomerTicketPage`, `CustomerOverviewPage`) relied on client-side simulation (`IS_PAYMENT_SIMULATION = true`, hardcoded `250,000đ` balance) and invoked staff-only endpoints (`/api/v1/vehicles/`, `/api/v1/tickets/`, `/api/v1/customers/{id}/`) that reject `CUSTOMER` accounts with HTTP `403`.
2. `payment.method` only permitted `CASH` and `VIETQR`, leaving no relational backing for prepaid wallet deductions at ticket purchase, checkout (WP4), or automatic renewal (WP4).

We need an enterprise-grade, concurrency-safe, auditable wallet subsystem in PostgreSQL 18.6 and Django REST Framework while preserving existing Schema v2 invariants (`ON DELETE RESTRICT`, soft-delete lifecycle, `row_version` OCC, and zero `DROP` statements in `db/01-schema.sql`).

---

## 2. Decision Outcome

### 2.1. Relational Schema (`wallet`, `wallet_transaction`, `payment.method`)

1. **Table `wallet`** (10 columns, 2 FKs `ON DELETE RESTRICT`, soft-deletable):
   - Stores one active wallet per active customer via partial unique index `uq_wallet_customer_active ON wallet (customer_id) WHERE deleted_at IS NULL`.
   - `balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00` with `CHECK (balance >= 0)`.
   - `currency VARCHAR(3) NOT NULL DEFAULT 'VND'` (`CHECK (currency IN ('VND'))`), `status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'` (`ACTIVE`, `LOCKED`, `CLOSED`).
   - Protected by `trg_wallet_row_version`, `trg_guard_wallet_immutable` (`BEFORE DELETE`), `trg_guard_soft_delete_and_restore_wallet` (blocks soft-deletion when `balance > 0`, verifies active `customer` on restore), and `trg_audit_soft_delete_and_restore_wallet`.
2. **Table `wallet_transaction`** (12 columns, 2 FKs `ON DELETE RESTRICT`, strictly append-only):
   - Records every ledger mutation with signed `amount NUMERIC(14, 2) NOT NULL` (`amount <> 0`, positive for `CREDIT`, negative for `DEBIT`), `balance_after NUMERIC(14, 2) >= 0`, `transaction_type IN ('CREDIT', 'DEBIT')`, `kind IN ('TOPUP_CASH', 'TOPUP_VIETQR', 'TICKET_PURCHASE', 'TICKET_RENEWAL', 'PARKING_FEE', 'REFUND', 'ADJUSTMENT')`, `idempotency_key VARCHAR(100) UNIQUE NOT NULL`, optional `(reference_type, reference_id)`, `note`, `created_by_id`, and `created_at`.
   - Protected by `trg_block_wallet_transaction_mutations` (`BEFORE UPDATE OR DELETE` calling `fn_block_wallet_transaction_mutations()`), rejecting all mutations with `SQLSTATE 23514`.
   - Both `wallet` and `wallet_transaction` are added to `v_forbidden_tables` in `fn_controlled_purge()`.
   - Consistency invariant: for every wallet, `SUM(wallet_transaction.amount) == wallet.balance` (verified by `manage.py reconcile_wallets` and automated tests).
3. **Extend `payment.method`**:
   - Expand `ck_payment_method_enum` to `CHECK (method IN ('CASH', 'VIETQR', 'WALLET'))`.
   - When a customer pays with their wallet, a `Payment(method='WALLET', status='PAID')` record and a `WalletTransaction(transaction_type='DEBIT')` ledger row are committed together inside one `transaction.atomic()` block.

### 2.2. Single-Service Money Logic (`apps/wallet/services/wallet.py`)

All wallet balance mutations execute exclusively through `credit_wallet` and `debit_wallet`:
- Both acquire `Wallet.objects.select_for_update()` inside `transaction.atomic()` before reading balance or creating a ledger row.
- **Idempotency check executes inside the lock before balance checks**: retrying a successful debit with the same `idempotency_key` returns the original `WalletTransaction` without double-debiting or raising a false insufficient-balance error. Reusing an `idempotency_key` with different parameters raises HTTP `409 Conflict` (`PROP-WALLET-IDEMPOTENCY-CONFLICT`).
- `debit_wallet` never allows partial debits or negative balances; when `wallet.balance < amount`, it raises `InsufficientWalletBalanceError` (HTTP `409 Conflict`, `PROP-WALLET-INSUFFICIENT`).

### 2.3. Top-Up Channels & Simulated VietQR Guard

1. **Staff Cash Top-Up (`POST /api/v1/customers/{id}/wallet/topup/`)**: Restricted to `IsEmployeeOrManager`, credits via `credit_wallet(..., kind="TOPUP_CASH")`, and records `ActivityLog` (`WALLET_STAFF_TOPUP`) without PII.
2. **Customer Self Top-Up (`POST /api/v1/me/wallet/topups/`)**: Controlled by `settings.WALLET_SIMULATED_TOPUP_ENABLED` (`False` in `base.py` / production; `True` in `local.py` and `test.py`). When disabled, returns HTTP `403` (`PROP-WALLET-SIMULATED-DISABLED`). Real payment gateway integration (VietQR webhook / VNPAY callback) is explicitly deferred to a future decision.

### 2.4. Customer Self-Service (`/api/v1/me/`) & Ticket Cancel Policy

- `IsCustomer` permission enforces authenticated active `Account(role='CUSTOMER')` linked to an active `Customer` profile (cached on `request._cached_customer` for zero extra queries).
- All `/api/v1/me/*` endpoints strictly scope queries to `customer.id`, returning `404` for resources owned by other customers.
- `POST /api/v1/me/tickets/` purchases a ticket using `ticket_type.default_price` from DB, selects/validates a compatible slot, creates `Ticket` + `Payment(method='WALLET', status='PAID')`, and calls `debit_wallet(..., kind="TICKET_PURCHASE")` atomically.
- `POST /api/v1/me/tickets/{lookup}/cancel/`: Per SRS 4.6 and `03-delete-rules-catalog.md`, self-service cancellation with automatic refund of `PAID` tickets is not authorized; paid tickets return HTTP `409` (`PROP-4.6.4-P06`) without silent refunds.

### 2.5. Idempotent Upgrade Path & ERD Caveat

- `db/upgrades/0012-wallet.sql` upgrades existing Schema v2 databases idempotently (`IF NOT EXISTS`, guarded constraint/trigger checks, and `0.00 VND` wallet backfill for active customers).
- **ERD Status (`UNVERIFIED` in WP3)**: `db/03-erd.asta` and `db/04..09*.png` are generated via Astah UML and were not edited manually. They require regenerating to add `wallet` and `wallet_transaction` (with their columns and FK links to `customer`, `account`, and `wallet`).

---

## 3. Consequences

- **Positive**: Race-free balance updates under concurrency, tamper-evident immutable ledger, safe idempotent retries, clean separation between customer self-service (`/api/v1/me/`) and staff operations (`/api/v1/`).
- **Trade-offs / Deferred**: Real VietQR webhook verification and self-service paid-ticket refund policy require explicit Owner approval in a future milestone.
