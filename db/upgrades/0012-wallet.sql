-- =============================================================================
-- FILE: db/upgrades/0012-wallet.sql
-- TARGET ENGINE: PostgreSQL 18.6
-- DESCRIPTION:
--   Idempotent upgrade script for ADR-0012 (Customer Prepaid Wallet & Append-Only Ledger).
--   Safe to execute multiple times against an existing Schema v2 database.
-- USAGE:
--   docker compose exec -T db psql -U parking_user -d parking_db -v ON_ERROR_STOP=1 < db/upgrades/0012-wallet.sql
-- =============================================================================

BEGIN;

SET client_encoding = 'UTF8';

-- 1. Extend payment.method CHECK constraint to allow 'WALLET'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = 'public.payment'::regclass
          AND c.conname = 'ck_payment_method_enum'
          AND pg_get_constraintdef(c.oid) NOT LIKE '%WALLET%'
    ) THEN
        ALTER TABLE payment DROP CONSTRAINT ck_payment_method_enum;
        ALTER TABLE payment ADD CONSTRAINT ck_payment_method_enum
            CHECK (method IN ('CASH', 'VIETQR', 'WALLET'));
    ELSIF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = 'public.payment'::regclass
          AND c.conname = 'ck_payment_method_enum'
    ) THEN
        ALTER TABLE payment ADD CONSTRAINT ck_payment_method_enum
            CHECK (method IN ('CASH', 'VIETQR', 'WALLET'));
    END IF;
END $$;

COMMENT ON TABLE payment IS 'Unified financial payment transactions supporting CASH, VIETQR, and WALLET methods and targeting exactly one session, ticket, or ticket_renewal (Trang chủ, Main Page, Quản lý vé, Lịch sử ra/vào, TL-07, ADR-0012).';
COMMENT ON COLUMN payment.method IS 'Payment method: CASH ("Tiền mặt"), VIETQR ("QR" / "VietQR"), or WALLET ("Ví khách hàng") (TL-07, ADR-0012).';

