-- =============================================================================
-- FILE: db/upgrades/0013-wallet-kind-vnpay.sql
-- TARGET ENGINE: PostgreSQL 18.6
-- DESCRIPTION:
--   Idempotent upgrade script for Round 94 WP1 (Decision B / D1).
--   Extends wallet_transaction.kind CHECK constraint (ck_wallet_tx_kind_enum)
--   to allow 'TOPUP_VNPAY' without mutating append-only ledger rows.
--   Safe to execute multiple times against an existing Schema v2 + 0012 database.
-- USAGE:
--   docker compose exec -T db psql -U parking_user -d parking_db -v ON_ERROR_STOP=1 < db/upgrades/0013-wallet-kind-vnpay.sql
-- =============================================================================

BEGIN;

SET client_encoding = 'UTF8';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = 'public.wallet_transaction'::regclass
          AND c.conname = 'ck_wallet_tx_kind_enum'
          AND pg_get_constraintdef(c.oid) NOT LIKE '%TOPUP_VNPAY%'
    ) THEN
        ALTER TABLE wallet_transaction DROP CONSTRAINT ck_wallet_tx_kind_enum;
        ALTER TABLE wallet_transaction ADD CONSTRAINT ck_wallet_tx_kind_enum
            CHECK (
                kind IN (
                    'TOPUP_CASH',
                    'TOPUP_VIETQR',
                    'TOPUP_VNPAY',
                    'TICKET_PURCHASE',
                    'TICKET_RENEWAL',
                    'PARKING_FEE',
                    'REFUND',
                    'ADJUSTMENT'
                )
            );
    ELSIF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        WHERE c.conrelid = 'public.wallet_transaction'::regclass
          AND c.conname = 'ck_wallet_tx_kind_enum'
    ) THEN
        ALTER TABLE wallet_transaction ADD CONSTRAINT ck_wallet_tx_kind_enum
            CHECK (
                kind IN (
                    'TOPUP_CASH',
                    'TOPUP_VIETQR',
                    'TOPUP_VNPAY',
                    'TICKET_PURCHASE',
                    'TICKET_RENEWAL',
                    'PARKING_FEE',
                    'REFUND',
                    'ADJUSTMENT'
                )
            );
    END IF;
END $$;

COMMENT ON COLUMN wallet_transaction.kind IS 'Business classification: TOPUP_CASH, TOPUP_VIETQR, TOPUP_VNPAY, TICKET_PURCHASE, TICKET_RENEWAL, PARKING_FEE, REFUND, or ADJUSTMENT.';

COMMIT;