-- 2. Create table: wallet
CREATE TABLE IF NOT EXISTS wallet (
    id BIGSERIAL,
    customer_id BIGINT NOT NULL,
    balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    currency VARCHAR(3) NOT NULL DEFAULT 'VND',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_wallet PRIMARY KEY (id),
    CONSTRAINT fk_wallet_customer FOREIGN KEY (customer_id)
        REFERENCES customer (id) ON DELETE RESTRICT,
    CONSTRAINT fk_wallet_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_wallet_balance_nonnegative CHECK (balance >= 0),
    CONSTRAINT ck_wallet_currency_enum CHECK (currency IN ('VND')),
    CONSTRAINT ck_wallet_status_enum CHECK (status IN ('ACTIVE', 'LOCKED', 'CLOSED')),
    CONSTRAINT ck_wallet_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_wallet_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_wallet_customer_active
    ON wallet (customer_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_wallet_status_active
    ON wallet (status)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE wallet IS 'Customer prepaid electronic wallet storing non-negative VND balance with OCC row_version and soft-delete lifecycle (ADR-0012, TL-98).';
COMMENT ON COLUMN wallet.id IS 'Primary key identifier of the customer wallet.';
COMMENT ON COLUMN wallet.customer_id IS 'Foreign key referencing owning customer (1:1 among active records via uq_wallet_customer_active, ON DELETE RESTRICT).';
COMMENT ON COLUMN wallet.balance IS 'Current available wallet balance in VND (NUMERIC(14,2), must be >= 0).';
COMMENT ON COLUMN wallet.currency IS 'ISO currency code of the wallet (default VND).';
COMMENT ON COLUMN wallet.status IS 'Wallet operational status: ACTIVE, LOCKED, or CLOSED.';
COMMENT ON COLUMN wallet.row_version IS 'Optimistic concurrency control version counter incremented automatically on update.';
COMMENT ON COLUMN wallet.created_at IS 'Record creation timestamp (TIMESTAMPTZ).';
COMMENT ON COLUMN wallet.updated_at IS 'Record last modification timestamp (TIMESTAMPTZ).';
COMMENT ON COLUMN wallet.deleted_at IS 'Soft deletion timestamp; NULL indicates active record (ADR-0003).';
COMMENT ON COLUMN wallet.deleted_by IS 'Foreign key referencing the account that performed soft deletion (ADR-0003).';

-- 3. Create table: wallet_transaction
CREATE TABLE IF NOT EXISTS wallet_transaction (
    id BIGSERIAL,
    wallet_id BIGINT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    balance_after NUMERIC(14, 2) NOT NULL,
    transaction_type VARCHAR(10) NOT NULL,
    kind VARCHAR(30) NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    reference_type VARCHAR(50) NULL,
    reference_id BIGINT NULL,
    note TEXT NULL,
    created_by_id BIGINT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_wallet_transaction PRIMARY KEY (id),
    CONSTRAINT uq_wallet_tx_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT fk_wallet_tx_wallet FOREIGN KEY (wallet_id)
        REFERENCES wallet (id) ON DELETE RESTRICT,
    CONSTRAINT fk_wallet_tx_created_by FOREIGN KEY (created_by_id)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_wallet_tx_amount_nonzero CHECK (amount <> 0),
    CONSTRAINT ck_wallet_tx_balance_after_nonnegative CHECK (balance_after >= 0),
    CONSTRAINT ck_wallet_tx_type_enum CHECK (transaction_type IN ('CREDIT', 'DEBIT')),
    CONSTRAINT ck_wallet_tx_type_amount_sign CHECK (
        (transaction_type = 'CREDIT' AND amount > 0)
        OR (transaction_type = 'DEBIT' AND amount < 0)
    ),
    CONSTRAINT ck_wallet_tx_kind_enum CHECK (
        kind IN (
            'TOPUP_CASH',
            'TOPUP_VIETQR',
            'TICKET_PURCHASE',
            'TICKET_RENEWAL',
            'PARKING_FEE',
            'REFUND',
            'ADJUSTMENT'
        )
    ),
    CONSTRAINT ck_wallet_tx_idempotency_nonempty CHECK (btrim(idempotency_key) <> ''),
    CONSTRAINT ck_wallet_tx_reference_type_nonempty CHECK (
        reference_type IS NULL OR btrim(reference_type) <> ''
    )
);

CREATE INDEX IF NOT EXISTS idx_wallet_tx_wallet_created
    ON wallet_transaction (wallet_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_wallet_tx_reference
    ON wallet_transaction (reference_type, reference_id)
    WHERE reference_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_wallet_tx_kind_created
    ON wallet_transaction (kind, created_at DESC);

COMMENT ON TABLE wallet_transaction IS 'Strictly append-only financial ledger recording every wallet credit and debit with idempotency key and post-transaction balance snapshot (ADR-0012, TL-98).';
COMMENT ON COLUMN wallet_transaction.id IS 'Primary key identifier of the wallet ledger entry.';
COMMENT ON COLUMN wallet_transaction.wallet_id IS 'Foreign key referencing parent wallet (ON DELETE RESTRICT).';
COMMENT ON COLUMN wallet_transaction.amount IS 'Signed transaction amount in VND (NUMERIC(14,2); positive for CREDIT, negative for DEBIT, never 0).';
COMMENT ON COLUMN wallet_transaction.balance_after IS 'Wallet balance immediately after this transaction (NUMERIC(14,2), must be >= 0).';
COMMENT ON COLUMN wallet_transaction.transaction_type IS 'Ledger entry direction: CREDIT or DEBIT.';
COMMENT ON COLUMN wallet_transaction.kind IS 'Business classification: TOPUP_CASH, TOPUP_VIETQR, TICKET_PURCHASE, TICKET_RENEWAL, PARKING_FEE, REFUND, or ADJUSTMENT.';
COMMENT ON COLUMN wallet_transaction.idempotency_key IS 'Globally unique idempotency key preventing duplicate ledger mutations on retries.';
COMMENT ON COLUMN wallet_transaction.reference_type IS 'Optional domain entity type linked to this ledger entry (e.g., PAYMENT, TICKET, TICKET_RENEWAL, VEHICLE_SESSION).';
COMMENT ON COLUMN wallet_transaction.reference_id IS 'Optional primary key of the referenced domain entity.';
COMMENT ON COLUMN wallet_transaction.note IS 'Optional human-readable description or staff/system note for the transaction.';
COMMENT ON COLUMN wallet_transaction.created_by_id IS 'Optional foreign key referencing the acting account; NULL for automated system operations.';
COMMENT ON COLUMN wallet_transaction.created_at IS 'Immutable ledger entry creation timestamp (TIMESTAMPTZ).';

-- 4. Functions & guarded trigger attachments
CREATE OR REPLACE FUNCTION fn_block_wallet_transaction_mutations()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'Sổ cái giao dịch ví là bảng chỉ ghi (append-only), không cho phép cập nhật hoặc xóa.'
        USING ERRCODE = 'check_violation',
              HINT = 'wallet_transaction is strictly append-only (ADR-0012, TL-98).';
END;
$$;

COMMENT ON FUNCTION fn_block_wallet_transaction_mutations() IS 'Enforces append-only immutability on wallet_transaction by rejecting UPDATE and DELETE operations (ADR-0012, TL-98).';

CREATE OR REPLACE FUNCTION fn_controlled_purge(
    p_table_name VARCHAR DEFAULT NULL,
    p_retention INTERVAL DEFAULT INTERVAL '30 days',
    p_dry_run BOOLEAN DEFAULT TRUE,
    p_purged_by BIGINT DEFAULT NULL,
    p_target_id BIGINT DEFAULT NULL
)
RETURNS TABLE (
    table_name VARCHAR,
    eligible_count BIGINT,
    purged_count BIGINT,
    status VARCHAR,
    details TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_allowed_tables VARCHAR[] := ARRAY[
        'news', 'notification', 'slot_reservation', 'plate_blacklist',
        'parking_slot', 'parking_zone', 'parking_floor', 'parking_lot', 'parking_gate',
        'vehicle', 'customer', 'employee', 'account',
        'ticket_type', 'vehicle_type', 'position'
    ];
    v_forbidden_tables VARCHAR[] := ARRAY[
        'ticket', 'ticket_renewal', 'payment', 'vehicle_entry_exit_log', 'activity_log', 'system_alert',
        'wallet', 'wallet_transaction',
        'administrative_province', 'administrative_district', 'administrative_ward'
    ];
    v_tbl VARCHAR;
    v_eligible BIGINT;
    v_purged BIGINT;
    v_skipped BIGINT;
    v_row_id BIGINT;
    v_cutoff TIMESTAMPTZ;
    v_target_exists BOOLEAN;
    v_target_deleted_at TIMESTAMPTZ;
    v_target_anonymized BOOLEAN;
    v_nonce TEXT;
    v_sql TEXT;
BEGIN
    IF p_retention IS NULL OR p_retention < INTERVAL '30 days' THEN
        RAISE EXCEPTION 'Khoảng thời gian lưu trữ tối thiểu (p_retention) không hợp lệ (yêu cầu tối thiểu 30 ngày).'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF p_target_id IS NOT NULL AND p_table_name IS NULL THEN
        RAISE EXCEPTION 'Phải chỉ định tên bảng (p_table_name) khi purge theo ID cụ thể (p_target_id).'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    v_cutoff := CURRENT_TIMESTAMP - p_retention;

    IF p_table_name IS NOT NULL THEN
        IF lower(btrim(p_table_name)) = ANY(v_forbidden_tables) THEN
            RAISE EXCEPTION 'Bảng % nằm trong danh mục bất biến/không thể xóa, nghiêm cấm purge.', p_table_name
                USING ERRCODE = '55000';
        END IF;
        IF NOT (lower(btrim(p_table_name)) = ANY(v_allowed_tables)) THEN
            RAISE EXCEPTION 'Bảng % không nằm trong danh mục bảng được phép purge.', p_table_name
                USING ERRCODE = 'invalid_parameter_value';
        END IF;
    END IF;

    FOREACH v_tbl IN ARRAY CASE
        WHEN p_table_name IS NOT NULL THEN ARRAY[lower(btrim(p_table_name))]
        ELSE v_allowed_tables
    END
    LOOP
        IF p_target_id IS NOT NULL THEN
            v_target_exists := FALSE;
            IF v_tbl = 'customer' THEN
                v_sql := format('SELECT TRUE, deleted_at, is_anonymized FROM %I WHERE id = $1', v_tbl);
                EXECUTE v_sql INTO v_target_exists, v_target_deleted_at, v_target_anonymized USING p_target_id;
            ELSE
                v_sql := format('SELECT TRUE, deleted_at, TRUE FROM %I WHERE id = $1', v_tbl);
                EXECUTE v_sql INTO v_target_exists, v_target_deleted_at, v_target_anonymized USING p_target_id;
            END IF;

            IF NOT COALESCE(v_target_exists, FALSE) THEN
                RAISE EXCEPTION 'Bản ghi cần purge (ID: %) không tồn tại trên bảng %.', p_target_id, v_tbl
                    USING ERRCODE = 'no_data_found';
            END IF;

            IF v_target_deleted_at IS NULL THEN
                RAISE EXCEPTION 'Bản ghi (ID: %) trên bảng % đang hoạt động (deleted_at IS NULL). Nghiêm cấm purge dữ liệu chưa xóa mềm.', p_target_id, v_tbl
                    USING ERRCODE = '55000',
                          HINT = 'Only records currently in trash (deleted_at IS NOT NULL) can be purged (TL-24).';
            END IF;

            IF v_target_deleted_at >= v_cutoff THEN
                RAISE EXCEPTION 'Bản ghi (ID: %) trên bảng % chưa đủ thời gian lưu giữ trong thùng rác (retention: %).', p_target_id, v_tbl, p_retention
                    USING ERRCODE = '55000';
            END IF;

            IF v_tbl = 'customer' AND NOT COALESCE(v_target_anonymized, FALSE) THEN
                RAISE EXCEPTION 'Khách hàng (ID: %) chưa được ẩn danh hóa dữ liệu cá nhân theo Nghị định 13/2023/NĐ-CP, không được phép purge.', p_target_id
                    USING ERRCODE = '55000';
            END IF;

            v_eligible := 1;
        ELSE
            IF v_tbl = 'customer' THEN
                v_sql := format(
                    'SELECT count(*) FROM %I WHERE deleted_at IS NOT NULL AND deleted_at < $1 AND is_anonymized = TRUE',
                    v_tbl
                );
            ELSE
                v_sql := format(
                    'SELECT count(*) FROM %I WHERE deleted_at IS NOT NULL AND deleted_at < $1',
                    v_tbl
                );
            END IF;
            EXECUTE v_sql INTO v_eligible USING v_cutoff;
        END IF;

        IF p_dry_run THEN
            table_name := v_tbl;
            eligible_count := v_eligible;
            purged_count := 0;
            status := 'DRY_RUN';
            details := format('Simulated purge: %s rows eligible in trash older than %s.', v_eligible, p_retention);
            RETURN NEXT;
        ELSE
            IF v_eligible > 0 THEN
                v_nonce := gen_random_uuid()::text;
                PERFORM set_config('app.purge_internal_nonce', v_nonce, true);

                v_purged := 0;
                v_skipped := 0;

                IF p_target_id IS NOT NULL THEN
                    IF v_tbl = 'account' THEN
                        DELETE FROM persistent_login_token WHERE account_id = p_target_id;
                        DELETE FROM password_reset_token WHERE account_id = p_target_id;
                    END IF;

                    IF v_tbl = 'customer' THEN
                        v_sql := format('DELETE FROM %I WHERE id = $2 AND deleted_at IS NOT NULL AND deleted_at < $1 AND is_anonymized = TRUE', v_tbl);
                    ELSE
                        v_sql := format('DELETE FROM %I WHERE id = $2 AND deleted_at IS NOT NULL AND deleted_at < $1', v_tbl);
                    END IF;

                    BEGIN
                        EXECUTE v_sql USING v_cutoff, p_target_id;
                        GET DIAGNOSTICS v_purged = ROW_COUNT;
                    EXCEPTION WHEN foreign_key_violation OR restrict_violation THEN
                        RAISE EXCEPTION 'Bản ghi (ID: %) trên bảng % đang được tham chiếu bởi dữ liệu khác, không thể purge.', p_target_id, v_tbl
                            USING ERRCODE = 'foreign_key_violation';
                    END;
                ELSE
                    IF v_tbl = 'customer' THEN
                        v_sql := format('SELECT id FROM %I WHERE deleted_at IS NOT NULL AND deleted_at < $1 AND is_anonymized = TRUE', v_tbl);
                    ELSE
                        v_sql := format('SELECT id FROM %I WHERE deleted_at IS NOT NULL AND deleted_at < $1', v_tbl);
                    END IF;

                    FOR v_row_id IN EXECUTE v_sql USING v_cutoff
                    LOOP
                        BEGIN
                            IF v_tbl = 'account' THEN
                                DELETE FROM persistent_login_token WHERE account_id = v_row_id;
                                DELETE FROM password_reset_token WHERE account_id = v_row_id;
                            END IF;

                            EXECUTE format('DELETE FROM %I WHERE id = $1', v_tbl) USING v_row_id;
                            v_purged := v_purged + 1;
                        EXCEPTION WHEN foreign_key_violation OR restrict_violation THEN
                            v_skipped := v_skipped + 1;
                        END;
                    END LOOP;
                END IF;

                PERFORM set_config('app.purge_internal_nonce', '', true);

                IF v_purged > 0 THEN
                    INSERT INTO activity_log (actor_account_id, action, entity_type, entity_id, message)
                    VALUES (
                        p_purged_by,
                        'PURGE',
                        v_tbl,
                        p_target_id,
                        format('Controlled purge: Đã xóa %s bản ghi từ %s (retention: %s).', v_purged, v_tbl, p_retention)
                    );
                END IF;

                table_name := v_tbl;
                eligible_count := v_eligible;
                purged_count := v_purged;
                IF v_purged = v_eligible THEN
                    status := 'PURGED';
                ELSIF v_purged > 0 THEN
                    status := 'PARTIALLY_PURGED';
                ELSE
                    status := 'SKIPPED';
                END IF;

                IF v_skipped > 0 THEN
                    details := format('Successfully purged %s rows, skipped %s rows referenced by foreign keys.', v_purged, v_skipped);
                ELSE
                    details := format('Successfully purged %s rows.', v_purged);
                END IF;
                RETURN NEXT;
            ELSE
                table_name := v_tbl;
                eligible_count := 0;
                purged_count := 0;
                status := 'SKIPPED';
                details := 'No eligible trash records to purge.';
                RETURN NEXT;
            END IF;
        END IF;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION fn_guard_soft_delete_and_restore()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_count BIGINT;
    v_parent_deleted TIMESTAMPTZ;
BEGIN
    IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
        IF TG_TABLE_NAME = 'parking_slot' THEN
            IF OLD.status IN ('OCCUPIED', 'CHARGING') THEN
                RAISE EXCEPTION 'Không thể xóa vị trí đỗ xe đang có phương tiện đỗ (trạng thái OCCUPIED).'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Cannot soft delete an occupied or charging slot (PROP-DEL-05-OCCUPIED, SRS 4.8.5, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM vehicle_entry_exit_log
            WHERE slot_id = OLD.id AND exit_time IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Không thể xóa vị trí đỗ xe đang có phương tiện đỗ (trạng thái OCCUPIED).'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Cannot soft delete a slot with an open parking session (PROP-DEL-05-OCCUPIED, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM ticket
            WHERE slot_id = OLD.id
              AND deleted_at IS NULL
              AND status IN ('ACTIVE', 'RENEWING')
              AND effective_to > CURRENT_TIMESTAMP;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Vị trí đỗ xe đang có phương tiện đăng ký vé, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'PROP-4.8.5-P02 (SRS 4.8.5 TH1, MSG-4.5.2-M02, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM slot_reservation
            WHERE slot_id = OLD.id
              AND deleted_at IS NULL
              AND status = 'ACTIVE'
              AND reserved_until > CURRENT_TIMESTAMP;
            IF v_count > 0 OR OLD.status = 'RESERVED' THEN
                RAISE EXCEPTION 'Vị trí đỗ xe đang được đặt trước còn hiệu lực, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Cannot soft delete a slot with an active advance reservation (PROP-DEL-05-RESERVED, DEL-05, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'customer' THEN
            SELECT count(*) INTO v_count
            FROM vehicle_entry_exit_log l
            JOIN vehicle v ON v.id = l.vehicle_id
            WHERE v.customer_id = OLD.id AND l.exit_time IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Khách hàng đang có phương tiện trong bãi, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'PROP-4.4.5-P02 (DEL-02, OQ-15, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM ticket
            WHERE customer_id = OLD.id
              AND deleted_at IS NULL
              AND status IN ('ACTIVE', 'RENEWING')
              AND effective_to > CURRENT_TIMESTAMP;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Khách hàng đang có vé xe còn hiệu lực, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'PROP-4.4.5-P03 (DEL-02, OQ-15, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM vehicle
            WHERE customer_id = OLD.id AND deleted_at IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Khách hàng đang có phương tiện hoạt động trong hệ thống, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Customer still has active registered vehicles (PROP-DEL-02-ACTIVE-VEH, DEL-02, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'vehicle' THEN
            SELECT count(*) INTO v_count
            FROM vehicle_entry_exit_log
            WHERE vehicle_id = OLD.id AND exit_time IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Phương tiện đang đỗ trong bãi xe (có phiên đỗ đang mở), không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Vehicle has uncompleted parking session (PROP-DEL-03-OPEN-SES, DEL-03, OQ-41, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM ticket
            WHERE vehicle_id = OLD.id
              AND deleted_at IS NULL
              AND status IN ('ACTIVE', 'RENEWING')
              AND effective_to > CURRENT_TIMESTAMP;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Phương tiện đang có vé đỗ xe còn hiệu lực, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Vehicle holds active ticket (PROP-DEL-03-ACTIVE-TKT, DEL-03, OQ-41, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM slot_reservation
            WHERE vehicle_id = OLD.id
              AND deleted_at IS NULL
              AND status = 'ACTIVE'
              AND reserved_until > CURRENT_TIMESTAMP;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Phương tiện đang có đặt trước vị trí đỗ xe còn hiệu lực, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Vehicle holds active slot reservation (PROP-DEL-03-ACTIVE-RSV, DEL-03, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'account' THEN
            IF NEW.deleted_by IS NOT NULL AND NEW.deleted_by = OLD.id THEN
                RAISE EXCEPTION 'Tài khoản đang đăng nhập không được phép tự xóa chính mình.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Self-deletion of the authenticated account is prohibited (PROP-DEL-01-SELF, DEL-01, OQ-10).';
            END IF;

            IF OLD.role = 'MANAGER' AND OLD.is_active = TRUE THEN
                SELECT count(*) INTO v_count
                FROM account
                WHERE role = 'MANAGER'
                  AND is_active = TRUE
                  AND deleted_at IS NULL
                  AND id <> OLD.id;
                IF v_count = 0 THEN
                    RAISE EXCEPTION 'Không thể xóa tài khoản Quản lý hoạt động cuối cùng trong hệ thống.'
                        USING ERRCODE = 'check_violation',
                              HINT = 'Last active manager safeguard (PROP-DEL-01-LAST-MGR, DEL-01, OQ-10, TL-25).';
                END IF;
            END IF;

        ELSIF TG_TABLE_NAME = 'employee' THEN
            IF NEW.deleted_by IS NOT NULL AND OLD.account_id IS NOT NULL AND NEW.deleted_by = OLD.account_id THEN
                RAISE EXCEPTION 'Nhân viên đang đăng nhập không được phép tự xóa hồ sơ của chính mình.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Self-deletion of the authenticated employee is prohibited (PROP-DEL-01-SELF-EMP, DEL-01, OQ-10).';
            END IF;

            IF OLD.account_id IS NOT NULL THEN
                SELECT count(*) INTO v_count
                FROM account a
                WHERE a.id = OLD.account_id
                  AND a.role = 'MANAGER'
                  AND a.is_active = TRUE
                  AND a.deleted_at IS NULL;
                IF v_count > 0 THEN
                    SELECT count(*) INTO v_count
                    FROM account
                    WHERE role = 'MANAGER'
                      AND is_active = TRUE
                      AND deleted_at IS NULL
                      AND id <> OLD.account_id;
                    IF v_count = 0 THEN
                        RAISE EXCEPTION 'Không thể xóa nhân viên gắn với tài khoản Quản lý hoạt động cuối cùng.'
                            USING ERRCODE = 'check_violation',
                                  HINT = 'Last active manager safeguard (PROP-DEL-01-LAST-MGR-EMP, DEL-01, OQ-10, TL-25).';
                    END IF;
                END IF;
            END IF;

        ELSIF TG_TABLE_NAME = 'parking_lot' THEN
            SELECT count(*) INTO v_count
            FROM parking_floor
            WHERE lot_id = OLD.id AND deleted_at IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Bãi đỗ xe còn tầng đang hoạt động, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Active child parking floors exist (PROP-DEL-06-LOT, DEL-06, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'parking_floor' THEN
            SELECT count(*) INTO v_count
            FROM parking_zone
            WHERE floor_id = OLD.id AND deleted_at IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Tầng bãi xe còn khu vực (zone) đang hoạt động, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Active child parking zones exist (PROP-DEL-06-FLOOR, DEL-06, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'parking_zone' THEN
            SELECT count(*) INTO v_count
            FROM parking_slot
            WHERE zone_id = OLD.id AND deleted_at IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Khu vực đỗ xe còn vị trí (slot) đang hoạt động, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Active child parking slots exist (PROP-DEL-06-ZONE, DEL-06, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'ticket_type' THEN
            SELECT count(*) INTO v_count
            FROM ticket
            WHERE ticket_type_id = OLD.id
              AND deleted_at IS NULL
              AND status IN ('ACTIVE', 'RENEWING')
              AND effective_to > CURRENT_TIMESTAMP;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Loại vé đang được sử dụng bởi các vé còn hiệu lực, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Active tickets bound to this ticket_type (PROP-DEL-06-TICKET-TYPE, DEL-06, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'position' THEN
            SELECT count(*) INTO v_count
            FROM employee
            WHERE position_id = OLD.id AND deleted_at IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Chức vụ đang được phân công cho nhân viên đang hoạt động, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Active employees assigned to this position (PROP-DEL-06-POSITION, DEL-06, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'vehicle_type' THEN
            SELECT count(*) INTO v_count
            FROM vehicle
            WHERE vehicle_type_id = OLD.id AND deleted_at IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Loại xe đang được liên kết với phương tiện đang hoạt động, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Active vehicles using this vehicle_type (PROP-DEL-06-VEHICLE-TYPE, DEL-06, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'parking_gate' THEN
            SELECT count(*) INTO v_count
            FROM vehicle_entry_exit_log
            WHERE (entry_gate_id = OLD.id OR exit_gate_id = OLD.id)
              AND exit_time IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Cổng kiểm soát đang xử lý phiên đỗ xe chưa hoàn thành, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Gate has active open sessions (PROP-DEL-06-GATE, DEL-06, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'ticket' THEN
            IF OLD.effective_to > CURRENT_TIMESTAMP AND OLD.status IN ('ACTIVE', 'RENEWING') THEN
                RAISE EXCEPTION 'Vé chưa hết hạn, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'PROP-4.6.4-P01 (SRS 4.6.4 TH1, DEL-04, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM ticket_renewal
            WHERE ticket_id = OLD.id;
            IF OLD.status = 'RENEWED' OR v_count > 0 THEN
                RAISE EXCEPTION 'Vé đã được gia hạn, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'PROP-4.6.4-P02 (SRS 4.6.4 TH1, OQ-18, DEL-04, TL-25).';
            END IF;

            SELECT count(*) INTO v_count
            FROM vehicle_entry_exit_log
            WHERE (ticket_id = OLD.id OR vehicle_id = OLD.vehicle_id)
              AND exit_time IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Phương tiện liên kết với vé đang đỗ trong bãi xe, không được phép xóa vé.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Vehicle is inside lot (PROP-DEL-04-OPEN-SES, DEL-04, OQ-42, TL-25).';
            END IF;

        ELSIF TG_TABLE_NAME = 'payment' THEN
            IF OLD.status IN ('PAID', 'REFUNDED') THEN
                RAISE EXCEPTION 'Không thể xóa chứng từ thanh toán đã hoàn thành hoặc đã hoàn tiền (trạng thái PAID/REFUNDED).'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Cannot soft delete payment with status PAID or REFUNDED (PROP-DEL-PAYMENT-SETTLED, TL-39).';
            END IF;

        ELSIF TG_TABLE_NAME = 'wallet' THEN
            IF OLD.balance > 0 THEN
                RAISE EXCEPTION 'Ví khách hàng còn số dư lớn hơn 0, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Wallet with positive balance cannot be soft-deleted (PROP-WALLET-DELETE-NONZERO, ADR-0012).';
            END IF;
        END IF;

        RETURN NEW;

    ELSIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
        NEW.deleted_by := NULL;

        IF TG_TABLE_NAME = 'vehicle' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM customer WHERE id = NEW.customer_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục phương tiện khi khách hàng sở hữu đang bị xóa hoặc không hoạt động.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent customer is deleted (TL-26).';
            END IF;

            SELECT deleted_at INTO v_parent_deleted
            FROM vehicle_type WHERE id = NEW.vehicle_type_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục phương tiện khi loại xe liên kết đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent vehicle_type is deleted (TL-26).';
            END IF;

            IF NEW.ticket_type_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM ticket_type WHERE id = NEW.ticket_type_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục phương tiện khi loại vé liên kết đang bị xóa.'
                        USING ERRCODE = 'check_violation',
                              HINT = 'Parent ticket_type is deleted (TL-26).';
                END IF;
            END IF;

        ELSIF TG_TABLE_NAME = 'parking_slot' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_zone WHERE id = NEW.zone_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục vị trí đỗ khi khu vực đỗ (zone) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent zone is deleted (TL-26).';
            END IF;

        ELSIF TG_TABLE_NAME = 'parking_zone' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_floor WHERE id = NEW.floor_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục khu vực đỗ khi tầng đỗ (floor) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent floor is deleted (TL-26).';
            END IF;

        ELSIF TG_TABLE_NAME = 'parking_floor' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_lot WHERE id = NEW.lot_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục tầng đỗ khi bãi xe (lot) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent lot is deleted (TL-26).';
            END IF;

        ELSIF TG_TABLE_NAME = 'parking_gate' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_lot WHERE id = NEW.lot_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục cổng kiểm soát khi bãi xe (lot) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent lot is deleted (TL-26).';
            END IF;

        ELSIF TG_TABLE_NAME = 'employee' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM position WHERE id = NEW.position_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục nhân viên khi chức vụ tương ứng đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Assigned position is deleted (TL-26).';
            END IF;

            IF NEW.account_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM account WHERE id = NEW.account_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục nhân viên khi tài khoản đăng nhập liên kết đang bị xóa.'
                        USING ERRCODE = 'check_violation',
                              HINT = 'Linked account is deleted (TL-26).';
                END IF;
            END IF;

        ELSIF TG_TABLE_NAME = 'customer' THEN
            IF NEW.account_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM account WHERE id = NEW.account_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục khách hàng khi tài khoản đăng nhập liên kết đang bị xóa.'
                        USING ERRCODE = 'check_violation',
                              HINT = 'Linked account is deleted (TL-26).';
                END IF;
            END IF;

        ELSIF TG_TABLE_NAME = 'slot_reservation' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_slot WHERE id = NEW.slot_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục đặt chỗ khi vị trí đỗ (slot) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Reserved slot is deleted (TL-26).';
            END IF;

            IF NEW.customer_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM customer WHERE id = NEW.customer_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục đặt chỗ khi khách hàng liên kết đang bị xóa.'
                        USING ERRCODE = 'check_violation',
                              HINT = 'Linked customer is deleted (TL-26).';
                END IF;
            END IF;

            IF NEW.vehicle_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM vehicle WHERE id = NEW.vehicle_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục đặt chỗ khi phương tiện liên kết đang bị xóa.'
                        USING ERRCODE = 'check_violation',
                              HINT = 'Linked vehicle is deleted (TL-26).';
                END IF;
            END IF;

        ELSIF TG_TABLE_NAME = 'ticket' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM customer WHERE id = NEW.customer_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục vé khi khách hàng liên kết đang bị xóa.'
                    USING ERRCODE = 'check_violation';
            END IF;

            SELECT deleted_at INTO v_parent_deleted
            FROM vehicle WHERE id = NEW.vehicle_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục vé khi phương tiện liên kết đang bị xóa.'
                    USING ERRCODE = 'check_violation';
            END IF;

            SELECT deleted_at INTO v_parent_deleted
            FROM parking_slot WHERE id = NEW.slot_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục vé khi vị trí đỗ liên kết đang bị xóa.'
                    USING ERRCODE = 'check_violation';
            END IF;

            SELECT deleted_at INTO v_parent_deleted
            FROM ticket_type WHERE id = NEW.ticket_type_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục vé khi loại vé liên kết đang bị xóa.'
                    USING ERRCODE = 'check_violation';
            END IF;

        ELSIF TG_TABLE_NAME = 'payment' THEN
            IF NEW.ticket_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM ticket WHERE id = NEW.ticket_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục thanh toán khi vé liên kết đang bị xóa.'
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;

        ELSIF TG_TABLE_NAME = 'news' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM employee WHERE id = NEW.author_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục bài viết khi nhân viên tác giả đang bị xóa.'
                    USING ERRCODE = 'check_violation';
            END IF;

        ELSIF TG_TABLE_NAME = 'notification' THEN
            IF NEW.recipient_account_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM account WHERE id = NEW.recipient_account_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục thông báo khi tài khoản người nhận đang bị xóa.'
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;

        ELSIF TG_TABLE_NAME = 'wallet' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM customer WHERE id = NEW.customer_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục ví khi khách hàng sở hữu đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Owning customer is deleted (ADR-0012).';
            END IF;
        END IF;

        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION fn_block_wallet_transaction_mutations() FROM PUBLIC;
REVOKE ALL ON FUNCTION fn_controlled_purge(VARCHAR, INTERVAL, BOOLEAN, BIGINT, BIGINT) FROM PUBLIC;
REVOKE ALL ON FUNCTION fn_guard_soft_delete_and_restore() FROM PUBLIC;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_block_wallet_transaction_mutations'
          AND tgrelid = 'public.wallet_transaction'::regclass
    ) THEN
        CREATE TRIGGER trg_block_wallet_transaction_mutations
            BEFORE UPDATE OR DELETE ON wallet_transaction
            FOR EACH ROW EXECUTE FUNCTION fn_block_wallet_transaction_mutations();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_wallet_row_version'
          AND tgrelid = 'public.wallet'::regclass
    ) THEN
        CREATE TRIGGER trg_wallet_row_version
            BEFORE UPDATE ON wallet
            FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_guard_wallet_immutable'
          AND tgrelid = 'public.wallet'::regclass
    ) THEN
        CREATE TRIGGER trg_guard_wallet_immutable
            BEFORE DELETE ON wallet
            FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_guard_soft_delete_and_restore_wallet'
          AND tgrelid = 'public.wallet'::regclass
    ) THEN
        CREATE TRIGGER trg_guard_soft_delete_and_restore_wallet
            BEFORE UPDATE OF deleted_at ON wallet
            FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_audit_soft_delete_and_restore_wallet'
          AND tgrelid = 'public.wallet'::regclass
    ) THEN
        CREATE TRIGGER trg_audit_soft_delete_and_restore_wallet
            AFTER UPDATE OF deleted_at ON wallet
            FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();
    END IF;
END $$;

-- 5. Idempotent backfill: ensure every active customer has an active wallet
INSERT INTO wallet (customer_id, balance, currency, status)
SELECT c.id, 0.00, 'VND', 'ACTIVE'
FROM customer c
WHERE c.deleted_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM wallet w
      WHERE w.customer_id = c.id
        AND w.deleted_at IS NULL
  )
ON CONFLICT (customer_id) WHERE deleted_at IS NULL DO NOTHING;

COMMIT;
