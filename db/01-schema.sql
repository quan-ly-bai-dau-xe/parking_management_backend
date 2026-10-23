-- =============================================================================
-- FILE: db/01-schema.sql
-- PROJECT: Car Parking Lot Management System Backend (parking_management_backend)
-- TARGET ENGINE: PostgreSQL 18.6
-- DESCRIPTION:
--   Enterprise-grade relational database schema (Schema v2 — Frontend-First).
--   Primary source: Frontend export (`Parking Project`, 11 PNG screens) and
--   Team Lead Decisions TL-01 through TL-41.
--   Secondary source: SRS v4.1 (`Quan ly bai dau xe oto_SRS_v4.1.docx`) where
--   the Frontend is silent.
--   Strictly adheres to ADR-0003 (Soft Delete & ON DELETE RESTRICT), ADR-0004
--   (OWASP Persistent Login Token), and Rule 05 (PostgreSQL Data Modeling).
--   NOTE: Pure creation script. Zero destructive statements are permitted.
-- =============================================================================

BEGIN;

SET client_encoding = 'UTF8';

-- Required for temporal exclusion constraints combining BIGINT with TSTZRANGE (TL-04, TL-10, TL-15)
CREATE EXTENSION btree_gist;

-- Required for partial GIN trigram indexes for fast substring search (TL-41, F6)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =============================================================================
-- SECTION 0: CANONICAL NORMALIZATION FUNCTIONS (TL-05, TL-08, TL-15, OQ-75)
-- =============================================================================

CREATE FUNCTION fn_normalize_license_plate(p_input TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE STRICT PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
    SELECT UPPER(REGEXP_REPLACE(p_input, '[^A-Za-z0-9]', '', 'g'));
$$;

COMMENT ON FUNCTION fn_normalize_license_plate(TEXT) IS 'Normalizes vehicle license plates by stripping non-alphanumeric separators (dots, hyphens, spaces) and converting to uppercase for canonical uniqueness and barrier matching (TL-05, TL-08, TL-15, OQ-75).';

-- =============================================================================
-- SECTION 1: AUTHENTICATION & ACCESS CONTROL MODULE (TL-01, TL-15, SRS 4.1)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1.1. Table: account
-- Source: Frontend `login-container.png` ("Email hoặc Số điện thoại", "Mật khẩu",
--         "Ghi nhớ đăng nhập", "Quên mật khẩu?", "Đăng ký ngay"), TL-01, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE account (
    id BIGSERIAL,
    email VARCHAR(100) NULL,
    phone VARCHAR(15) NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'EMPLOYEE',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_account PRIMARY KEY (id),
    CONSTRAINT fk_account_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_account_login_identifier_present CHECK (num_nonnulls(email, phone) >= 1),
    CONSTRAINT ck_account_email_format CHECK (
        email IS NULL OR (btrim(email) <> '' AND email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
    ),
    CONSTRAINT ck_account_phone_digits CHECK (
        phone IS NULL OR phone ~ '^[0-9]{9,15}$'
    ),
    CONSTRAINT ck_account_password_nonempty CHECK (btrim(password_hash) <> ''),
    CONSTRAINT ck_account_role_enum CHECK (role IN ('MANAGER', 'EMPLOYEE', 'CUSTOMER')),
    CONSTRAINT ck_account_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_account_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_account_email_active
    ON account (lower(email))
    WHERE deleted_at IS NULL AND email IS NOT NULL;

CREATE UNIQUE INDEX uq_account_phone_active
    ON account (phone)
    WHERE deleted_at IS NULL AND phone IS NOT NULL;

CREATE INDEX idx_account_role_active
    ON account (role)
    WHERE deleted_at IS NULL AND is_active = TRUE;

COMMENT ON TABLE account IS 'System authentication accounts using email or phone login identifiers and supporting self-registered customers (login-container.png, TL-01, TL-15).';
COMMENT ON COLUMN account.id IS 'Primary key identifier of the system account.';
COMMENT ON COLUMN account.email IS 'Login email address for authentication ("Email hoặc Số điện thoại" on login-container.png, TL-01); case-insensitively unique via lower(email) among active accounts when present (TL-21, OQ-84).';
COMMENT ON COLUMN account.phone IS 'Login phone number (9-15 digits) for authentication ("Email hoặc Số điện thoại" on login-container.png, TL-01); unique among active accounts when present.';
COMMENT ON COLUMN account.password_hash IS 'Cryptographic password hash (Argon2id/PBKDF2) for "Mật khẩu" on login-container.png (TL-01, ADR-0004).';
COMMENT ON COLUMN account.role IS 'Authorization role: MANAGER (Quản lý), EMPLOYEE (Nhân viên), or CUSTOMER (Khách hàng self-registration per TL-01, OQ-03, OQ-55).';
COMMENT ON COLUMN account.is_active IS 'Account activation status flag ("Khoá tài khoản" on Quản lý nhân viên, TL-01, TL-11).';
COMMENT ON COLUMN account.last_login_at IS 'Timestamp of the most recent successful authentication.';
COMMENT ON COLUMN account.row_version IS 'Optimistic concurrency control version counter incremented automatically on update (TL-15, OQ-64).';
COMMENT ON COLUMN account.created_at IS 'Record creation timestamp (TIMESTAMPTZ).';
COMMENT ON COLUMN account.updated_at IS 'Record last modification timestamp (TIMESTAMPTZ).';
COMMENT ON COLUMN account.deleted_at IS 'Soft deletion timestamp; NULL indicates active record (ADR-0003, TL-15).';
COMMENT ON COLUMN account.deleted_by IS 'Foreign key referencing the account that performed soft deletion (ADR-0003, TL-15).';

-- -----------------------------------------------------------------------------
-- 1.2. Table: persistent_login_token
-- Source: Frontend `login-container.png` ("Ghi nhớ đăng nhập"), TL-01, TL-15, ADR-0004
-- -----------------------------------------------------------------------------
CREATE TABLE persistent_login_token (
    id BIGSERIAL,
    series VARCHAR(64) NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    account_id BIGINT NOT NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_persistent_login_token PRIMARY KEY (id),
    CONSTRAINT uq_persistent_login_token_series UNIQUE (series),
    CONSTRAINT fk_plt_account FOREIGN KEY (account_id)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_plt_series_nonempty CHECK (btrim(series) <> ''),
    CONSTRAINT ck_plt_token_nonempty CHECK (btrim(token_hash) <> ''),
    CONSTRAINT ck_plt_expiry_order CHECK (expires_at > created_at)
);

CREATE INDEX idx_plt_account_id ON persistent_login_token (account_id);
CREATE INDEX idx_plt_expires_at ON persistent_login_token (expires_at);

COMMENT ON TABLE persistent_login_token IS 'OWASP Series/Token persistent login store for "Ghi nhớ đăng nhập" (login-container.png, TL-01, TL-15, ADR-0004, OQ-01).';
COMMENT ON COLUMN persistent_login_token.id IS 'Primary key identifier of the persistent login token.';
COMMENT ON COLUMN persistent_login_token.series IS 'Unique token series identifier for theft detection across rotations.';
COMMENT ON COLUMN persistent_login_token.token_hash IS 'SHA-256 cryptographic hash of the rotating single-use remember-me token.';
COMMENT ON COLUMN persistent_login_token.account_id IS 'Foreign key referencing the authenticated account.';
COMMENT ON COLUMN persistent_login_token.ip_address IS 'Client IPv4/IPv6 address recorded at session issuance.';
COMMENT ON COLUMN persistent_login_token.user_agent IS 'Client browser User-Agent string recorded at session issuance.';
COMMENT ON COLUMN persistent_login_token.created_at IS 'Timestamp when the persistent session was initially established.';
COMMENT ON COLUMN persistent_login_token.last_used_at IS 'Timestamp when the token was most recently rotated.';
COMMENT ON COLUMN persistent_login_token.expires_at IS 'Expiration timestamp after which the persistent token is invalid.';

-- -----------------------------------------------------------------------------
-- 1.3. Table: password_reset_token
-- Source: Frontend `login-container.png` ("Quên mật khẩu?") & `Quản lý nhân viên` ("Đặt lại mật khẩu"), TL-01, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE password_reset_token (
    id BIGSERIAL,
    account_id BIGINT NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    requested_ip VARCHAR(45) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_password_reset_token PRIMARY KEY (id),
    CONSTRAINT uq_password_reset_token_hash UNIQUE (token_hash),
    CONSTRAINT fk_prt_account FOREIGN KEY (account_id)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_prt_token_nonempty CHECK (btrim(token_hash) <> ''),
    CONSTRAINT ck_prt_expiry_order CHECK (expires_at > created_at)
);

CREATE INDEX idx_prt_account_id ON password_reset_token (account_id);

COMMENT ON TABLE password_reset_token IS 'Single-use cryptographic token store for "Quên mật khẩu?" and "Đặt lại mật khẩu" (login-container.png, TL-01, TL-15, SCO-05).';
COMMENT ON COLUMN password_reset_token.id IS 'Primary key identifier of the password reset token.';
COMMENT ON COLUMN password_reset_token.account_id IS 'Foreign key referencing the account requesting password recovery.';
COMMENT ON COLUMN password_reset_token.token_hash IS 'Cryptographic hash of the one-time reset token.';
COMMENT ON COLUMN password_reset_token.expires_at IS 'Token expiration timestamp.';
COMMENT ON COLUMN password_reset_token.used_at IS 'Timestamp when the token was consumed; NULL if unused.';
COMMENT ON COLUMN password_reset_token.requested_ip IS 'Requester IPv4/IPv6 address for security auditing.';
COMMENT ON COLUMN password_reset_token.created_at IS 'Token generation timestamp.';

-- =============================================================================
-- SECTION 2: HUMAN RESOURCES & ADMINISTRATIVE GEOGRAPHY (TL-11, TL-15, SRS 4.3)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 2.1. Table: position
-- Source: Frontend `Quản lý nhân viên - Smart mobility.png` ("Chức vụ: 4" — Quản lý, Nhân viên vận hành, Nhân viên thu ngân, Kỹ thuật viên), TL-11
-- -----------------------------------------------------------------------------
CREATE TABLE position (
    id BIGSERIAL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(255) NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_position PRIMARY KEY (id),
    CONSTRAINT fk_position_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_position_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_position_name_nonempty CHECK (btrim(name) <> ''),
    CONSTRAINT ck_position_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_position_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_position_code_active
    ON position (code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_position_name_active
    ON position (name)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE position IS 'Employee job position lookup catalog ("Chức vụ" on Quản lý nhân viên - Smart mobility.png: Quản lý, Nhân viên vận hành, Nhân viên thu ngân, Kỹ thuật viên; TL-11).';
COMMENT ON COLUMN position.id IS 'Primary key identifier of the job position.';
COMMENT ON COLUMN position.code IS 'Unique business code for the position (e.g., QL, NVVH, NVTN, KTV).';
COMMENT ON COLUMN position.name IS 'Display name of the job position in Vietnamese (TL-11).';
COMMENT ON COLUMN position.description IS 'Optional description of position duties and access scope.';
COMMENT ON COLUMN position.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN position.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN position.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN position.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN position.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 2.2. Tables: administrative_province, administrative_district, administrative_ward
-- Source: Frontend `Quản lý nhân viên — Smart Mobility.png` ("Khu vực"), SRS 4.3.2 & 4.4.3, TL-11, TL-15, OQ-50, OQ-62
-- -----------------------------------------------------------------------------
CREATE TABLE administrative_province (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_administrative_province PRIMARY KEY (id),
    CONSTRAINT uq_admin_province_code UNIQUE (code),
    CONSTRAINT ck_admin_province_name_nonempty CHECK (btrim(name) <> '')
);

CREATE INDEX idx_admin_province_name ON administrative_province (name);

COMMENT ON TABLE administrative_province IS 'Provincial-level administrative division lookup ("Khu vực" on Quản lý nhân viên, SRS 4.3.2, 4.4.3, TL-11, TL-15, OQ-50, OQ-62).';
COMMENT ON COLUMN administrative_province.id IS 'Primary key identifier of the province/municipality.';
COMMENT ON COLUMN administrative_province.code IS 'Unique administrative code of the province.';
COMMENT ON COLUMN administrative_province.name IS 'Official Vietnamese name of the province or centrally-run city.';
COMMENT ON COLUMN administrative_province.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN administrative_province.updated_at IS 'Record modification timestamp.';

CREATE TABLE administrative_district (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    province_id BIGINT NOT NULL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_administrative_district PRIMARY KEY (id),
    CONSTRAINT uq_admin_district_code UNIQUE (code),
    CONSTRAINT uq_admin_district_id_province UNIQUE (id, province_id),
    CONSTRAINT fk_admin_district_province FOREIGN KEY (province_id)
        REFERENCES administrative_province (id) ON DELETE RESTRICT,
    CONSTRAINT ck_admin_district_name_nonempty CHECK (btrim(name) <> '')
);

CREATE INDEX idx_admin_district_province ON administrative_district (province_id);

COMMENT ON TABLE administrative_district IS 'District-level administrative lookup ("Khu vực" on Quản lý nhân viên, SRS 4.3.2, TL-11, TL-15, OQ-50, OQ-62).';
COMMENT ON COLUMN administrative_district.id IS 'Primary key identifier of the district.';
COMMENT ON COLUMN administrative_district.province_id IS 'Foreign key referencing parent province (ON DELETE RESTRICT).';
COMMENT ON COLUMN administrative_district.code IS 'Unique administrative district code.';
COMMENT ON COLUMN administrative_district.name IS 'Vietnamese name of the district/county/town.';
COMMENT ON COLUMN administrative_district.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN administrative_district.updated_at IS 'Record modification timestamp.';

CREATE TABLE administrative_ward (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    district_id BIGINT NOT NULL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_administrative_ward PRIMARY KEY (id),
    CONSTRAINT uq_admin_ward_code UNIQUE (code),
    CONSTRAINT uq_admin_ward_id_district UNIQUE (id, district_id),
    CONSTRAINT fk_admin_ward_district FOREIGN KEY (district_id)
        REFERENCES administrative_district (id) ON DELETE RESTRICT,
    CONSTRAINT ck_admin_ward_name_nonempty CHECK (btrim(name) <> '')
);

CREATE INDEX idx_admin_ward_district ON administrative_ward (district_id);

COMMENT ON TABLE administrative_ward IS 'Commune/ward-level administrative lookup (SRS 4.3.2, TL-11, TL-15, OQ-50, OQ-62).';
COMMENT ON COLUMN administrative_ward.id IS 'Primary key identifier of the ward/commune.';
COMMENT ON COLUMN administrative_ward.district_id IS 'Foreign key referencing parent district (ON DELETE RESTRICT).';
COMMENT ON COLUMN administrative_ward.code IS 'Unique administrative ward code.';
COMMENT ON COLUMN administrative_ward.name IS 'Vietnamese name of the ward/commune/township.';
COMMENT ON COLUMN administrative_ward.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN administrative_ward.updated_at IS 'Record modification timestamp.';

-- -----------------------------------------------------------------------------
-- 2.3. Table: employee
-- Source: Frontend `Quản lý nhân viên - Smart mobility.png` (Mã NV NV001..NV008 and NV0005,
--         Trạng thái Đang hoạt động / Ngừng hoạt động, Chức vụ, Khu vực), TL-11, TL-15, TL-18
-- -----------------------------------------------------------------------------
CREATE TABLE employee (
    id BIGSERIAL,
    code VARCHAR(10) NOT NULL,
    full_name VARCHAR(45) NOT NULL,
    date_of_birth DATE NULL,
    gender VARCHAR(10) NULL,
    identity_card_number VARCHAR(20) NULL,
    phone VARCHAR(15) NOT NULL,
    email VARCHAR(100) NOT NULL,
    address VARCHAR(100) NULL,
    province_id BIGINT NULL,
    district_id BIGINT NULL,
    ward_id BIGINT NULL,
    position_id BIGINT NOT NULL,
    account_id BIGINT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_employee PRIMARY KEY (id),
    CONSTRAINT fk_employee_district_hierarchy FOREIGN KEY (district_id, province_id)
        REFERENCES administrative_district (id, province_id) ON DELETE RESTRICT,
    CONSTRAINT fk_employee_ward_hierarchy FOREIGN KEY (ward_id, district_id)
        REFERENCES administrative_ward (id, district_id) ON DELETE RESTRICT,
    CONSTRAINT fk_employee_position FOREIGN KEY (position_id)
        REFERENCES position (id) ON DELETE RESTRICT,
    CONSTRAINT fk_employee_account FOREIGN KEY (account_id)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT fk_employee_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_employee_code_format CHECK (code ~ '^NV[0-9]{3,4}$'),
    CONSTRAINT ck_employee_full_name_nonempty CHECK (btrim(full_name) <> ''),
    CONSTRAINT ck_employee_dob_past CHECK (date_of_birth IS NULL OR date_of_birth < CURRENT_DATE),
    CONSTRAINT ck_employee_gender CHECK (gender IS NULL OR gender IN ('Nam', 'Nữ')),
    CONSTRAINT ck_employee_idcard_digits CHECK (identity_card_number IS NULL OR identity_card_number ~ '^[0-9]{9,20}$'),
    CONSTRAINT ck_employee_phone_digits CHECK (phone ~ '^[0-9]{9,15}$'),
    CONSTRAINT ck_employee_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT ck_employee_address_nonempty CHECK (address IS NULL OR btrim(address) <> ''),
    CONSTRAINT ck_employee_ward_requires_district CHECK (
        (ward_id IS NULL OR district_id IS NOT NULL) AND
        (district_id IS NULL OR province_id IS NOT NULL)
    ),
    CONSTRAINT ck_employee_status_enum CHECK (status IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT ck_employee_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_employee_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_employee_code_active
    ON employee (code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_employee_idcard_active
    ON employee (identity_card_number)
    WHERE deleted_at IS NULL AND identity_card_number IS NOT NULL;

CREATE UNIQUE INDEX uq_employee_email_active
    ON employee (lower(email))
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_employee_phone_active
    ON employee (phone)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_employee_account_active
    ON employee (account_id)
    WHERE deleted_at IS NULL AND account_id IS NOT NULL;

CREATE INDEX idx_employee_position_id ON employee (position_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_employee_status_active ON employee (status) WHERE deleted_at IS NULL;
CREATE INDEX idx_employee_full_name ON employee (full_name) WHERE deleted_at IS NULL;
CREATE INDEX idx_employee_district_province ON employee (district_id, province_id) WHERE deleted_at IS NULL;

COMMENT ON TABLE employee IS 'Employee HR records with code format NV + 3 or 4 digits (NV005 / NV0005), operational status (ACTIVE / INACTIVE), and 3-level address hierarchy (Quản lý nhân viên - Smart mobility.png, TL-11, TL-15, TL-18).';
COMMENT ON COLUMN employee.id IS 'Primary key identifier of the employee.';
COMMENT ON COLUMN employee.code IS 'Employee code matching ^NV[0-9]{3,4}$ (supports both NV001..NV008 and NV0005 on Quản lý nhân viên, TL-11, OQ-48).';
COMMENT ON COLUMN employee.full_name IS 'Full name of the employee ("Họ và tên", max 45 chars, required per TL-18).';
COMMENT ON COLUMN employee.date_of_birth IS 'Optional employee date of birth ("Ngày sinh", must be in the past when provided, TL-18).';
COMMENT ON COLUMN employee.gender IS 'Optional employee gender ("Giới tính": Nam or Nữ when provided, TL-18).';
COMMENT ON COLUMN employee.identity_card_number IS 'Optional national ID / CCCD number ("Số CCCD / CMND", 9-20 digits, unique among active non-null rows, TL-18).';
COMMENT ON COLUMN employee.phone IS 'Employee contact phone number ("Số điện thoại", 9-15 digits, required per TL-18).';
COMMENT ON COLUMN employee.email IS 'Employee work email address ("Email công việc", required per TL-18 and case-insensitively unique via lower(email) among active rows per TL-21, OQ-84).';
COMMENT ON COLUMN employee.address IS 'Optional detailed street address ("Địa chỉ chi tiết", TL-18).';
COMMENT ON COLUMN employee.province_id IS 'Foreign key referencing administrative_province ("Tỉnh / Thành phố", TL-11, OQ-62).';
COMMENT ON COLUMN employee.district_id IS 'Foreign key referencing administrative_district ("Quận / Huyện", TL-11, OQ-62).';
COMMENT ON COLUMN employee.ward_id IS 'Foreign key referencing administrative_ward ("Phường / Xã", TL-11, OQ-62).';
COMMENT ON COLUMN employee.position_id IS 'Foreign key referencing job position ("Chức vụ", TL-11).';
COMMENT ON COLUMN employee.account_id IS 'Optional foreign key referencing system login account (OQ-56, TL-11).';
COMMENT ON COLUMN employee.status IS 'Employment operational status: ACTIVE ("Đang hoạt động") or INACTIVE ("Ngừng hoạt động" / "Tạm nghỉ", TL-11).';
COMMENT ON COLUMN employee.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN employee.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN employee.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN employee.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN employee.deleted_by IS 'Account that performed soft deletion.';

-- =============================================================================
-- SECTION 3: CUSTOMER, BLACKLIST & VEHICLE MANAGEMENT (TL-08, TL-09, TL-15, TL-18)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 3.1. Table: customer
-- Source: Frontend `Khách hàng — Smart Mobility.png` ("Tổng khách hàng", "Đang hoạt động",
--         "Tạm ngừng", "Blacklist/Tạm khoá"), TL-08, TL-15, TL-18
-- -----------------------------------------------------------------------------
CREATE TABLE customer (
    id BIGSERIAL,
    code VARCHAR(10) NOT NULL,
    full_name VARCHAR(45) NOT NULL,
    date_of_birth DATE NULL,
    gender VARCHAR(10) NULL,
    identity_card_number VARCHAR(20) NOT NULL,
    phone VARCHAR(15) NOT NULL,
    email VARCHAR(100) NULL,
    address VARCHAR(100) NULL,
    province_id BIGINT NULL,
    district_id BIGINT NULL,
    ward_id BIGINT NULL,
    account_id BIGINT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    status_reason TEXT NULL,
    is_anonymized BOOLEAN NOT NULL DEFAULT FALSE,
    anonymized_at TIMESTAMPTZ NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_customer PRIMARY KEY (id),
    CONSTRAINT fk_customer_district_hierarchy FOREIGN KEY (district_id, province_id)
        REFERENCES administrative_district (id, province_id) ON DELETE RESTRICT,
    CONSTRAINT fk_customer_ward_hierarchy FOREIGN KEY (ward_id, district_id)
        REFERENCES administrative_ward (id, district_id) ON DELETE RESTRICT,
    CONSTRAINT fk_customer_account FOREIGN KEY (account_id)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT fk_customer_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_customer_code_format CHECK (code ~ '^[A-Za-z0-9-]+$'),
    CONSTRAINT ck_customer_full_name_nonempty CHECK (btrim(full_name) <> ''),
    CONSTRAINT ck_customer_dob_past CHECK (date_of_birth IS NULL OR date_of_birth < CURRENT_DATE),
    CONSTRAINT ck_customer_gender CHECK (gender IS NULL OR gender IN ('Nam', 'Nữ')),
    CONSTRAINT ck_customer_idcard_digits CHECK (identity_card_number ~ '^[0-9]{9,20}$'),
    CONSTRAINT ck_customer_phone_digits CHECK (phone ~ '^[0-9]{9,15}$'),
    CONSTRAINT ck_customer_email_format CHECK (email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT ck_customer_address_nonempty CHECK (address IS NULL OR btrim(address) <> ''),
    CONSTRAINT ck_customer_ward_requires_district CHECK (
        (ward_id IS NULL OR district_id IS NOT NULL) AND
        (district_id IS NULL OR province_id IS NOT NULL)
    ),
    CONSTRAINT ck_customer_status_enum CHECK (status IN ('ACTIVE', 'SUSPENDED', 'BLACKLISTED')),
    CONSTRAINT ck_customer_blacklist_reason CHECK (
        status <> 'BLACKLISTED' OR (status_reason IS NOT NULL AND btrim(status_reason) <> '')
    ),
    CONSTRAINT ck_customer_anonymized_pair CHECK (
        (is_anonymized = FALSE AND anonymized_at IS NULL) OR (is_anonymized = TRUE AND anonymized_at IS NOT NULL)
    ),
    CONSTRAINT ck_customer_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_customer_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_customer_code_active
    ON customer (code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_customer_idcard_active
    ON customer (identity_card_number)
    WHERE deleted_at IS NULL AND is_anonymized = FALSE;

CREATE UNIQUE INDEX uq_customer_email_active
    ON customer (lower(email))
    WHERE deleted_at IS NULL AND is_anonymized = FALSE AND email IS NOT NULL;

CREATE UNIQUE INDEX uq_customer_phone_active
    ON customer (phone)
    WHERE deleted_at IS NULL AND is_anonymized = FALSE;

CREATE UNIQUE INDEX uq_customer_account_active
    ON customer (account_id)
    WHERE deleted_at IS NULL AND account_id IS NOT NULL;

CREATE INDEX idx_customer_full_name ON customer (full_name) WHERE deleted_at IS NULL;
CREATE INDEX idx_customer_status_active ON customer (status) WHERE deleted_at IS NULL;
CREATE INDEX idx_customer_district_province ON customer (district_id, province_id) WHERE deleted_at IS NULL;

-- Trigram GIN indexes for fast frontend substring/ILIKE search (TL-41, F6)
CREATE INDEX idx_customer_full_name_trgm ON customer USING gin (full_name gin_trgm_ops) WHERE deleted_at IS NULL;
CREATE INDEX idx_customer_phone_trgm ON customer USING gin (phone gin_trgm_ops) WHERE deleted_at IS NULL;
CREATE INDEX idx_customer_idcard_trgm ON customer USING gin (identity_card_number gin_trgm_ops) WHERE deleted_at IS NULL;

COMMENT ON TABLE customer IS 'Customer profile table with operational status (ACTIVE, SUSPENDED, BLACKLISTED) and status reason (Khách hàng — Smart Mobility.png, TL-08, TL-15, TL-18).';
COMMENT ON COLUMN customer.id IS 'Primary key identifier of the customer.';
COMMENT ON COLUMN customer.code IS 'Customer code ("Mã KH", e.g., KH0001..KH0004).';
COMMENT ON COLUMN customer.full_name IS 'Full name of the customer ("Họ và tên", required per TL-18).';
COMMENT ON COLUMN customer.date_of_birth IS 'Optional customer date of birth ("Ngày sinh", must be in the past when provided, TL-18).';
COMMENT ON COLUMN customer.gender IS 'Optional customer gender ("Giới tính": Nam or Nữ when provided, TL-18).';
COMMENT ON COLUMN customer.identity_card_number IS 'National ID / CCCD number ("CCCD", 9-20 digits, required per TL-18).';
COMMENT ON COLUMN customer.phone IS 'Customer phone number ("Số điện thoại", required per TL-18).';
COMMENT ON COLUMN customer.email IS 'Optional customer email address ("Email", case-insensitively unique via lower(email) among active non-anonymized non-null rows per TL-18, TL-21, OQ-84).';
COMMENT ON COLUMN customer.address IS 'Optional customer residential address ("Địa chỉ", TL-18).';
COMMENT ON COLUMN customer.province_id IS 'Optional foreign key referencing administrative_province (OQ-62).';
COMMENT ON COLUMN customer.district_id IS 'Optional foreign key referencing administrative_district (OQ-62).';
COMMENT ON COLUMN customer.ward_id IS 'Optional foreign key referencing administrative_ward (OQ-62).';
COMMENT ON COLUMN customer.account_id IS 'Optional foreign key referencing self-registered customer login account (TL-01, TL-18, OQ-55).';
COMMENT ON COLUMN customer.status IS 'Customer status: ACTIVE ("Đang hoạt động"), SUSPENDED ("Tạm ngừng"), or BLACKLISTED ("Blacklist/Tạm khoá", TL-08).';
COMMENT ON COLUMN customer.status_reason IS 'Reason for suspension or blacklisting; required when status is BLACKLISTED (TL-08).';
COMMENT ON COLUMN customer.is_anonymized IS 'Decree 13/2023/ND-CP PII anonymization flag (OQ-12).';
COMMENT ON COLUMN customer.anonymized_at IS 'Timestamp when PII anonymization was executed (OQ-12).';
COMMENT ON COLUMN customer.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN customer.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN customer.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN customer.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN customer.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 3.2. Table: plate_blacklist
-- Source: Frontend `Trang chủ — Smart Mobility.png` ("Biển số 51G-888.88 thuộc Blacklist (Nợ phí)"), TL-08, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE plate_blacklist (
    id BIGSERIAL,
    license_plate VARCHAR(20) NOT NULL,
    license_plate_norm VARCHAR(20) GENERATED ALWAYS AS (fn_normalize_license_plate(license_plate)) STORED,
    reason TEXT NOT NULL,
    unpaid_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    added_by BIGINT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_plate_blacklist PRIMARY KEY (id),
    CONSTRAINT fk_plate_blacklist_added_by FOREIGN KEY (added_by)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT fk_plate_blacklist_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_plate_blacklist_plate_nonempty CHECK (btrim(license_plate) <> ''),
    CONSTRAINT ck_plate_blacklist_plate_format CHECK (license_plate ~ '^[A-Za-z0-9 .\-]+$'),
    CONSTRAINT ck_plate_blacklist_norm_nonempty CHECK (license_plate_norm <> ''),
    CONSTRAINT ck_plate_blacklist_reason_nonempty CHECK (btrim(reason) <> ''),
    CONSTRAINT ck_plate_blacklist_unpaid_nonnegative CHECK (unpaid_amount >= 0),
    CONSTRAINT ck_plate_blacklist_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_plate_blacklist_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_plate_blacklist_norm_active
    ON plate_blacklist (license_plate_norm)
    WHERE deleted_at IS NULL AND is_active = TRUE;

COMMENT ON TABLE plate_blacklist IS 'Blacklisted license plates for visitor/unregistered vehicles with reason and unpaid debt amount ("Biển số 51G-888.88 thuộc Blacklist (Nợ phí)" on Trang chủ, TL-08).';
COMMENT ON COLUMN plate_blacklist.id IS 'Primary key identifier of the plate blacklist entry.';
COMMENT ON COLUMN plate_blacklist.license_plate IS 'Raw license plate string as entered (e.g., 51G-888.88).';
COMMENT ON COLUMN plate_blacklist.license_plate_norm IS 'Canonical normalized license plate computed via fn_normalize_license_plate(license_plate) (TL-08, TL-15, OQ-75).';
COMMENT ON COLUMN plate_blacklist.reason IS 'Mandatory reason for blacklisting the license plate (e.g., Nợ phí).';
COMMENT ON COLUMN plate_blacklist.unpaid_amount IS 'Outstanding unpaid debt amount in VND associated with the blacklisted plate (TL-08).';
COMMENT ON COLUMN plate_blacklist.is_active IS 'Whether the blacklist entry is currently active.';
COMMENT ON COLUMN plate_blacklist.added_by IS 'Optional foreign key referencing the employee who recorded the blacklist entry.';
COMMENT ON COLUMN plate_blacklist.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN plate_blacklist.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN plate_blacklist.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN plate_blacklist.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN plate_blacklist.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 3.3. Table: vehicle_type
-- Source: Frontend `Quản lý xe — Smart Mobility.png` & `Quản lý vé — Smart Mobility.png`
--         ("Ô tô", "Xe điện"), TL-09, TL-15, TL-20
-- -----------------------------------------------------------------------------
CREATE TABLE vehicle_type (
    id BIGSERIAL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(255) NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_vehicle_type PRIMARY KEY (id),
    CONSTRAINT fk_vehicle_type_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_vehicle_type_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_vehicle_type_name_nonempty CHECK (btrim(name) <> ''),
    CONSTRAINT ck_vehicle_type_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_vehicle_type_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_vehicle_type_code_active
    ON vehicle_type (code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_vehicle_type_name_active
    ON vehicle_type (name)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE vehicle_type IS 'Vehicle classification catalog ("Loại xe": Ô tô, Xe điện on Quản lý xe and Quản lý vé; cars only per TL-09, TL-20, OQ-49).';
COMMENT ON COLUMN vehicle_type.id IS 'Primary key identifier of the vehicle type.';
COMMENT ON COLUMN vehicle_type.code IS 'Unique code for the vehicle type (CAR, EV per TL-20).';
COMMENT ON COLUMN vehicle_type.name IS 'Display name of the vehicle category (Ô tô, Xe điện per TL-09, TL-20).';
COMMENT ON COLUMN vehicle_type.description IS 'Detailed description of the vehicle category.';
COMMENT ON COLUMN vehicle_type.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN vehicle_type.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN vehicle_type.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN vehicle_type.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN vehicle_type.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 3.4. Table: ticket_type
-- Source: Frontend `Quản lý vé — Smart Mobility.png` ("Vé ngày" 50.000đ, "Vé tháng" 500.000đ,
--         "Vé quý" 1.200.000đ, "Vé năm" 4.800.000đ [PROPOSAL OQ-79]), TL-10, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE ticket_type (
    id BIGSERIAL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    duration_days INTEGER NOT NULL,
    default_price NUMERIC(12, 2) NOT NULL,
    description VARCHAR(255) NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_ticket_type PRIMARY KEY (id),
    CONSTRAINT fk_ticket_type_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_ticket_type_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_ticket_type_name_nonempty CHECK (btrim(name) <> ''),
    CONSTRAINT ck_ticket_type_duration_positive CHECK (duration_days > 0),
    CONSTRAINT ck_ticket_type_price_nonnegative CHECK (default_price >= 0),
    CONSTRAINT ck_ticket_type_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_ticket_type_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_ticket_type_code_active
    ON ticket_type (code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_ticket_type_name_active
    ON ticket_type (name)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE ticket_type IS 'Ticket tariff catalog ("Loại vé" on Quản lý vé: Vé ngày 50.000đ, Vé tháng 500.000đ, Vé quý 1.200.000đ, Vé năm 4.800.000đ [PROPOSAL OQ-79], TL-10).';
COMMENT ON COLUMN ticket_type.id IS 'Primary key identifier of the ticket type.';
COMMENT ON COLUMN ticket_type.code IS 'Unique code of the ticket type (DAILY, MONTHLY, QUARTERLY, YEARLY).';
COMMENT ON COLUMN ticket_type.name IS 'Display name of the ticket type in Vietnamese (Vé ngày, Vé tháng, Vé quý, Vé năm).';
COMMENT ON COLUMN ticket_type.duration_days IS 'Validity duration in calendar days (1, 30, 90, 365).';
COMMENT ON COLUMN ticket_type.default_price IS 'Default standard tariff price in VND (NUMERIC(12,2)).';
COMMENT ON COLUMN ticket_type.description IS 'Optional tariff description and policy notes.';
COMMENT ON COLUMN ticket_type.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN ticket_type.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN ticket_type.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN ticket_type.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN ticket_type.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 3.5. Table: vehicle
-- Source: Frontend `Quản lý xe — Smart Mobility.png` (Mã xe, Ảnh, Biển số & Thông tin xe,
--         Loại xe, Chủ sở hữu, Vé liên kết, Ghi chú), TL-09, TL-15, OQ-52, OQ-53, OQ-75
-- -----------------------------------------------------------------------------
CREATE TABLE vehicle (
    id BIGSERIAL,
    code VARCHAR(10) NOT NULL,
    license_plate VARCHAR(20) NOT NULL,
    license_plate_norm VARCHAR(20) GENERATED ALWAYS AS (fn_normalize_license_plate(license_plate)) STORED,
    model_name VARCHAR(50) NOT NULL,
    brand VARCHAR(50) NULL,
    color VARCHAR(30) NULL,
    image_url TEXT NULL,
    notes TEXT NULL,
    vehicle_type_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    ticket_type_id BIGINT NULL,
    ticket_expires_at TIMESTAMPTZ NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_vehicle PRIMARY KEY (id),
    CONSTRAINT uq_vehicle_id_customer UNIQUE (id, customer_id),
    CONSTRAINT fk_vehicle_type FOREIGN KEY (vehicle_type_id)
        REFERENCES vehicle_type (id) ON DELETE RESTRICT,
    CONSTRAINT fk_vehicle_customer FOREIGN KEY (customer_id)
        REFERENCES customer (id) ON DELETE RESTRICT,
    CONSTRAINT fk_vehicle_ticket_type FOREIGN KEY (ticket_type_id)
        REFERENCES ticket_type (id) ON DELETE RESTRICT,
    CONSTRAINT fk_vehicle_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_vehicle_code_format CHECK (code ~ '^[A-Za-z0-9-]+$'),
    CONSTRAINT ck_vehicle_license_plate_nonempty CHECK (btrim(license_plate) <> ''),
    CONSTRAINT ck_vehicle_license_plate_format CHECK (license_plate ~ '^[A-Za-z0-9 .\-]+$'),
    CONSTRAINT ck_vehicle_license_plate_norm_nonempty CHECK (license_plate_norm <> ''),
    CONSTRAINT ck_vehicle_model_name_nonempty CHECK (btrim(model_name) <> ''),
    CONSTRAINT ck_vehicle_ticket_pref_pair CHECK (
        (ticket_type_id IS NULL AND ticket_expires_at IS NULL) OR
        (ticket_type_id IS NOT NULL AND ticket_expires_at IS NOT NULL)
    ),
    CONSTRAINT ck_vehicle_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_vehicle_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_vehicle_code_active
    ON vehicle (code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_vehicle_license_plate_active
    ON vehicle (license_plate_norm)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_vehicle_customer_id ON vehicle (customer_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_vehicle_type_id ON vehicle (vehicle_type_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_vehicle_ticket_type_id ON vehicle (ticket_type_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_vehicle_plate_trgm ON vehicle USING gin (license_plate_norm gin_trgm_ops) WHERE deleted_at IS NULL;

COMMENT ON TABLE vehicle IS 'Customer registered vehicles with raw display license_plate, stored generated license_plate_norm, image_url ("Ảnh"), and notes ("Ghi chú" on Quản lý xe — Smart Mobility.png, TL-09, TL-15, OQ-75).';
COMMENT ON COLUMN vehicle.id IS 'Primary key identifier of the vehicle.';
COMMENT ON COLUMN vehicle.code IS 'Vehicle business code ("Mã xe", e.g., XE0001..XE0008).';
COMMENT ON COLUMN vehicle.license_plate IS 'Raw license plate string preserved as entered for UI display (e.g., 51K-992.14, 51K-992-14).';
COMMENT ON COLUMN vehicle.license_plate_norm IS 'Canonical normalized license plate computed via fn_normalize_license_plate(license_plate) for uniqueness and barrier matching (TL-15, OQ-75).';
COMMENT ON COLUMN vehicle.model_name IS 'Commercial vehicle model name (e.g., Camry 2.5Q, Mazda CX-5, VF 8 Plus).';
COMMENT ON COLUMN vehicle.brand IS 'Vehicle manufacturer brand (e.g., Toyota, Mazda, VinFast; nullable per OQ-53).';
COMMENT ON COLUMN vehicle.color IS 'Exterior color of the vehicle (e.g., Trắng, Đen, Xanh rêu).';
COMMENT ON COLUMN vehicle.image_url IS 'Optional vehicle photo URI/path ("Ảnh" column on Quản lý xe — Smart Mobility.png, TL-09).';
COMMENT ON COLUMN vehicle.notes IS 'Optional free-text vehicle notes ("Ghi chú" column and "Ghi chú phương tiện" on Quản lý xe — Smart Mobility.png, TL-09).';
COMMENT ON COLUMN vehicle.vehicle_type_id IS 'Foreign key referencing vehicle_type ("Loại xe": Ô tô, Xe điện per TL-09, TL-20).';
COMMENT ON COLUMN vehicle.customer_id IS 'Foreign key referencing the owning customer ("Chủ sở hữu (Khách hàng)").';
COMMENT ON COLUMN vehicle.ticket_type_id IS 'Synchronized active ticket type preference (OQ-52, TL-15).';
COMMENT ON COLUMN vehicle.ticket_expires_at IS 'Synchronized active ticket expiration timestamp (OQ-52, TL-15).';
COMMENT ON COLUMN vehicle.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN vehicle.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN vehicle.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN vehicle.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN vehicle.deleted_by IS 'Account that performed soft deletion.';

-- =============================================================================
-- SECTION 4: PARKING FACILITY HIERARCHY, SLOTS & RESERVATIONS (TL-02, TL-03, TL-04)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 4.1. Table: parking_lot
-- Source: Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` & `Trang chủ — Smart Mobility.png`
--         ("Bãi đỗ xe: Bãi xe Smart Mobility"), TL-02, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE parking_lot (
    id BIGSERIAL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    address VARCHAR(255) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_parking_lot PRIMARY KEY (id),
    CONSTRAINT fk_parking_lot_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_parking_lot_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_parking_lot_name_nonempty CHECK (btrim(name) <> ''),
    CONSTRAINT ck_parking_lot_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_parking_lot_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_parking_lot_code_active
    ON parking_lot (code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_parking_lot_name_active
    ON parking_lot (name)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE parking_lot IS 'Top-level parking facility entity ("Bãi đỗ xe: Bãi xe Smart Mobility" on Sơ đồ bãi đậu xe and Trang chủ, TL-02).';
COMMENT ON COLUMN parking_lot.id IS 'Primary key identifier of the parking lot.';
COMMENT ON COLUMN parking_lot.code IS 'Unique code of the parking lot (e.g., SMART_MOBILITY).';
COMMENT ON COLUMN parking_lot.name IS 'Display name of the parking lot (e.g., Bãi xe Smart Mobility).';
COMMENT ON COLUMN parking_lot.address IS 'Physical address or location description of the parking lot.';
COMMENT ON COLUMN parking_lot.is_active IS 'Whether the parking facility is currently active.';
COMMENT ON COLUMN parking_lot.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN parking_lot.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN parking_lot.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN parking_lot.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN parking_lot.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 4.2. Table: parking_floor
-- Source: Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` ("+ Thêm tầng", "Tầng B1",
--         "Tầng B2", "Tầng F1 - Ngoài trời", panel "Quản lý cấu trúc bãi"), TL-02
-- -----------------------------------------------------------------------------
CREATE TABLE parking_floor (
    id BIGSERIAL,
    lot_id BIGINT NOT NULL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 1,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_parking_floor PRIMARY KEY (id),
    CONSTRAINT fk_parking_floor_lot FOREIGN KEY (lot_id)
        REFERENCES parking_lot (id) ON DELETE RESTRICT,
    CONSTRAINT fk_parking_floor_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_parking_floor_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_parking_floor_name_nonempty CHECK (btrim(name) <> ''),
    CONSTRAINT ck_parking_floor_sort_positive CHECK (sort_order > 0),
    CONSTRAINT ck_parking_floor_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_parking_floor_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_parking_floor_lot_code_active
    ON parking_floor (lot_id, code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_parking_floor_lot_name_active
    ON parking_floor (lot_id, name)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_parking_floor_lot_id ON parking_floor (lot_id) WHERE deleted_at IS NULL;

COMMENT ON TABLE parking_floor IS 'Named parking floor within a parking lot ("Tầng B1", "Tầng B2", "Tầng F1" on Sơ đồ bãi đậu xe, TL-02).';
COMMENT ON COLUMN parking_floor.id IS 'Primary key identifier of the parking floor.';
COMMENT ON COLUMN parking_floor.lot_id IS 'Foreign key referencing parent parking_lot (ON DELETE RESTRICT).';
COMMENT ON COLUMN parking_floor.code IS 'Short string code of the floor within the lot (e.g., B1, B2, B3, F1).';
COMMENT ON COLUMN parking_floor.name IS 'Display name of the floor (e.g., Tầng B1, Tầng F1 - Ngoài trời).';
COMMENT ON COLUMN parking_floor.sort_order IS 'Positive display ordering of the floor in UI tabs and trees.';
COMMENT ON COLUMN parking_floor.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN parking_floor.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN parking_floor.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN parking_floor.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN parking_floor.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 4.3. Table: parking_zone
-- Source: Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` ("+ Thêm khu", "Khu A".."Khu D",
--         "Khu VIP", panel "Quản lý cấu trúc bãi"), TL-02
-- -----------------------------------------------------------------------------
CREATE TABLE parking_zone (
    id BIGSERIAL,
    floor_id BIGINT NOT NULL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    description TEXT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_parking_zone PRIMARY KEY (id),
    CONSTRAINT fk_parking_zone_floor FOREIGN KEY (floor_id)
        REFERENCES parking_floor (id) ON DELETE RESTRICT,
    CONSTRAINT fk_parking_zone_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_parking_zone_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_parking_zone_name_nonempty CHECK (btrim(name) <> ''),
    CONSTRAINT ck_parking_zone_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_parking_zone_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_parking_zone_floor_code_active
    ON parking_zone (floor_id, code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_parking_zone_floor_name_active
    ON parking_zone (floor_id, name)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_parking_zone_floor_id ON parking_zone (floor_id) WHERE deleted_at IS NULL;

COMMENT ON TABLE parking_zone IS 'Named parking zone within a floor ("Khu A".."Khu D", "Khu VIP" on Sơ đồ bãi đậu xe, TL-02).';
COMMENT ON COLUMN parking_zone.id IS 'Primary key identifier of the parking zone.';
COMMENT ON COLUMN parking_zone.floor_id IS 'Foreign key referencing parent parking_floor (ON DELETE RESTRICT).';
COMMENT ON COLUMN parking_zone.code IS 'Short code of the zone within the floor (e.g., KHU_A, A, VIP).';
COMMENT ON COLUMN parking_zone.name IS 'Display name of the zone (e.g., Khu A, Khu VIP).';
COMMENT ON COLUMN parking_zone.description IS 'Optional description of the zone (e.g., Dãy ô tô tiêu chuẩn, Khu sạc xe điện).';
COMMENT ON COLUMN parking_zone.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN parking_zone.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN parking_zone.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN parking_zone.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN parking_zone.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 4.4. Table: parking_slot
-- Source: Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` & `Main Page.png`
--         (code "A-01", slot_kind STANDARD/PRIORITY/EV_CHARGING, 5 statuses AVAILABLE/
--         OCCUPIED/RESERVED/CHARGING/MAINTENANCE, "Ghi chú", grid coordinates & dimensions),
--         TL-02, TL-03, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE parking_slot (
    id BIGSERIAL,
    zone_id BIGINT NOT NULL,
    code VARCHAR(20) NOT NULL,
    slot_kind VARCHAR(20) NOT NULL DEFAULT 'STANDARD',
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE',
    map_row SMALLINT NULL,
    map_col SMALLINT NULL,
    width NUMERIC(5, 2) NOT NULL DEFAULT 2.50,
    length NUMERIC(5, 2) NOT NULL DEFAULT 5.00,
    height NUMERIC(5, 2) NOT NULL DEFAULT 2.20,
    notes TEXT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_parking_slot PRIMARY KEY (id),
    CONSTRAINT fk_slot_zone FOREIGN KEY (zone_id)
        REFERENCES parking_zone (id) ON DELETE RESTRICT,
    CONSTRAINT fk_slot_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_slot_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_slot_code_format CHECK (code ~ '^[A-Za-z0-9 .\-]+$'),
    CONSTRAINT ck_slot_kind_enum CHECK (slot_kind IN ('STANDARD', 'PRIORITY', 'EV_CHARGING')),
    CONSTRAINT ck_slot_status_enum CHECK (
        status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'CHARGING', 'MAINTENANCE')
    ),
    CONSTRAINT ck_slot_charging_requires_ev_kind CHECK (
        status <> 'CHARGING' OR slot_kind = 'EV_CHARGING'
    ),
    CONSTRAINT ck_slot_map_coords_pair CHECK (
        (map_row IS NULL AND map_col IS NULL) OR
        (map_row IS NOT NULL AND map_col IS NOT NULL AND map_row > 0 AND map_col > 0)
    ),
    CONSTRAINT ck_slot_dimensions_positive CHECK (width > 0 AND length > 0 AND height > 0),
    CONSTRAINT ck_slot_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_slot_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_parking_slot_zone_code_active
    ON parking_slot (zone_id, code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_parking_slot_zone_map_pos_active
    ON parking_slot (zone_id, map_row, map_col)
    WHERE deleted_at IS NULL AND map_row IS NOT NULL AND map_col IS NOT NULL;

CREATE INDEX idx_parking_slot_status_active
    ON parking_slot (zone_id, status)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE parking_slot IS 'Physical parking slot belonging to a parking_zone with 5 operational statuses, 3 slot kinds, 2D map coordinates, physical dimensions, and free-text notes (Sơ đồ bãi đậu xe — Smart Mobility.png, Main Page.png, TL-02, TL-03).';
COMMENT ON COLUMN parking_slot.id IS 'Primary key identifier of the parking slot.';
COMMENT ON COLUMN parking_slot.zone_id IS 'Foreign key referencing parent parking_zone (TL-02).';
COMMENT ON COLUMN parking_slot.code IS 'Display code of the slot within the zone (e.g., A-01, A10, B-01, Slot 42; TL-02).';
COMMENT ON COLUMN parking_slot.slot_kind IS 'Physical classification of the slot: STANDARD (tiêu chuẩn), PRIORITY (xe ưu tiên), or EV_CHARGING (sạc xe điện) (TL-03).';
COMMENT ON COLUMN parking_slot.status IS 'Operational status: AVAILABLE (Trống), OCCUPIED (Đang có xe), RESERVED (Đã đặt trước), CHARGING (Sạc xe điện), or MAINTENANCE (Bảo trì) (TL-03).';
COMMENT ON COLUMN parking_slot.map_row IS '1-based row coordinate on the 2D zone/floor map grid (TL-02, OQ-69).';
COMMENT ON COLUMN parking_slot.map_col IS '1-based column coordinate on the 2D zone/floor map grid (TL-02, OQ-69).';
COMMENT ON COLUMN parking_slot.width IS 'Slot width in meters (must be > 0, SRS 4.8.2, TL-02).';
COMMENT ON COLUMN parking_slot.length IS 'Slot length in meters (must be > 0, SRS 4.8.2, TL-02).';
COMMENT ON COLUMN parking_slot.height IS 'Slot height clearance in meters (must be > 0, SRS 4.8.2, TL-02).';
COMMENT ON COLUMN parking_slot.notes IS 'Optional free-text note for the slot ("Ghi chú" in Chi tiết ô đỗ on Sơ đồ bãi đậu xe, TL-03).';
COMMENT ON COLUMN parking_slot.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN parking_slot.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN parking_slot.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN parking_slot.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN parking_slot.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 4.5. Table: slot_allowed_vehicle_type
-- Source: Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` ("Loại xe: Ô tô 4-7 chỗ"), TL-03, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE slot_allowed_vehicle_type (
    slot_id BIGINT NOT NULL,
    vehicle_type_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_slot_allowed_vehicle_type PRIMARY KEY (slot_id, vehicle_type_id),
    CONSTRAINT fk_savt_slot FOREIGN KEY (slot_id)
        REFERENCES parking_slot (id) ON DELETE RESTRICT,
    CONSTRAINT fk_savt_vehicle_type FOREIGN KEY (vehicle_type_id)
        REFERENCES vehicle_type (id) ON DELETE RESTRICT
);

CREATE INDEX idx_savt_vehicle_type_id ON slot_allowed_vehicle_type (vehicle_type_id);

COMMENT ON TABLE slot_allowed_vehicle_type IS 'Many-to-many junction specifying permitted vehicle_type categories per parking_slot (TL-03, TL-15, SRS 4.8.2).';
COMMENT ON COLUMN slot_allowed_vehicle_type.slot_id IS 'Foreign key referencing parking_slot.';
COMMENT ON COLUMN slot_allowed_vehicle_type.vehicle_type_id IS 'Foreign key referencing allowed vehicle_type.';
COMMENT ON COLUMN slot_allowed_vehicle_type.created_at IS 'Association creation timestamp.';

-- -----------------------------------------------------------------------------
-- 4.6. Table: slot_reservation
-- Source: Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` ("ĐÃ ĐẶT 13:30", "Người đặt trước",
--         "Đặt trước ô A-04 cho xe 30E-456.78 lúc 13:30"), TL-04, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE slot_reservation (
    id BIGSERIAL,
    code VARCHAR(30) NOT NULL,
    slot_id BIGINT NOT NULL,
    customer_id BIGINT NULL,
    vehicle_id BIGINT NULL,
    reserved_name VARCHAR(100) NULL,
    reserved_phone VARCHAR(15) NULL,
    reserved_from TIMESTAMPTZ NOT NULL,
    reserved_until TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    notes TEXT NULL,
    created_by BIGINT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_slot_reservation PRIMARY KEY (id),
    CONSTRAINT fk_reservation_slot FOREIGN KEY (slot_id)
        REFERENCES parking_slot (id) ON DELETE RESTRICT,
    CONSTRAINT fk_reservation_customer FOREIGN KEY (customer_id)
        REFERENCES customer (id) ON DELETE RESTRICT,
    CONSTRAINT fk_reservation_vehicle FOREIGN KEY (vehicle_id)
        REFERENCES vehicle (id) ON DELETE RESTRICT,
    CONSTRAINT fk_reservation_created_by FOREIGN KEY (created_by)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT fk_reservation_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_reservation_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_reservation_time_order CHECK (reserved_until > reserved_from),
    CONSTRAINT ck_reservation_status_enum CHECK (
        status IN ('ACTIVE', 'COMPLETED', 'CANCELLED', 'EXPIRED')
    ),
    CONSTRAINT ck_reservation_phone_digits CHECK (
        reserved_phone IS NULL OR reserved_phone ~ '^[0-9]{9,15}$'
    ),
    CONSTRAINT ck_reservation_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_reservation_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    ),
    CONSTRAINT excl_reservation_slot_time_overlap EXCLUDE USING gist (
        slot_id WITH =,
        tstzrange(reserved_from, reserved_until, '[)') WITH &&
    ) WHERE (deleted_at IS NULL AND status = 'ACTIVE')
);

CREATE UNIQUE INDEX uq_reservation_code_active
    ON slot_reservation (code)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_reservation_slot_status
    ON slot_reservation (slot_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_slot_reservation_customer_id ON slot_reservation (customer_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_slot_reservation_vehicle_id ON slot_reservation (vehicle_id) WHERE deleted_at IS NULL;

COMMENT ON TABLE slot_reservation IS 'Advance parking slot reservations with GiST anti-overlap exclusion on active reservations ("ĐÃ ĐẶT 13:30", "Người đặt trước" on Sơ đồ bãi đậu xe, TL-04).';
COMMENT ON COLUMN slot_reservation.id IS 'Primary key identifier of the slot reservation.';
COMMENT ON COLUMN slot_reservation.code IS 'Unique reservation reference code among active records.';
COMMENT ON COLUMN slot_reservation.slot_id IS 'Foreign key referencing the reserved parking_slot.';
COMMENT ON COLUMN slot_reservation.customer_id IS 'Optional foreign key referencing a registered customer.';
COMMENT ON COLUMN slot_reservation.vehicle_id IS 'Optional foreign key referencing a registered vehicle.';
COMMENT ON COLUMN slot_reservation.reserved_name IS 'Display name of the reserver when booked for a walk-in/visitor ("Người đặt trước", TL-04).';
COMMENT ON COLUMN slot_reservation.reserved_phone IS 'Contact phone number of the reserver.';
COMMENT ON COLUMN slot_reservation.reserved_from IS 'Reservation start timestamp (inclusive lower bound).';
COMMENT ON COLUMN slot_reservation.reserved_until IS 'Reservation end timestamp (exclusive upper bound, must be > reserved_from).';
COMMENT ON COLUMN slot_reservation.status IS 'Reservation lifecycle status: ACTIVE, COMPLETED, CANCELLED, or EXPIRED (TL-04, OQ-81).';
COMMENT ON COLUMN slot_reservation.notes IS 'Optional reservation notes.';
COMMENT ON COLUMN slot_reservation.created_by IS 'Optional foreign key referencing the employee who created the reservation.';
COMMENT ON COLUMN slot_reservation.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN slot_reservation.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN slot_reservation.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN slot_reservation.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN slot_reservation.deleted_by IS 'Account that performed soft deletion.';

-- =============================================================================
-- SECTION 5: TICKETING & RENEWAL MODULE (TL-10, TL-15, SRS 4.6)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 5.1. Table: ticket
-- Source: Frontend `Quản lý vé — Smart Mobility.png` (main list & 3 dialogs:
--         "Thêm vé mới", "Gia hạn vé", "Chi tiết vé"; statuses ACTIVE, EXPIRED,
--         CANCELLED, RENEWING; "Sắp hết hạn" is derived from dates; "Ghi chú"), TL-10, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE ticket (
    id BIGSERIAL,
    code VARCHAR(10) NOT NULL,
    vehicle_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    slot_id BIGINT NOT NULL,
    ticket_type_id BIGINT NOT NULL,
    issued_by BIGINT NULL,
    price NUMERIC(12, 2) NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    effective_to TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    notes TEXT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_ticket PRIMARY KEY (id),
    CONSTRAINT fk_ticket_vehicle_customer FOREIGN KEY (vehicle_id, customer_id)
        REFERENCES vehicle (id, customer_id) ON DELETE RESTRICT,
    CONSTRAINT fk_ticket_customer FOREIGN KEY (customer_id)
        REFERENCES customer (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ticket_slot FOREIGN KEY (slot_id)
        REFERENCES parking_slot (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ticket_type FOREIGN KEY (ticket_type_id)
        REFERENCES ticket_type (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ticket_issued_by FOREIGN KEY (issued_by)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ticket_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_ticket_code_format CHECK (code ~ '^[A-Za-z0-9-]+$'),
    CONSTRAINT ck_ticket_price_nonnegative CHECK (price >= 0),
    CONSTRAINT ck_ticket_time_order CHECK (effective_to > effective_from),
    CONSTRAINT ck_ticket_status_enum CHECK (
        status IN ('ACTIVE', 'EXPIRED', 'CANCELLED', 'RENEWING')
    ),
    CONSTRAINT ck_ticket_delete_only_expired CHECK (
        deleted_at IS NULL OR effective_to <= deleted_at
    ),
    CONSTRAINT ck_ticket_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_ticket_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    ),
    CONSTRAINT excl_ticket_slot_time_overlap EXCLUDE USING gist (
        slot_id WITH =,
        tstzrange(effective_from, effective_to, '[)') WITH &&
    ) WHERE (deleted_at IS NULL AND status IN ('ACTIVE', 'RENEWING'))
);

CREATE UNIQUE INDEX uq_ticket_code_active
    ON ticket (code)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_ticket_customer_id ON ticket (customer_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_ticket_vehicle_id ON ticket (vehicle_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_ticket_slot_id ON ticket (slot_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_ticket_ticket_type_id ON ticket (ticket_type_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_ticket_status_effective ON ticket (status, effective_to) WHERE deleted_at IS NULL;
CREATE INDEX idx_ticket_stat_active ON ticket (created_at) WHERE deleted_at IS NULL;

COMMENT ON TABLE ticket IS 'Issued parking tickets with GiST non-overlapping slot exclusion, composite vehicle-customer ownership FK, notes, and statuses ACTIVE, EXPIRED, CANCELLED, RENEWING ("Sắp hết hạn" is derived from effective_to; Quản lý vé — Smart Mobility.png, TL-10, TL-15).';
COMMENT ON COLUMN ticket.id IS 'Primary key identifier of the ticket.';
COMMENT ON COLUMN ticket.code IS 'Unique ticket business code ("Mã vé", e.g., VT0001..VT0006).';
COMMENT ON COLUMN ticket.vehicle_id IS 'Foreign key referencing registered vehicle (part of composite FK with customer_id per OQ-61).';
COMMENT ON COLUMN ticket.customer_id IS 'Foreign key referencing ticket owner customer.';
COMMENT ON COLUMN ticket.slot_id IS 'Foreign key referencing assigned physical parking_slot.';
COMMENT ON COLUMN ticket.ticket_type_id IS 'Foreign key referencing tariff ticket_type.';
COMMENT ON COLUMN ticket.issued_by IS 'Optional foreign key referencing the employee who issued the ticket.';
COMMENT ON COLUMN ticket.price IS 'Billed ticket price in VND ("Giá vé (VNĐ)").';
COMMENT ON COLUMN ticket.effective_from IS 'Ticket validity start timestamp ("Ngày bắt đầu").';
COMMENT ON COLUMN ticket.effective_to IS 'Ticket validity end timestamp ("Ngày kết thúc", must be > effective_from).';
COMMENT ON COLUMN ticket.status IS 'Stored ticket lifecycle status: ACTIVE (Đang hiệu lực), EXPIRED (Hết hạn), CANCELLED (Đã hủy), or RENEWING (Đang gia hạn); "Sắp hết hạn" is derived from effective_to (TL-10).';
COMMENT ON COLUMN ticket.notes IS 'Optional ticket notes ("Ghi chú" on Thêm vé mới and Chi tiết vé dialogs, TL-10).';
COMMENT ON COLUMN ticket.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN ticket.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN ticket.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN ticket.deleted_at IS 'Soft deletion timestamp; permitted only after expiration (ck_ticket_delete_only_expired, OQ-64).';
COMMENT ON COLUMN ticket.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 5.2. Table: ticket_renewal
-- Source: Frontend `Quản lý vé — Smart Mobility.png` (Dialog 2 "Gia hạn vé" & Dialog 3
--         "Lịch sử gia hạn", including "Ghi chú gia hạn"), TL-10, TL-15, OQ-58
-- -----------------------------------------------------------------------------
CREATE TABLE ticket_renewal (
    id BIGSERIAL,
    ticket_id BIGINT NOT NULL,
    old_slot_id BIGINT NOT NULL,
    new_slot_id BIGINT NOT NULL,
    old_ticket_type_id BIGINT NULL,
    new_ticket_type_id BIGINT NULL,
    old_price NUMERIC(12, 2) NULL,
    new_price NUMERIC(12, 2) NULL,
    old_effective_to TIMESTAMPTZ NOT NULL,
    new_effective_to TIMESTAMPTZ NOT NULL,
    additional_price NUMERIC(12, 2) NOT NULL DEFAULT 0,
    notes TEXT NULL,
    renewed_by BIGINT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT pk_ticket_renewal PRIMARY KEY (id),
    CONSTRAINT fk_renewal_ticket FOREIGN KEY (ticket_id)
        REFERENCES ticket (id) ON DELETE RESTRICT,
    CONSTRAINT fk_renewal_old_slot FOREIGN KEY (old_slot_id)
        REFERENCES parking_slot (id) ON DELETE RESTRICT,
    CONSTRAINT fk_renewal_new_slot FOREIGN KEY (new_slot_id)
        REFERENCES parking_slot (id) ON DELETE RESTRICT,
    CONSTRAINT fk_renewal_old_ticket_type FOREIGN KEY (old_ticket_type_id)
        REFERENCES ticket_type (id) ON DELETE RESTRICT,
    CONSTRAINT fk_renewal_new_ticket_type FOREIGN KEY (new_ticket_type_id)
        REFERENCES ticket_type (id) ON DELETE RESTRICT,
    CONSTRAINT fk_renewal_staff FOREIGN KEY (renewed_by)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT ck_renewal_time_extension CHECK (new_effective_to > old_effective_to),
    CONSTRAINT ck_renewal_price_nonnegative CHECK (
        additional_price >= 0 AND
        (old_price IS NULL OR old_price >= 0) AND
        (new_price IS NULL OR new_price >= 0)
    ),
    CONSTRAINT ck_renewal_row_version_positive CHECK (row_version >= 1)
);

CREATE INDEX idx_ticket_renewal_ticket_id ON ticket_renewal (ticket_id);
CREATE INDEX idx_ticket_renewal_created_at ON ticket_renewal (created_at);

COMMENT ON TABLE ticket_renewal IS 'Immutable financial and operational audit trail of ticket renewals ("Gia hạn vé" & "Lịch sử gia hạn" on Quản lý vé — Smart Mobility.png, TL-10, TL-15, OQ-58).';
COMMENT ON COLUMN ticket_renewal.id IS 'Primary key identifier of the renewal record.';
COMMENT ON COLUMN ticket_renewal.ticket_id IS 'Foreign key referencing the renewed ticket.';
COMMENT ON COLUMN ticket_renewal.old_slot_id IS 'Foreign key referencing parking_slot prior to renewal.';
COMMENT ON COLUMN ticket_renewal.new_slot_id IS 'Foreign key referencing parking_slot after renewal ("Đổi vị trí đỗ (tùy chọn)").';
COMMENT ON COLUMN ticket_renewal.old_ticket_type_id IS 'Foreign key referencing ticket_type prior to renewal (OQ-58).';
COMMENT ON COLUMN ticket_renewal.new_ticket_type_id IS 'Foreign key referencing newly selected ticket_type ("Loại vé gia hạn", OQ-58).';
COMMENT ON COLUMN ticket_renewal.old_price IS 'Ticket price prior to renewal (OQ-58).';
COMMENT ON COLUMN ticket_renewal.new_price IS 'New ticket tariff price upon renewal (OQ-58).';
COMMENT ON COLUMN ticket_renewal.old_effective_to IS 'Previous expiration timestamp before renewal ("Hạn hiện tại").';
COMMENT ON COLUMN ticket_renewal.new_effective_to IS 'Extended expiration timestamp after renewal ("Ngày kết thúc mới").';
COMMENT ON COLUMN ticket_renewal.additional_price IS 'Renewal fee charged for the extension ("Giá gia hạn").';
COMMENT ON COLUMN ticket_renewal.notes IS 'Optional renewal note ("Ghi chú gia hạn" on Dialog 2 Gia hạn vé, TL-10).';
COMMENT ON COLUMN ticket_renewal.renewed_by IS 'Optional foreign key referencing the employee who processed the renewal.';
COMMENT ON COLUMN ticket_renewal.created_at IS 'Timestamp when the renewal transaction occurred.';
COMMENT ON COLUMN ticket_renewal.row_version IS 'Concurrency version counter.';

-- =============================================================================
-- SECTION 6: GATES, ENTRY/EXIT SESSIONS & PAYMENTS (TL-05, TL-06, TL-07, TL-15)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 6.1. Table: parking_gate
-- Source: Frontend `Trang chủ — Smart Mobility.png` ("4 Cổng quét tự động",
--         "Cổng vào 1", "Cổng vào 2", "Cổng ra 1", "Cổng ra 2", "Camera cổng ra 1"), TL-06
-- -----------------------------------------------------------------------------
CREATE TABLE parking_gate (
    id BIGSERIAL,
    lot_id BIGINT NOT NULL,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    camera_status VARCHAR(20) NOT NULL DEFAULT 'ONLINE',
    is_auto_scan BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_parking_gate PRIMARY KEY (id),
    CONSTRAINT fk_parking_gate_lot FOREIGN KEY (lot_id)
        REFERENCES parking_lot (id) ON DELETE RESTRICT,
    CONSTRAINT fk_parking_gate_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_gate_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_gate_name_nonempty CHECK (btrim(name) <> ''),
    CONSTRAINT ck_gate_direction_enum CHECK (direction IN ('IN', 'OUT')),
    CONSTRAINT ck_gate_camera_status_enum CHECK (
        camera_status IN ('ONLINE', 'LOW_LIGHT', 'DEGRADED', 'OFFLINE')
    ),
    CONSTRAINT ck_gate_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_gate_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_parking_gate_lot_code_active
    ON parking_gate (lot_id, code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX uq_parking_gate_lot_name_active
    ON parking_gate (lot_id, name)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE parking_gate IS 'Entry and exit barrier gates with camera health and AI auto-scan status ("4 Cổng quét tự động", "Cổng vào 1", "Camera cổng ra 1" on Trang chủ, TL-06).';
COMMENT ON COLUMN parking_gate.id IS 'Primary key identifier of the parking gate.';
COMMENT ON COLUMN parking_gate.lot_id IS 'Foreign key referencing parent parking_lot.';
COMMENT ON COLUMN parking_gate.code IS 'Unique gate code within the parking lot (e.g., IN_01, OUT_01).';
COMMENT ON COLUMN parking_gate.name IS 'Display name of the gate (e.g., Cổng vào 1, Cổng ra 1; TL-06).';
COMMENT ON COLUMN parking_gate.direction IS 'Gate traffic direction: IN (entry) or OUT (exit) (TL-06).';
COMMENT ON COLUMN parking_gate.camera_status IS 'Operational health of the gate ALPR camera: ONLINE, LOW_LIGHT, DEGRADED, or OFFLINE (TL-06, OQ-81).';
COMMENT ON COLUMN parking_gate.is_auto_scan IS 'Whether automatic AI license plate scanning is enabled on this gate ("4 Cổng quét tự động", TL-06).';
COMMENT ON COLUMN parking_gate.is_active IS 'Whether the gate is currently active in operation.';
COMMENT ON COLUMN parking_gate.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN parking_gate.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN parking_gate.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN parking_gate.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN parking_gate.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 6.2. Table: vehicle_entry_exit_log
-- Source: Frontend `Lịch sử ra/vào — Smart Mobility.png` ("Mã phiên đỗ xe", "Cước phí",
--         "Hình ảnh đối soát") & `Trang chủ — Smart Mobility.png` ("Xem ảnh (99%)",
--         "Ảnh khớp", "Cần duyệt", "Nhập thủ công: 1.6%"), TL-05, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE vehicle_entry_exit_log (
    id BIGSERIAL,
    session_code VARCHAR(30) NOT NULL,
    vehicle_id BIGINT NULL,
    slot_id BIGINT NULL,
    ticket_id BIGINT NULL,
    entry_gate_id BIGINT NULL,
    exit_gate_id BIGINT NULL,
    license_plate VARCHAR(20) NOT NULL,
    license_plate_norm VARCHAR(20) GENERATED ALWAYS AS (fn_normalize_license_plate(license_plate)) STORED,
    ai_confidence NUMERIC(5, 2) NULL,
    recognition_source VARCHAR(20) NOT NULL DEFAULT 'AI',
    review_status VARCHAR(20) NOT NULL DEFAULT 'AUTO',
    fee_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    entry_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    exit_time TIMESTAMPTZ NULL,
    entry_image_url TEXT NULL,
    exit_image_url TEXT NULL,
    entry_handled_by BIGINT NULL,
    exit_handled_by BIGINT NULL,
    notes TEXT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_vehicle_entry_exit_log PRIMARY KEY (id),
    CONSTRAINT uq_log_session_code UNIQUE (session_code),
    CONSTRAINT fk_log_vehicle FOREIGN KEY (vehicle_id)
        REFERENCES vehicle (id) ON DELETE RESTRICT,
    CONSTRAINT fk_log_slot FOREIGN KEY (slot_id)
        REFERENCES parking_slot (id) ON DELETE RESTRICT,
    CONSTRAINT fk_log_ticket FOREIGN KEY (ticket_id)
        REFERENCES ticket (id) ON DELETE RESTRICT,
    CONSTRAINT fk_log_entry_gate FOREIGN KEY (entry_gate_id)
        REFERENCES parking_gate (id) ON DELETE RESTRICT,
    CONSTRAINT fk_log_exit_gate FOREIGN KEY (exit_gate_id)
        REFERENCES parking_gate (id) ON DELETE RESTRICT,
    CONSTRAINT fk_log_entry_staff FOREIGN KEY (entry_handled_by)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT fk_log_exit_staff FOREIGN KEY (exit_handled_by)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT ck_log_session_code_nonempty CHECK (btrim(session_code) <> ''),
    CONSTRAINT ck_log_license_plate_nonempty CHECK (btrim(license_plate) <> ''),
    CONSTRAINT ck_log_license_plate_format CHECK (license_plate ~ '^[A-Za-z0-9 .\-]+$'),
    CONSTRAINT ck_log_license_plate_norm_nonempty CHECK (license_plate_norm <> ''),
    CONSTRAINT ck_log_ai_confidence_range CHECK (
        ai_confidence IS NULL OR (ai_confidence >= 0 AND ai_confidence <= 100)
    ),
    CONSTRAINT ck_log_recognition_source_enum CHECK (
        recognition_source IN ('AI', 'MANUAL')
    ),
    CONSTRAINT ck_log_review_status_enum CHECK (
        review_status IN ('AUTO', 'MATCHED', 'NEEDS_REVIEW', 'APPROVED', 'REJECTED')
    ),
    CONSTRAINT ck_log_fee_nonnegative CHECK (fee_amount >= 0),
    CONSTRAINT ck_log_exit_after_entry CHECK (exit_time IS NULL OR exit_time >= entry_time),
    CONSTRAINT ck_log_row_version_positive CHECK (row_version >= 1)
);

CREATE UNIQUE INDEX uq_log_open_session_slot
    ON vehicle_entry_exit_log (slot_id)
    WHERE exit_time IS NULL AND slot_id IS NOT NULL;

CREATE UNIQUE INDEX uq_log_open_session_vehicle
    ON vehicle_entry_exit_log (vehicle_id)
    WHERE exit_time IS NULL AND vehicle_id IS NOT NULL;

CREATE UNIQUE INDEX uq_log_open_session_plate
    ON vehicle_entry_exit_log (license_plate_norm)
    WHERE exit_time IS NULL;

CREATE INDEX idx_log_vehicle_id ON vehicle_entry_exit_log (vehicle_id);
CREATE INDEX idx_log_slot_id ON vehicle_entry_exit_log (slot_id);
CREATE INDEX idx_entry_exit_ticket_id ON vehicle_entry_exit_log (ticket_id);
CREATE INDEX idx_entry_exit_gates ON vehicle_entry_exit_log (entry_gate_id, exit_gate_id);
CREATE INDEX idx_entry_exit_exit_gate_id ON vehicle_entry_exit_log (exit_gate_id);
CREATE INDEX idx_log_entry_time ON vehicle_entry_exit_log (entry_time);
CREATE INDEX idx_log_exit_time ON vehicle_entry_exit_log (exit_time);
CREATE INDEX idx_log_license_plate ON vehicle_entry_exit_log (license_plate_norm);
CREATE INDEX idx_log_review_status ON vehicle_entry_exit_log (review_status, entry_time DESC);
CREATE INDEX idx_log_license_plate_trgm ON vehicle_entry_exit_log USING gin (license_plate_norm gin_trgm_ops);
CREATE INDEX idx_log_session_code_trgm ON vehicle_entry_exit_log USING gin (session_code gin_trgm_ops);

COMMENT ON TABLE vehicle_entry_exit_log IS 'Barrier entry/exit parking sessions supporting both registered vehicles and unregistered visitors (vehicle_id NULL), with session_code, entry/exit gates, AI confidence, recognition source, review status, and fee amount (Lịch sử ra/vào & Trang chủ, TL-05, TL-15).';
COMMENT ON COLUMN vehicle_entry_exit_log.id IS 'Primary key identifier of the parking session log.';
COMMENT ON COLUMN vehicle_entry_exit_log.session_code IS 'Unique parking session code ("Mã phiên đỗ xe", e.g., #PK-20260414-01; TL-05).';
COMMENT ON COLUMN vehicle_entry_exit_log.vehicle_id IS 'Optional foreign key referencing registered vehicle; NULL for unregistered visitor vehicles (TL-05).';
COMMENT ON COLUMN vehicle_entry_exit_log.slot_id IS 'Optional foreign key referencing occupied physical parking_slot.';
COMMENT ON COLUMN vehicle_entry_exit_log.ticket_id IS 'Optional foreign key referencing subscription ticket applied to the session.';
COMMENT ON COLUMN vehicle_entry_exit_log.entry_gate_id IS 'Optional foreign key referencing entry parking_gate ("Cổng vào 1/2", TL-05, TL-06).';
COMMENT ON COLUMN vehicle_entry_exit_log.exit_gate_id IS 'Optional foreign key referencing exit parking_gate ("Cổng ra 1/2", TL-05, TL-06).';
COMMENT ON COLUMN vehicle_entry_exit_log.license_plate IS 'Raw license plate captured or entered at barrier gate.';
COMMENT ON COLUMN vehicle_entry_exit_log.license_plate_norm IS 'Canonical normalized license plate computed via fn_normalize_license_plate(license_plate) (TL-05, TL-15, OQ-75).';
COMMENT ON COLUMN vehicle_entry_exit_log.ai_confidence IS 'ALPR recognition confidence percentage 0..100 ("Xem ảnh (99%)", "84%", TL-05).';
COMMENT ON COLUMN vehicle_entry_exit_log.recognition_source IS 'Plate capture source: AI (automatic camera OCR) or MANUAL ("Nhập thủ công", TL-05).';
COMMENT ON COLUMN vehicle_entry_exit_log.review_status IS 'Verification status: AUTO, MATCHED ("Ảnh khớp"), NEEDS_REVIEW ("Cần duyệt"), APPROVED, or REJECTED (TL-05, OQ-81).';
COMMENT ON COLUMN vehicle_entry_exit_log.fee_amount IS 'Session parking fee in VND ("Cước phí" / "Cước phí tạm tính", TL-05, TL-07, OQ-80).';
COMMENT ON COLUMN vehicle_entry_exit_log.entry_time IS 'Check-in timestamp when vehicle entered the parking lot ("Thời gian vào").';
COMMENT ON COLUMN vehicle_entry_exit_log.exit_time IS 'Check-out timestamp when vehicle exited the parking lot ("Thời gian ra"); NULL while parked.';
COMMENT ON COLUMN vehicle_entry_exit_log.entry_image_url IS 'Check-in comparison camera snapshot URI ("Ảnh lúc vào" under Hình ảnh đối soát, TL-05, OQ-60).';
COMMENT ON COLUMN vehicle_entry_exit_log.exit_image_url IS 'Check-out comparison camera snapshot URI ("Ảnh lúc ra" under Hình ảnh đối soát, TL-05, OQ-60).';
COMMENT ON COLUMN vehicle_entry_exit_log.entry_handled_by IS 'Optional foreign key referencing employee on duty at entry.';
COMMENT ON COLUMN vehicle_entry_exit_log.exit_handled_by IS 'Optional foreign key referencing employee on duty at exit.';
COMMENT ON COLUMN vehicle_entry_exit_log.notes IS 'Optional operator notes for the session.';
COMMENT ON COLUMN vehicle_entry_exit_log.row_version IS 'Concurrency version counter.';
COMMENT ON COLUMN vehicle_entry_exit_log.created_at IS 'Log record creation timestamp.';

-- -----------------------------------------------------------------------------
-- 6.3. Table: payment
-- Source: Frontend `Trang chủ — Smart Mobility.png` ("Doanh thu hôm nay",
--         "Tiền mặt: 18% | QR: 82%"), `Main Page.png` ("VietQR"), `Quản lý vé`
--         ("Giá vé", "Giá gia hạn"), `Lịch sử ra/vào` ("Cước phí"), TL-07
-- -----------------------------------------------------------------------------
CREATE TABLE payment (
    id BIGSERIAL,
    code VARCHAR(30) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    method VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'UNPAID',
    paid_at TIMESTAMPTZ NULL,
    received_by BIGINT NULL,
    provider_ref VARCHAR(100) NULL,
    session_id BIGINT NULL,
    ticket_id BIGINT NULL,
    renewal_id BIGINT NULL,
    notes TEXT NULL,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_payment PRIMARY KEY (id),
    CONSTRAINT fk_payment_received_by FOREIGN KEY (received_by)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT fk_payment_session FOREIGN KEY (session_id)
        REFERENCES vehicle_entry_exit_log (id) ON DELETE RESTRICT,
    CONSTRAINT fk_payment_ticket FOREIGN KEY (ticket_id)
        REFERENCES ticket (id) ON DELETE RESTRICT,
    CONSTRAINT fk_payment_renewal FOREIGN KEY (renewal_id)
        REFERENCES ticket_renewal (id) ON DELETE RESTRICT,
    CONSTRAINT fk_payment_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_payment_code_nonempty CHECK (btrim(code) <> ''),
    CONSTRAINT ck_payment_amount_nonnegative CHECK (amount >= 0),
    CONSTRAINT ck_payment_method_enum CHECK (method IN ('CASH', 'VIETQR')),
    CONSTRAINT ck_payment_status_enum CHECK (
        status IN ('UNPAID', 'PAID', 'CANCELLED', 'REFUNDED')
    ),
    CONSTRAINT ck_payment_paid_timestamp CHECK (
        status NOT IN ('PAID', 'REFUNDED') OR paid_at IS NOT NULL
    ),
    CONSTRAINT ck_payment_single_target CHECK (
        num_nonnulls(session_id, ticket_id, renewal_id) = 1
    ),
    CONSTRAINT ck_payment_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_payment_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_payment_code_active
    ON payment (code)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_payment_session_id ON payment (session_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_payment_ticket_id ON payment (ticket_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_payment_renewal_id ON payment (renewal_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_payment_paid_at_method ON payment (paid_at, method) WHERE deleted_at IS NULL AND status = 'PAID';
CREATE INDEX idx_payment_revenue_today ON payment ((COALESCE(paid_at, created_at))) WHERE deleted_at IS NULL AND status = 'PAID';

COMMENT ON TABLE payment IS 'Unified financial payment transactions supporting CASH and VIETQR methods and targeting exactly one session, ticket, or ticket_renewal (Trang chủ, Main Page, Quản lý vé, Lịch sử ra/vào, TL-07).';
COMMENT ON COLUMN payment.id IS 'Primary key identifier of the payment record.';
COMMENT ON COLUMN payment.code IS 'Unique payment transaction code among active records.';
COMMENT ON COLUMN payment.amount IS 'Payment amount in VND (NUMERIC(12,2), must be >= 0).';
COMMENT ON COLUMN payment.method IS 'Payment method: CASH ("Tiền mặt") or VIETQR ("QR" / "VietQR") (TL-07).';
COMMENT ON COLUMN payment.status IS 'Payment lifecycle status: UNPAID, PAID, CANCELLED, or REFUNDED (TL-07, OQ-81).';
COMMENT ON COLUMN payment.paid_at IS 'Timestamp when payment was settled; NULL while UNPAID.';
COMMENT ON COLUMN payment.received_by IS 'Optional foreign key referencing cashier/operator employee.';
COMMENT ON COLUMN payment.provider_ref IS 'Optional external payment reference or VietQR transfer narrative (TL-07, OQ-82).';
COMMENT ON COLUMN payment.session_id IS 'Optional foreign key referencing vehicle_entry_exit_log (exactly one of session_id, ticket_id, renewal_id must be non-null per ck_payment_single_target).';
COMMENT ON COLUMN payment.ticket_id IS 'Optional foreign key referencing ticket (initial ticket purchase target).';
COMMENT ON COLUMN payment.renewal_id IS 'Optional foreign key referencing ticket_renewal (ticket renewal target).';
COMMENT ON COLUMN payment.notes IS 'Optional payment notes.';
COMMENT ON COLUMN payment.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN payment.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN payment.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN payment.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN payment.deleted_by IS 'Account that performed soft deletion.';

-- =============================================================================
-- SECTION 7: ACTIVITY FEED, ALERTS, NEWS & NOTIFICATIONS (TL-12, TL-13, TL-15)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 7.1. Table: activity_log
-- Source: Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` ("Hoạt động gần đây"), TL-12
-- -----------------------------------------------------------------------------
CREATE TABLE activity_log (
    id BIGSERIAL,
    actor_account_id BIGINT NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id BIGINT NULL,
    message TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_activity_log PRIMARY KEY (id),
    CONSTRAINT fk_activity_log_actor FOREIGN KEY (actor_account_id)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_activity_log_action_nonempty CHECK (btrim(action) <> ''),
    CONSTRAINT ck_activity_log_entity_type_nonempty CHECK (btrim(entity_type) <> ''),
    CONSTRAINT ck_activity_log_message_nonempty CHECK (btrim(message) <> '')
);

CREATE INDEX idx_activity_log_occurred_at ON activity_log (occurred_at DESC);
CREATE INDEX idx_activity_log_entity ON activity_log (entity_type, entity_id);

COMMENT ON TABLE activity_log IS 'Append-only operational activity feed ("Hoạt động gần đây" on Sơ đồ bãi đậu xe — Smart Mobility.png, TL-12).';
COMMENT ON COLUMN activity_log.id IS 'Primary key identifier of the activity log entry.';
COMMENT ON COLUMN activity_log.actor_account_id IS 'Optional foreign key referencing the account that performed the action (NULL for automated gate/system events).';
COMMENT ON COLUMN activity_log.action IS 'Action code (e.g., SLOT_CHECKIN, SLOT_RESERVE, SLOT_MAINTENANCE, SLOT_CREATE).';
COMMENT ON COLUMN activity_log.entity_type IS 'Target domain entity type (e.g., PARKING_SLOT, VEHICLE_SESSION, TICKET).';
COMMENT ON COLUMN activity_log.entity_id IS 'Optional identifier of the affected domain record.';
COMMENT ON COLUMN activity_log.message IS 'Human-readable Vietnamese activity description displayed in "Hoạt động gần đây".';
COMMENT ON COLUMN activity_log.occurred_at IS 'Timestamp when the activity occurred.';

-- -----------------------------------------------------------------------------
-- 7.2. Table: system_alert
-- Source: Frontend `Trang chủ — Smart Mobility.png` ("Cảnh báo bất thường & khẩn cấp":
--         Blacklist plate, Overstay 36h, Low-light camera quality), TL-13
-- -----------------------------------------------------------------------------
CREATE TABLE system_alert (
    id BIGSERIAL,
    alert_type VARCHAR(30) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    entity_type VARCHAR(50) NULL,
    entity_id BIGINT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ NULL,
    resolved_by BIGINT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_system_alert PRIMARY KEY (id),
    CONSTRAINT fk_system_alert_resolved_by FOREIGN KEY (resolved_by)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT ck_alert_type_enum CHECK (
        alert_type IN ('BLACKLIST_PLATE', 'OVERSTAY', 'CAMERA_QUALITY', 'SYSTEM')
    ),
    CONSTRAINT ck_alert_severity_enum CHECK (
        severity IN ('INFO', 'WARNING', 'CRITICAL')
    ),
    CONSTRAINT ck_alert_message_nonempty CHECK (btrim(message) <> ''),
    CONSTRAINT ck_alert_resolution_order CHECK (
        resolved_at IS NULL OR resolved_at >= occurred_at
    )
);

CREATE INDEX idx_system_alert_unresolved
    ON system_alert (occurred_at DESC)
    WHERE resolved_at IS NULL;

COMMENT ON TABLE system_alert IS 'Operational and security anomaly alerts ("Cảnh báo bất thường & khẩn cấp" on Trang chủ — Smart Mobility.png, TL-13).';
COMMENT ON COLUMN system_alert.id IS 'Primary key identifier of the system alert.';
COMMENT ON COLUMN system_alert.alert_type IS 'Alert category: BLACKLIST_PLATE, OVERSTAY, CAMERA_QUALITY, or SYSTEM (TL-13, OQ-81).';
COMMENT ON COLUMN system_alert.severity IS 'Alert severity level: INFO, WARNING, or CRITICAL (TL-13, OQ-81).';
COMMENT ON COLUMN system_alert.message IS 'Alert message text displayed on the dashboard.';
COMMENT ON COLUMN system_alert.entity_type IS 'Optional domain entity type associated with the alert (e.g., PLATE_BLACKLIST, VEHICLE_SESSION, PARKING_GATE).';
COMMENT ON COLUMN system_alert.entity_id IS 'Optional primary key of the associated domain entity.';
COMMENT ON COLUMN system_alert.occurred_at IS 'Timestamp when the anomaly or alert was triggered.';
COMMENT ON COLUMN system_alert.resolved_at IS 'Timestamp when the alert was acknowledged/resolved; NULL while unresolved ("cần xử lý").';
COMMENT ON COLUMN system_alert.resolved_by IS 'Optional foreign key referencing the employee who resolved the alert.';
COMMENT ON COLUMN system_alert.created_at IS 'Record creation timestamp.';

-- -----------------------------------------------------------------------------
-- 7.3. Table: news
-- Source: Sprint Plan `Tasks_Sprint_1` (SCO-03), OQ-51, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE news (
    id BIGSERIAL,
    title VARCHAR(200) NOT NULL,
    slug VARCHAR(220) NOT NULL,
    summary VARCHAR(500) NULL,
    content TEXT NOT NULL,
    thumbnail_url TEXT NULL,
    author_id BIGINT NOT NULL,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMPTZ NULL,
    view_count INTEGER NOT NULL DEFAULT 0,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_news PRIMARY KEY (id),
    CONSTRAINT fk_news_author FOREIGN KEY (author_id)
        REFERENCES employee (id) ON DELETE RESTRICT,
    CONSTRAINT fk_news_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_news_title_nonempty CHECK (btrim(title) <> ''),
    CONSTRAINT ck_news_slug_format CHECK (slug ~ '^[a-z0-9-]+$'),
    CONSTRAINT ck_news_content_nonempty CHECK (btrim(content) <> ''),
    CONSTRAINT ck_news_view_count_nonnegative CHECK (view_count >= 0),
    CONSTRAINT ck_news_row_version_positive CHECK (row_version >= 1),
    CONSTRAINT ck_news_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_news_slug_active
    ON news (slug)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_news_published
    ON news (published_at DESC)
    WHERE deleted_at IS NULL AND is_published = TRUE;

CREATE INDEX idx_news_author_id ON news (author_id) WHERE deleted_at IS NULL;

COMMENT ON TABLE news IS 'Parking facility news and announcements article table (SCO-03, OQ-51, TL-15).';
COMMENT ON COLUMN news.id IS 'Primary key identifier of the news article.';
COMMENT ON COLUMN news.title IS 'Headline title of the news article.';
COMMENT ON COLUMN news.slug IS 'URL-safe lowercase slug unique among active articles.';
COMMENT ON COLUMN news.summary IS 'Optional short summary excerpt.';
COMMENT ON COLUMN news.content IS 'Full article body content.';
COMMENT ON COLUMN news.thumbnail_url IS 'Optional cover thumbnail image URL.';
COMMENT ON COLUMN news.author_id IS 'Foreign key referencing authoring employee.';
COMMENT ON COLUMN news.is_published IS 'Publication visibility flag.';
COMMENT ON COLUMN news.published_at IS 'Publication timestamp.';
COMMENT ON COLUMN news.view_count IS 'Article read counter (must be >= 0).';
COMMENT ON COLUMN news.row_version IS 'Optimistic concurrency control version counter (TL-15, OQ-64).';
COMMENT ON COLUMN news.created_at IS 'Record creation timestamp.';
COMMENT ON COLUMN news.updated_at IS 'Record last update timestamp.';
COMMENT ON COLUMN news.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN news.deleted_by IS 'Account that performed soft deletion.';

-- -----------------------------------------------------------------------------
-- 7.4. Table: notification
-- Source: SRS 4.2 (`Bảng thông báo`), OQ-51, TL-15
-- -----------------------------------------------------------------------------
CREATE TABLE notification (
    id BIGSERIAL,
    recipient_account_id BIGINT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    notification_type VARCHAR(30) NOT NULL DEFAULT 'SYSTEM',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    CONSTRAINT pk_notification PRIMARY KEY (id),
    CONSTRAINT fk_notification_recipient FOREIGN KEY (recipient_account_id)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT fk_notification_deleted_by FOREIGN KEY (deleted_by)
        REFERENCES account (id) ON DELETE RESTRICT,
    CONSTRAINT ck_notification_title_nonempty CHECK (btrim(title) <> ''),
    CONSTRAINT ck_notification_content_nonempty CHECK (btrim(content) <> ''),
    CONSTRAINT ck_notification_type_enum CHECK (
        notification_type IN ('SYSTEM', 'TICKET_EXPIRY', 'PAYMENT', 'SECURITY')
    ),
    CONSTRAINT ck_notification_read_pair CHECK (
        (is_read = FALSE AND read_at IS NULL) OR (is_read = TRUE AND read_at IS NOT NULL)
    ),
    CONSTRAINT ck_notification_soft_delete_pair CHECK (
        (deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL)
    )
);

CREATE INDEX idx_notification_recipient_unread
    ON notification (recipient_account_id, is_read)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE notification IS 'User and broadcast notification messages table (SRS 4.2, OQ-51, TL-15).';
COMMENT ON COLUMN notification.id IS 'Primary key identifier of the notification.';
COMMENT ON COLUMN notification.recipient_account_id IS 'Optional target account; NULL indicates system-wide broadcast.';
COMMENT ON COLUMN notification.title IS 'Short notification title.';
COMMENT ON COLUMN notification.content IS 'Notification body content.';
COMMENT ON COLUMN notification.notification_type IS 'Notification category: SYSTEM, TICKET_EXPIRY, PAYMENT, or SECURITY.';
COMMENT ON COLUMN notification.is_read IS 'Whether the recipient has read the notification.';
COMMENT ON COLUMN notification.read_at IS 'Timestamp when the notification was marked read.';
COMMENT ON COLUMN notification.created_at IS 'Notification creation timestamp.';
COMMENT ON COLUMN notification.deleted_at IS 'Soft deletion timestamp (ADR-0003).';
COMMENT ON COLUMN notification.deleted_by IS 'Account that performed soft deletion.';

-- =============================================================================
-- SECTION 8: TRIGGERS & SYNCHRONIZATION FUNCTIONS (TL-03..TL-05, TL-10, TL-15)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 8.1. Trigger Function: fn_update_row_version_and_timestamp()
-- Automatically increments row_version and updates updated_at on mutable tables.
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_update_row_version_and_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.row_version := OLD.row_version + 1;
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_update_row_version_and_timestamp() IS 'Increments row_version and sets updated_at = CURRENT_TIMESTAMP on BEFORE UPDATE across mutable versioned tables (TL-15, OQ-64).';

CREATE TRIGGER trg_account_row_version
    BEFORE UPDATE ON account
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_position_row_version
    BEFORE UPDATE ON position
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_employee_row_version
    BEFORE UPDATE ON employee
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_customer_row_version
    BEFORE UPDATE ON customer
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_plate_blacklist_row_version
    BEFORE UPDATE ON plate_blacklist
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_vehicle_type_row_version
    BEFORE UPDATE ON vehicle_type
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_ticket_type_row_version
    BEFORE UPDATE ON ticket_type
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_vehicle_row_version
    BEFORE UPDATE ON vehicle
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_parking_lot_row_version
    BEFORE UPDATE ON parking_lot
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_parking_floor_row_version
    BEFORE UPDATE ON parking_floor
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_parking_zone_row_version
    BEFORE UPDATE ON parking_zone
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_parking_slot_row_version
    BEFORE UPDATE ON parking_slot
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_slot_reservation_row_version
    BEFORE UPDATE ON slot_reservation
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_ticket_row_version
    BEFORE UPDATE ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_parking_gate_row_version
    BEFORE UPDATE ON parking_gate
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_payment_row_version
    BEFORE UPDATE ON payment
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

CREATE TRIGGER trg_news_row_version
    BEFORE UPDATE ON news
    FOR EACH ROW EXECUTE FUNCTION fn_update_row_version_and_timestamp();

-- -----------------------------------------------------------------------------
-- 8.2. Trigger Function: fn_guard_parking_slot_status()
-- Enforces TL-03 manual quick-action guards on parking_slot.status:
--   - Cannot mark AVAILABLE while an open session, active reservation, or active ticket exists.
--   - OCCUPIED only follows an open session in vehicle_entry_exit_log.
--   - Cannot mark MAINTENANCE or RESERVED while an open session physically occupies the slot.
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_guard_parking_slot_status()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_has_open_session BOOLEAN;
    v_has_active_reservation BOOLEAN;
    v_has_active_ticket BOOLEAN;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status = 'OCCUPIED' THEN
            RAISE EXCEPTION 'Không thể chuyển vị trí sang trạng thái đang có xe khi không có phiên đỗ xe đang mở.'
                USING ERRCODE = 'check_violation',
                      HINT = 'OCCUPIED status requires an open session in vehicle_entry_exit_log (TL-03, OQ-81).';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM vehicle_entry_exit_log l
        WHERE l.slot_id = NEW.id
          AND l.exit_time IS NULL
    ) INTO v_has_open_session;

    IF NEW.status = 'OCCUPIED' AND NOT v_has_open_session THEN
        RAISE EXCEPTION 'Không thể chuyển vị trí sang trạng thái đang có xe khi không có phiên đỗ xe đang mở.'
            USING ERRCODE = 'check_violation',
                  HINT = 'OCCUPIED status only follows an open session (TL-03, OQ-81).';
    END IF;

    IF NEW.status IN ('MAINTENANCE', 'RESERVED') AND v_has_open_session THEN
        RAISE EXCEPTION 'Không thể chuyển trạng thái vị trí khi đang có xe đỗ trong ô.'
            USING ERRCODE = 'check_violation',
                  HINT = 'Close the open parking session before marking the slot as RESERVED or MAINTENANCE (TL-03, OQ-81).';
    END IF;

    IF NEW.status = 'AVAILABLE' THEN
        SELECT EXISTS (
            SELECT 1
            FROM slot_reservation r
            WHERE r.slot_id = NEW.id
              AND r.deleted_at IS NULL
              AND r.status = 'ACTIVE'
              AND r.reserved_until > CURRENT_TIMESTAMP
        ) INTO v_has_active_reservation;

        SELECT EXISTS (
            SELECT 1
            FROM ticket t
            WHERE t.slot_id = NEW.id
              AND t.deleted_at IS NULL
              AND t.status IN ('ACTIVE', 'RENEWING')
              AND CURRENT_TIMESTAMP >= t.effective_from
              AND CURRENT_TIMESTAMP < t.effective_to
        ) INTO v_has_active_ticket;

        IF v_has_open_session OR v_has_active_reservation OR v_has_active_ticket THEN
            RAISE EXCEPTION 'Không thể đánh dấu vị trí trống khi đang có xe đỗ hoặc đặt trước còn hiệu lực.'
                USING ERRCODE = 'check_violation',
                      HINT = 'Cannot mark slot AVAILABLE while an open session, active reservation, or active ticket exists (TL-03, OQ-81).';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_guard_parking_slot_status() IS 'Guards parking_slot.status transitions so OCCUPIED only follows an open session and AVAILABLE cannot be set while an open session, active reservation, or active ticket exists (TL-03, OQ-81).';

CREATE TRIGGER trg_guard_parking_slot_status
    BEFORE INSERT OR UPDATE OF status ON parking_slot
    FOR EACH ROW EXECUTE FUNCTION fn_guard_parking_slot_status();

-- -----------------------------------------------------------------------------
-- 8.3. Trigger Function: fn_sync_ticket_status()
-- Synchronizes ticket status with effective_to boundary (TL-10, TL-15, TL-38, OQ-63).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_sync_ticket_status()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_slot_status VARCHAR(20);
BEGIN
    IF NEW.status IN ('ACTIVE', 'RENEWING') AND NEW.effective_to <= CURRENT_TIMESTAMP THEN
        NEW.status := 'EXPIRED';
    ELSIF TG_OP = 'UPDATE'
      AND NEW.status IN ('EXPIRED', 'RENEWING')
      AND NEW.effective_to > CURRENT_TIMESTAMP
      AND OLD.effective_to <= CURRENT_TIMESTAMP THEN
        NEW.status := 'ACTIVE';
    END IF;

    IF NEW.deleted_at IS NULL AND NEW.status IN ('ACTIVE', 'RENEWING') AND NEW.effective_to > CURRENT_TIMESTAMP THEN
        SELECT s.status INTO v_slot_status
        FROM parking_slot s
        WHERE s.id = NEW.slot_id
          AND s.deleted_at IS NULL
        FOR NO KEY UPDATE;

        IF v_slot_status = 'MAINTENANCE' THEN
            RAISE EXCEPTION 'Vị trí này đang bảo trì.'
                USING ERRCODE = 'check_violation',
                      HINT = 'Cannot assign an active ticket to a slot in MAINTENANCE status (PROP-4.5.2-P01, TL-03, TL-10).';
        END IF;

        -- TL-38: Validate vehicle_type_id in slot_allowed_vehicle_type
        IF NEW.slot_id IS NOT NULL AND NEW.vehicle_id IS NOT NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM slot_allowed_vehicle_type savt
                JOIN vehicle v ON v.id = NEW.vehicle_id
                WHERE savt.slot_id = NEW.slot_id AND savt.vehicle_type_id = v.vehicle_type_id
            ) THEN
                RAISE EXCEPTION 'Loại xe không phù hợp với cấu hình cho phép của vị trí đỗ.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Vehicle type is not permitted in the assigned parking slot (PROP-SLOT-VEHICLE-TYPE-MISMATCH, TL-38).';
            END IF;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_sync_ticket_status() IS 'Automatically transitions ticket status to EXPIRED when effective_to <= CURRENT_TIMESTAMP, reactivates on renewal extension, blocks MAINTENANCE slots, and enforces slot_allowed_vehicle_type compatibility (TL-03, TL-10, TL-15, TL-38, OQ-63).';

CREATE TRIGGER trg_ticket_status_sync
    BEFORE INSERT OR UPDATE ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_sync_ticket_status();

-- -----------------------------------------------------------------------------
-- 8.4. Trigger Function: fn_guard_slot_reservation_write()
-- Guards slot_reservation writes against MAINTENANCE slots and active tickets (TL-04, TL-15, TL-38).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_guard_slot_reservation_write()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_slot_status VARCHAR(20);
    v_has_conflicting_ticket BOOLEAN;
BEGIN
    IF NEW.status = 'ACTIVE' AND NEW.reserved_until <= CURRENT_TIMESTAMP THEN
        NEW.status := 'EXPIRED';
    END IF;

    IF NEW.deleted_at IS NULL AND NEW.status = 'ACTIVE' THEN
        SELECT s.status INTO v_slot_status
        FROM parking_slot s
        WHERE s.id = NEW.slot_id
          AND s.deleted_at IS NULL
        FOR NO KEY UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Vị trí đỗ xe không tồn tại hoặc đã bị xóa.'
                USING ERRCODE = 'check_violation';
        END IF;

        IF v_slot_status = 'MAINTENANCE' THEN
            RAISE EXCEPTION 'Vị trí này đang bảo trì.'
                USING ERRCODE = 'check_violation',
                      HINT = 'Cannot reserve a slot currently in MAINTENANCE status (PROP-4.5.2-P01, TL-03, TL-04).';
        END IF;

        SELECT EXISTS (
            SELECT 1
            FROM ticket t
            WHERE t.slot_id = NEW.slot_id
              AND t.deleted_at IS NULL
              AND t.status IN ('ACTIVE', 'RENEWING')
              AND tstzrange(t.effective_from, t.effective_to, '[)') && tstzrange(NEW.reserved_from, NEW.reserved_until, '[)')
              AND (NEW.vehicle_id IS NULL OR t.vehicle_id <> NEW.vehicle_id)
        ) INTO v_has_conflicting_ticket;

        IF v_has_conflicting_ticket THEN
            RAISE EXCEPTION 'Vị trí này đã có xe đk vé và đang sử dụng'
                USING ERRCODE = 'check_violation',
                      HINT = 'Slot is already reserved by an active subscription ticket during the requested window (MSG-4.5.2-M02, TL-04).';
        END IF;

        -- TL-38: Validate vehicle_type_id in slot_allowed_vehicle_type
        IF NEW.vehicle_id IS NOT NULL AND NEW.slot_id IS NOT NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM slot_allowed_vehicle_type savt
                JOIN vehicle v ON v.id = NEW.vehicle_id
                WHERE savt.slot_id = NEW.slot_id AND savt.vehicle_type_id = v.vehicle_type_id
            ) THEN
                RAISE EXCEPTION 'Loại xe không phù hợp với cấu hình cho phép của vị trí đỗ.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Vehicle type is not permitted in the assigned parking slot (PROP-SLOT-VEHICLE-TYPE-MISMATCH, TL-38).';
            END IF;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_guard_slot_reservation_write() IS 'Prevents creating an active slot_reservation on a MAINTENANCE slot, overlapping an active subscription ticket for another vehicle, or using a disallowed vehicle type (TL-03, TL-04, TL-15, TL-38).';

CREATE TRIGGER trg_guard_slot_reservation_write
    BEFORE INSERT OR UPDATE ON slot_reservation
    FOR EACH ROW EXECUTE FUNCTION fn_guard_slot_reservation_write();

-- -----------------------------------------------------------------------------
-- 8.5. Trigger Function: fn_guard_slot_reservation_on_entry()
-- Enforces TL-05, TL-03, TL-04, TL-15, TL-17, TL-38 on vehicle_entry_exit_log:
--   1. When a session is inserted or its plate changes with vehicle_id IS NULL
--      and the normalized plate matches an active registered vehicle, sets
--      NEW.vehicle_id to that vehicle (TL-17).
--   2. When an open session (exit_time IS NULL) has vehicle_id IS NOT NULL on INSERT
--      or when license_plate/vehicle_id changes, the normalized plate must match the
--      active registered vehicle (else raises verbatim 'Lỗi dữ liệu không tìm thấy đê lưu').
--   3. Rejects check-in into MAINTENANCE slots with 'Vị trí này đang bảo trì.'.
--   4. Rejects check-in into a slot reserved by an active ticket for another vehicle/plate
--      with verbatim 'Vị trí này đã có xe đk vé và đang sử dụng'.
--   5. Rejects check-in into a slot reserved by an active slot_reservation for another vehicle/plate.
--   6. Validates vehicle_type_id against slot_allowed_vehicle_type (TL-38) and locks
--      parking_slot before modifying vehicle_entry_exit_log to guarantee uniform lock ordering.
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_guard_slot_reservation_on_entry()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_slot_status VARCHAR(20);
    v_registered_plate VARCHAR(20);
    v_norm_new_plate TEXT;
    v_reserved_ticket_vehicle_id BIGINT;
    v_reserved_ticket_plate_norm TEXT;
    v_res_vehicle_id BIGINT;
    v_res_plate_norm TEXT;
    v_has_conflicting_reservation BOOLEAN;
BEGIN
    v_norm_new_plate := fn_normalize_license_plate(NEW.license_plate);

    -- 1. Visitor plate auto-link: if vehicle_id IS NULL on INSERT or plate/vehicle_id change,
    --    and normalized plate matches an active registered vehicle, link NEW.vehicle_id (TL-17).
    IF NEW.vehicle_id IS NULL AND (
        TG_OP = 'INSERT'
        OR NEW.license_plate IS DISTINCT FROM OLD.license_plate
        OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id
    ) THEN
        SELECT v.id INTO NEW.vehicle_id
        FROM vehicle v
        WHERE v.license_plate_norm = v_norm_new_plate
          AND v.deleted_at IS NULL
        LIMIT 1;
    END IF;

    IF NEW.exit_time IS NULL THEN
        -- 2. If vehicle_id is provided on INSERT or when plate/vehicle_id changes on an open session,
        --    verify normalized plate matches the active registered vehicle (TL-05, TL-17, OQ-75).
        --    Never run when closing a session (NEW.exit_time IS NOT NULL) so soft-deleted vehicles can exit.
        IF NEW.vehicle_id IS NOT NULL AND (
            TG_OP = 'INSERT'
            OR NEW.license_plate IS DISTINCT FROM OLD.license_plate
            OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id
        ) THEN
            SELECT v.license_plate INTO v_registered_plate
            FROM vehicle v
            WHERE v.id = NEW.vehicle_id
              AND v.deleted_at IS NULL;

            IF NOT FOUND OR v_norm_new_plate <> fn_normalize_license_plate(v_registered_plate) THEN
                RAISE EXCEPTION 'Lỗi dữ liệu không tìm thấy đê lưu'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Entered license plate does not match the registered active vehicle (MSG-4.5.1-M02, TL-05, OQ-75).';
            END IF;
        END IF;

        -- 3. If slot_id is assigned, guard maintenance, active ticket reservation, and active slot_reservation
        IF NEW.slot_id IS NOT NULL THEN
            SELECT s.status INTO v_slot_status
            FROM parking_slot s
            WHERE s.id = NEW.slot_id
              AND s.deleted_at IS NULL
            FOR NO KEY UPDATE;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Vị trí đỗ xe không tồn tại hoặc đã bị xóa.'
                    USING ERRCODE = 'check_violation';
            END IF;

            IF v_slot_status = 'MAINTENANCE' THEN
                RAISE EXCEPTION 'Vị trí này đang bảo trì.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Slot is currently under maintenance and cannot be occupied (PROP-4.5.2-P01, OQ-63, OQ-67, TL-03).';
            END IF;

            -- TL-38: Validate vehicle_type_id in slot_allowed_vehicle_type
            IF NEW.vehicle_id IS NOT NULL THEN
                IF NOT EXISTS (
                    SELECT 1 FROM slot_allowed_vehicle_type savt
                    JOIN vehicle v ON v.id = NEW.vehicle_id
                    WHERE savt.slot_id = NEW.slot_id AND savt.vehicle_type_id = v.vehicle_type_id
                ) THEN
                    RAISE EXCEPTION 'Loại xe không phù hợp với cấu hình cho phép của vị trí đỗ.'
                        USING ERRCODE = 'check_violation',
                              HINT = 'Vehicle type is not permitted in the assigned parking slot (PROP-SLOT-VEHICLE-TYPE-MISMATCH, TL-38).';
                END IF;
            END IF;

            SELECT t.vehicle_id, v.license_plate_norm
            INTO v_reserved_ticket_vehicle_id, v_reserved_ticket_plate_norm
            FROM ticket t
            JOIN vehicle v ON v.id = t.vehicle_id
            WHERE t.slot_id = NEW.slot_id
              AND t.deleted_at IS NULL
              AND t.status IN ('ACTIVE', 'RENEWING')
              AND CURRENT_TIMESTAMP >= t.effective_from
              AND CURRENT_TIMESTAMP < t.effective_to
            ORDER BY t.effective_to DESC, t.id DESC
            LIMIT 1;

            IF v_reserved_ticket_vehicle_id IS NOT NULL THEN
                IF (NEW.vehicle_id IS NOT NULL AND NEW.vehicle_id <> v_reserved_ticket_vehicle_id)
                   OR (v_norm_new_plate <> v_reserved_ticket_plate_norm) THEN
                    RAISE EXCEPTION 'Vị trí này đã có xe đk vé và đang sử dụng'
                        USING ERRCODE = 'check_violation',
                              HINT = 'Slot is reserved by an active ticket for another vehicle (MSG-4.5.2-M02, TL-04, TL-05, OQ-67).';
                END IF;
            END IF;

            SELECT EXISTS (
                SELECT 1
                FROM slot_reservation r
                LEFT JOIN vehicle rv ON rv.id = r.vehicle_id
                WHERE r.slot_id = NEW.slot_id
                  AND r.deleted_at IS NULL
                  AND r.status = 'ACTIVE'
                  AND CURRENT_TIMESTAMP >= r.reserved_from
                  AND CURRENT_TIMESTAMP < r.reserved_until
                  AND (
                      (r.vehicle_id IS NOT NULL AND (NEW.vehicle_id IS DISTINCT FROM r.vehicle_id AND v_norm_new_plate IS DISTINCT FROM rv.license_plate_norm))
                      OR (r.vehicle_id IS NULL AND NEW.vehicle_id IS NOT NULL)
                  )
            ) INTO v_has_conflicting_reservation;

            IF v_has_conflicting_reservation THEN
                RAISE EXCEPTION 'Vị trí này đã được đặt trước cho phương tiện khác.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Slot has an active reservation for another vehicle (TL-04, OQ-81).';
            END IF;
        END IF;
    ELSIF COALESCE(NEW.slot_id, OLD.slot_id) IS NOT NULL THEN
        -- Acquire slot lock in BEFORE trigger on check-out as well so check-in and check-out
        -- always lock parking_slot before modifying vehicle_entry_exit_log (F5 lock-order invariant).
        PERFORM 1
        FROM parking_slot s
        WHERE s.id = COALESCE(NEW.slot_id, OLD.slot_id)
          AND s.deleted_at IS NULL
        FOR NO KEY UPDATE;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_guard_slot_reservation_on_entry() IS 'Validates barrier check-in sessions: auto-links visitor sessions matching an active registered vehicle plate (TL-17), permits unregistered visitors (vehicle_id NULL), enforces normalized plate match when vehicle_id is provided, blocks MAINTENANCE slots, validates slot_allowed_vehicle_type (TL-38), and guards slots reserved by tickets or slot_reservation (TL-03, TL-04, TL-05, TL-15, TL-17, TL-38).';

CREATE TRIGGER trg_guard_slot_reservation_on_entry
    BEFORE INSERT OR UPDATE OF slot_id, exit_time, vehicle_id, license_plate ON vehicle_entry_exit_log
    FOR EACH ROW EXECUTE FUNCTION fn_guard_slot_reservation_on_entry();

-- -----------------------------------------------------------------------------
-- 8.6. Helper Function: fn_recompute_slot_status(p_slot_id BIGINT)
-- Recomputes a slot's status from open sessions, active tickets, and active reservations.
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_recompute_slot_status(p_slot_id BIGINT)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_has_open_session BOOLEAN;
    v_has_active_reservation BOOLEAN;
    v_current_status VARCHAR(20);
BEGIN
    IF p_slot_id IS NULL THEN
        RETURN;
    END IF;

    SELECT s.status INTO v_current_status
    FROM parking_slot s
    WHERE s.id = p_slot_id
      AND s.deleted_at IS NULL
    FOR UPDATE;

    IF NOT FOUND OR v_current_status = 'MAINTENANCE' THEN
        RETURN;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM vehicle_entry_exit_log l
        WHERE l.slot_id = p_slot_id
          AND l.exit_time IS NULL
    ) INTO v_has_open_session;

    IF v_has_open_session THEN
        IF v_current_status NOT IN ('OCCUPIED', 'CHARGING') THEN
            UPDATE parking_slot
            SET status = 'OCCUPIED'
            WHERE id = p_slot_id
              AND deleted_at IS NULL;
        END IF;
        RETURN;
    END IF;

    SELECT (
        EXISTS (
            SELECT 1
            FROM ticket t
            WHERE t.slot_id = p_slot_id
              AND t.deleted_at IS NULL
              AND t.status IN ('ACTIVE', 'RENEWING')
              AND CURRENT_TIMESTAMP >= t.effective_from
              AND CURRENT_TIMESTAMP < t.effective_to
        )
        OR EXISTS (
            SELECT 1
            FROM slot_reservation r
            WHERE r.slot_id = p_slot_id
              AND r.deleted_at IS NULL
              AND r.status = 'ACTIVE'
              AND r.reserved_until > CURRENT_TIMESTAMP
        )
    ) INTO v_has_active_reservation;

    IF v_has_active_reservation THEN
        IF v_current_status <> 'RESERVED' THEN
            UPDATE parking_slot
            SET status = 'RESERVED'
            WHERE id = p_slot_id
              AND deleted_at IS NULL;
        END IF;
    ELSE
        IF v_current_status <> 'AVAILABLE' THEN
            UPDATE parking_slot
            SET status = 'AVAILABLE'
            WHERE id = p_slot_id
              AND deleted_at IS NULL;
        END IF;
    END IF;
END;
$$;

COMMENT ON FUNCTION fn_recompute_slot_status(BIGINT) IS 'Synchronizes parking_slot.status (OCCUPIED, RESERVED, AVAILABLE) from live open sessions, active tickets, and active reservations while respecting MAINTENANCE (TL-03, TL-04, TL-10, TL-15).';

-- -----------------------------------------------------------------------------
-- 8.7. Trigger Function: fn_sync_slot_status_on_traffic()
-- Synchronizes parking_slot.status after INSERT or UPDATE on vehicle_entry_exit_log.
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_sync_slot_status_on_traffic()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.slot_id IS NOT NULL AND OLD.slot_id IS DISTINCT FROM NEW.slot_id THEN
        PERFORM fn_recompute_slot_status(OLD.slot_id);
    END IF;

    IF NEW.slot_id IS NOT NULL THEN
        PERFORM fn_recompute_slot_status(NEW.slot_id);
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_sync_slot_status_on_traffic() IS 'Trigger function updating parking_slot.status upon vehicle check-in, check-out, or slot reassignment (TL-03, TL-05, TL-15, OQ-63).';

CREATE TRIGGER trg_slot_status_on_traffic
    AFTER INSERT OR UPDATE ON vehicle_entry_exit_log
    FOR EACH ROW EXECUTE FUNCTION fn_sync_slot_status_on_traffic();

-- -----------------------------------------------------------------------------
-- 8.8. Trigger Function: fn_sync_slot_status_on_ticket()
-- Synchronizes parking_slot.status and vehicle ticket preference metadata after
-- INSERT or UPDATE on ticket (TL-10, TL-15, OQ-52, OQ-63).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_sync_slot_status_on_ticket()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_latest_type_id BIGINT;
    v_latest_expires_at TIMESTAMPTZ;
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.slot_id IS DISTINCT FROM NEW.slot_id THEN
        PERFORM fn_recompute_slot_status(OLD.slot_id);
    END IF;

    PERFORM fn_recompute_slot_status(NEW.slot_id);

    SELECT t.ticket_type_id, t.effective_to
    INTO v_latest_type_id, v_latest_expires_at
    FROM ticket t
    WHERE t.vehicle_id = NEW.vehicle_id
      AND t.deleted_at IS NULL
      AND t.status IN ('ACTIVE', 'RENEWING')
      AND t.effective_to > CURRENT_TIMESTAMP
    ORDER BY t.effective_to DESC, t.id DESC
    LIMIT 1;

    UPDATE vehicle
    SET ticket_type_id = v_latest_type_id,
        ticket_expires_at = v_latest_expires_at
    WHERE id = NEW.vehicle_id
      AND (ticket_type_id IS DISTINCT FROM v_latest_type_id
           OR ticket_expires_at IS DISTINCT FROM v_latest_expires_at);

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_sync_slot_status_on_ticket() IS 'Synchronizes parking_slot.status and vehicle ticket preference metadata (ticket_type_id, ticket_expires_at) with ticket lifecycle changes (TL-10, TL-15, OQ-52, OQ-63).';

CREATE TRIGGER trg_slot_status_on_ticket
    AFTER INSERT OR UPDATE ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_sync_slot_status_on_ticket();

-- -----------------------------------------------------------------------------
-- 8.9. Trigger Function: fn_sync_slot_status_on_reservation()
-- Synchronizes parking_slot.status after INSERT or UPDATE on slot_reservation (TL-04).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_sync_slot_status_on_reservation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.slot_id IS DISTINCT FROM NEW.slot_id THEN
        PERFORM fn_recompute_slot_status(OLD.slot_id);
    END IF;

    PERFORM fn_recompute_slot_status(NEW.slot_id);

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_sync_slot_status_on_reservation() IS 'Synchronizes parking_slot.status when advance slot reservations are created, updated, cancelled, expired, or soft-deleted (TL-04, TL-15).';

CREATE TRIGGER trg_slot_status_on_reservation
    AFTER INSERT OR UPDATE ON slot_reservation
    FOR EACH ROW EXECUTE FUNCTION fn_sync_slot_status_on_reservation();

-- -----------------------------------------------------------------------------
-- 8.10. Trigger Function: fn_prevent_activity_log_mutation()
-- Enforces append-only immutability on activity_log (TL-12).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_prevent_activity_log_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'Nhật ký hoạt động là bảng chỉ ghi (append-only), không cho phép cập nhật hoặc xóa.'
        USING ERRCODE = 'check_violation',
              HINT = 'activity_log is strictly append-only (TL-12, OQ-81).';
END;
$$;

COMMENT ON FUNCTION fn_prevent_activity_log_mutation() IS 'Enforces append-only immutability on activity_log by rejecting UPDATE and DELETE operations (TL-12, OQ-81).';

CREATE TRIGGER trg_activity_log_immutable
    BEFORE UPDATE OR DELETE ON activity_log
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_activity_log_mutation();

-- -----------------------------------------------------------------------------
-- 8.11. Trigger Function: fn_guard_hard_immutable_table()
-- Enforces absolute immutability on fiscal, audit, token, and reference tables:
-- hard delete and purge are strictly prohibited under any circumstances (TL-24, ADR-0003).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_guard_hard_immutable_table()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'Bảng % là dữ liệu bất biến (chứng từ tài chính / kiểm toán an ninh / danh mục chuẩn), nghiêm cấm xóa vĩnh viễn (hard delete) dưới mọi hình thức.', TG_TABLE_NAME
        USING ERRCODE = '55000',
              HINT = 'Fiscal vouchers, audit movement records, and system reference tables can never be hard-deleted or purged (TL-24, ADR-0003).';
END;
$$;

COMMENT ON FUNCTION fn_guard_hard_immutable_table() IS 'Enforces absolute immutability on fiscal vouchers, audit movement tables, and non-purgeable system tables by rejecting all DELETE operations (TL-24, ADR-0003).';

CREATE TRIGGER trg_guard_ticket_immutable
    BEFORE DELETE ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();

CREATE TRIGGER trg_guard_ticket_renewal_immutable
    BEFORE DELETE ON ticket_renewal
    FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();

CREATE TRIGGER trg_guard_payment_immutable
    BEFORE DELETE ON payment
    FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();

CREATE TRIGGER trg_guard_entry_exit_log_immutable
    BEFORE DELETE ON vehicle_entry_exit_log
    FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();

CREATE TRIGGER trg_guard_system_alert_immutable
    BEFORE DELETE ON system_alert
    FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();

CREATE TRIGGER trg_guard_province_immutable
    BEFORE DELETE ON administrative_province
    FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();

CREATE TRIGGER trg_guard_district_immutable
    BEFORE DELETE ON administrative_district
    FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();

CREATE TRIGGER trg_guard_ward_immutable
    BEFORE DELETE ON administrative_ward
    FOR EACH ROW EXECUTE FUNCTION fn_guard_hard_immutable_table();

-- -----------------------------------------------------------------------------
-- 8.12. Trigger Function: fn_guard_slot_allowed_vehicle_type_delete()
-- Blocks removing an allowed vehicle type from a slot while active tickets,
-- open parking sessions, or active reservations of that type exist in the slot (TL-37).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_guard_slot_allowed_vehicle_type_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    -- 1. Active / renewing ticket check
    IF EXISTS (
        SELECT 1 FROM ticket t
        JOIN vehicle v ON v.id = t.vehicle_id
        WHERE t.slot_id = OLD.slot_id
          AND v.vehicle_type_id = OLD.vehicle_type_id
          AND t.deleted_at IS NULL
          AND t.status IN ('ACTIVE', 'RENEWING')
          AND t.effective_to > CURRENT_TIMESTAMP
    ) THEN
        RAISE EXCEPTION 'Không thể xóa loại xe cho phép khi vị trí đỗ đang có vé, phiên đỗ hoặc đặt chỗ thuộc loại xe này.'
            USING ERRCODE = 'check_violation',
                  HINT = 'Active ticket uses this vehicle type in this slot (PROP-DEL-SAVT-IN-USE, TL-37).';
    END IF;

    -- 2. Open session check
    IF EXISTS (
        SELECT 1 FROM vehicle_entry_exit_log l
        JOIN vehicle v ON v.id = l.vehicle_id
        WHERE l.slot_id = OLD.slot_id
          AND v.vehicle_type_id = OLD.vehicle_type_id
          AND l.exit_time IS NULL
    ) THEN
        RAISE EXCEPTION 'Không thể xóa loại xe cho phép khi vị trí đỗ đang có vé, phiên đỗ hoặc đặt chỗ thuộc loại xe này.'
            USING ERRCODE = 'check_violation',
                  HINT = 'Open session uses this vehicle type in this slot (PROP-DEL-SAVT-IN-USE, TL-37).';
    END IF;

    -- 3. Active reservation check
    IF EXISTS (
        SELECT 1 FROM slot_reservation r
        JOIN vehicle v ON v.id = r.vehicle_id
        WHERE r.slot_id = OLD.slot_id
          AND v.vehicle_type_id = OLD.vehicle_type_id
          AND r.deleted_at IS NULL
          AND r.status = 'ACTIVE'
          AND r.reserved_until > CURRENT_TIMESTAMP
    ) THEN
        RAISE EXCEPTION 'Không thể xóa loại xe cho phép khi vị trí đỗ đang có vé, phiên đỗ hoặc đặt chỗ thuộc loại xe này.'
            USING ERRCODE = 'check_violation',
                  HINT = 'Active reservation uses this vehicle type in this slot (PROP-DEL-SAVT-IN-USE, TL-37).';
    END IF;

    RETURN OLD;
END;
$$;

COMMENT ON FUNCTION fn_guard_slot_allowed_vehicle_type_delete() IS 'Blocks removing an allowed vehicle type from a slot if active tickets, open sessions, or active reservations of that type exist in the slot (TL-37).';

CREATE TRIGGER trg_guard_slot_allowed_vehicle_type_delete
    BEFORE DELETE ON slot_allowed_vehicle_type
    FOR EACH ROW EXECUTE FUNCTION fn_guard_slot_allowed_vehicle_type_delete();

-- -----------------------------------------------------------------------------
-- 8.13. Trigger Function: fn_guard_prevent_plain_delete()
-- Blocks plain client DELETE statements on purgeable business tables. Enforces
-- 4-layer protection: exact PG_CONTEXT stack frame verification, pg_proc namespace
-- anti-spoofing check, transaction nonce, and trash condition (TL-24).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_guard_prevent_plain_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_context TEXT;
    v_line2 TEXT;
    v_line3 TEXT;
    v_active_nonce TEXT;
BEGIN
    -- 1. Check Call Stack via PG_CONTEXT and verify no spoofed fn_controlled_purge exists outside public
    GET DIAGNOSTICS v_context = PG_CONTEXT;
    v_line2 := split_part(v_context, E'\n', 2);
    v_line3 := split_part(v_context, E'\n', 3);

    IF v_line2 !~ '^SQL statement "DELETE FROM [a-z_]+ WHERE .*"$'
       OR v_line3 !~ '^PL/pgSQL function (public\.)?fn_controlled_purge\([a-z ,]+\) line [0-9]+ at EXECUTE$'
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc p
           JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
           WHERE p.proname = 'fn_controlled_purge'
             AND n.nspname <> 'public'
       ) THEN
        RAISE EXCEPTION 'Thao tác xóa trực tiếp (plain DELETE) trên bảng % bị nghiêm cấm. Dữ liệu chỉ có thể được xóa mềm (soft-delete) hoặc xóa vĩnh viễn thông qua thủ tục controlled purge được ủy quyền.', TG_TABLE_NAME
            USING ERRCODE = '55000',
                  HINT = 'Use soft delete (UPDATE deleted_at) or invoke fn_controlled_purge() (TL-24).';
    END IF;

    -- 2. Check Transaction-Local Cryptographic Nonce Token
    v_active_nonce := current_setting('app.purge_internal_nonce', true);
    IF v_active_nonce IS NULL OR btrim(v_active_nonce) = '' THEN
        RAISE EXCEPTION 'Xác thực thủ tục purge không hợp lệ: thiếu mã ủy quyền phiên làm việc (missing purge auth token).'
            USING ERRCODE = '42501';
    END IF;

    -- 3. Inviolable Trash Condition: Live records (deleted_at IS NULL) CANNOT be purged under any circumstances
    IF OLD.deleted_at IS NULL THEN
        RAISE EXCEPTION 'Bản ghi (ID: %) trên bảng % đang hoạt động (deleted_at IS NULL). Nghiêm cấm purge dữ liệu chưa xóa mềm.', OLD.id, TG_TABLE_NAME
            USING ERRCODE = '55000',
                  HINT = 'Only records currently in trash (deleted_at IS NOT NULL) can be purged (TL-24).';
    END IF;

    RETURN OLD;
END;
$$;

COMMENT ON FUNCTION fn_guard_prevent_plain_delete() IS 'Blocks plain client DELETE on purgeable tables, allowing removal only via public.fn_controlled_purge() with verified call-stack frames, pg_proc namespace check, and transaction-local nonce (TL-24).';

CREATE TRIGGER trg_prevent_plain_delete_news
    BEFORE DELETE ON news
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_notification
    BEFORE DELETE ON notification
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_slot_reservation
    BEFORE DELETE ON slot_reservation
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_plate_blacklist
    BEFORE DELETE ON plate_blacklist
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_parking_slot
    BEFORE DELETE ON parking_slot
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_parking_zone
    BEFORE DELETE ON parking_zone
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_parking_floor
    BEFORE DELETE ON parking_floor
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_parking_lot
    BEFORE DELETE ON parking_lot
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_parking_gate
    BEFORE DELETE ON parking_gate
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_position
    BEFORE DELETE ON position
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_vehicle_type
    BEFORE DELETE ON vehicle_type
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_ticket_type
    BEFORE DELETE ON ticket_type
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_vehicle
    BEFORE DELETE ON vehicle
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_customer
    BEFORE DELETE ON customer
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_employee
    BEFORE DELETE ON employee
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

CREATE TRIGGER trg_prevent_plain_delete_account
    BEFORE DELETE ON account
    FOR EACH ROW EXECUTE FUNCTION fn_guard_prevent_plain_delete();

-- -----------------------------------------------------------------------------
-- 8.14. Stored Procedure: fn_controlled_purge()
-- Secure controlled purge procedure for trash records older than retention interval.
-- SECURITY DEFINER with search_path hardening, non-bypassable call-stack guard,
-- Decree 13/2023/ND-CP customer anonymization check, and activity_log audit (TL-24, TL-36, TL-40).
-- Minimal Role Model (TL-24):
--   - PUBLIC: REVOKE ALL ON FUNCTION fn_controlled_purge FROM PUBLIC.
--   - app_rw (ordinary Django application role): no EXECUTE privilege on fn_controlled_purge.
--   - db_admin / purge_operator (maintenance role): granted EXECUTE for scheduled trash cleanup.
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_controlled_purge(
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
    -- Validate retention parameter (minimum 30 days floor per TL-40, F4)
    IF p_retention IS NULL OR p_retention < INTERVAL '30 days' THEN
        RAISE EXCEPTION 'Khoảng thời gian lưu trữ tối thiểu (p_retention) không hợp lệ (yêu cầu tối thiểu 30 ngày).'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF p_target_id IS NOT NULL AND p_table_name IS NULL THEN
        RAISE EXCEPTION 'Phải chỉ định tên bảng (p_table_name) khi purge theo ID cụ thể (p_target_id).'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    v_cutoff := CURRENT_TIMESTAMP - p_retention;

    -- Check forbidden and invalid table targeting
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

    -- Iterate through target purgeable tables
    FOREACH v_tbl IN ARRAY CASE
        WHEN p_table_name IS NOT NULL THEN ARRAY[lower(btrim(p_table_name))]
        ELSE v_allowed_tables
    END
    LOOP
        -- When targeting a specific row ID, explicitly validate that the row exists, is in trash,
        -- satisfies the retention cutoff, and (for customer) is anonymized per Decree 13/2023/ND-CP.
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
            -- Count eligible trash records in batch mode
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
                -- Set internal nonce token for this transaction
                v_nonce := gen_random_uuid()::text;
                PERFORM set_config('app.purge_internal_nonce', v_nonce, true);

                v_purged := 0;
                v_skipped := 0;

                -- Perform actual purge
                IF p_target_id IS NOT NULL THEN
                    -- Single-row mode: fail explicitly if foreign key references exist (do NOT swallow error)
                    -- F1 (TL-36): If account, delete associated tokens in the same transaction
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
                    -- Batch mode: iterate through eligible trash records, skip referenced rows per TL-40
                    IF v_tbl = 'customer' THEN
                        v_sql := format('SELECT id FROM %I WHERE deleted_at IS NOT NULL AND deleted_at < $1 AND is_anonymized = TRUE', v_tbl);
                    ELSE
                        v_sql := format('SELECT id FROM %I WHERE deleted_at IS NOT NULL AND deleted_at < $1', v_tbl);
                    END IF;

                    FOR v_row_id IN EXECUTE v_sql USING v_cutoff
                    LOOP
                        BEGIN
                            -- F1 (TL-36): If account, delete associated tokens first in the same subtransaction
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

                -- Clear nonce
                PERFORM set_config('app.purge_internal_nonce', '', true);

                -- Audit log insertion matching schema (actor_account_id, action, entity_type, entity_id, message)
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

COMMENT ON FUNCTION fn_controlled_purge(VARCHAR, INTERVAL, BOOLEAN, BIGINT, BIGINT) IS 'Secure controlled purge procedure for trash records older than retention interval (>= 30 days floor, per-row FK skip in batch mode, and credential token cleanup for accounts per TL-24, TL-36, TL-40).';

REVOKE ALL ON FUNCTION fn_controlled_purge(VARCHAR, INTERVAL, BOOLEAN, BIGINT, BIGINT) FROM PUBLIC;

-- -----------------------------------------------------------------------------
-- 8.15. Trigger Function: fn_guard_soft_delete_and_restore()
-- Enforces business guards for soft-delete (DEL-01..DEL-06, TL-25, TL-39) and
-- restore (TL-23 deleted_by reset, active parent hierarchy validation per TL-26).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_guard_soft_delete_and_restore()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_count BIGINT;
    v_parent_deleted TIMESTAMPTZ;
BEGIN
    -- =========================================================================
    -- BRANCH A: SOFT-DELETE ACTION (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL)
    -- =========================================================================
    IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
        -- 1. parking_slot guards (DEL-05, TL-25)
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

        -- 2. customer guards (DEL-02, TL-25)
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

        -- 3. vehicle guards (DEL-03, TL-25)
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

        -- 4. account guards (DEL-01, OQ-10, TL-25)
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

        -- 5. employee guards (DEL-01, OQ-10, TL-25)
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

        -- 6. parking_lot, parking_floor, parking_zone hierarchy guards (DEL-06, TL-25)
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

        -- 7. ticket_type guard (DEL-06, TL-25)
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

        -- 8. position guard (DEL-06, TL-25)
        ELSIF TG_TABLE_NAME = 'position' THEN
            SELECT count(*) INTO v_count
            FROM employee
            WHERE position_id = OLD.id AND deleted_at IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Chức vụ đang được phân công cho nhân viên đang hoạt động, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Active employees assigned to this position (PROP-DEL-06-POSITION, DEL-06, TL-25).';
            END IF;

        -- 9. vehicle_type guard (DEL-06, TL-25)
        ELSIF TG_TABLE_NAME = 'vehicle_type' THEN
            SELECT count(*) INTO v_count
            FROM vehicle
            WHERE vehicle_type_id = OLD.id AND deleted_at IS NULL;
            IF v_count > 0 THEN
                RAISE EXCEPTION 'Loại xe đang được liên kết với phương tiện đang hoạt động, không được phép xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Active vehicles using this vehicle_type (PROP-DEL-06-VEHICLE-TYPE, DEL-06, TL-25).';
            END IF;

        -- 10. parking_gate guard (DEL-06, TL-25)
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

        -- 11. ticket guard (DEL-04, SRS 4.6.4, TL-25)
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

        -- 12. payment guard (TL-39)
        ELSIF TG_TABLE_NAME = 'payment' THEN
            IF OLD.status IN ('PAID', 'REFUNDED') THEN
                RAISE EXCEPTION 'Không thể xóa chứng từ thanh toán đã hoàn thành hoặc đã hoàn tiền (trạng thái PAID/REFUNDED).'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Cannot soft delete payment with status PAID or REFUNDED (PROP-DEL-PAYMENT-SETTLED, TL-39).';
            END IF;
        END IF;

        RETURN NEW;

    -- =========================================================================
    -- BRANCH B: RESTORE ACTION (OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL)
    -- =========================================================================
    ELSIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
        -- TL-23: Restoring a row clears both deleted_at and deleted_by
        NEW.deleted_by := NULL;

        -- 1. vehicle restore: parent customer, vehicle_type, and optional ticket_type must be active
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

        -- 2. parking_slot restore: parent zone must be active
        ELSIF TG_TABLE_NAME = 'parking_slot' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_zone WHERE id = NEW.zone_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục vị trí đỗ khi khu vực đỗ (zone) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent zone is deleted (TL-26).';
            END IF;

        -- 3. parking_zone restore: parent floor must be active
        ELSIF TG_TABLE_NAME = 'parking_zone' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_floor WHERE id = NEW.floor_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục khu vực đỗ khi tầng đỗ (floor) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent floor is deleted (TL-26).';
            END IF;

        -- 4. parking_floor restore: parent lot must be active
        ELSIF TG_TABLE_NAME = 'parking_floor' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_lot WHERE id = NEW.lot_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục tầng đỗ khi bãi xe (lot) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent lot is deleted (TL-26).';
            END IF;

        -- 5. parking_gate restore: parent lot must be active
        ELSIF TG_TABLE_NAME = 'parking_gate' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM parking_lot WHERE id = NEW.lot_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục cổng kiểm soát khi bãi xe (lot) đang bị xóa.'
                    USING ERRCODE = 'check_violation',
                          HINT = 'Parent lot is deleted (TL-26).';
            END IF;

        -- 6. employee restore: position and optional account must be active
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

        -- 7. customer restore: optional account must be active
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

        -- 8. slot_reservation restore: slot, optional customer, and optional vehicle must be active
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

        -- 9. ticket restore: customer, vehicle, slot, and ticket_type must be active
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

        -- 10. payment restore: optional ticket and received_by employee must be active
        ELSIF TG_TABLE_NAME = 'payment' THEN
            IF NEW.ticket_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM ticket WHERE id = NEW.ticket_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục thanh toán khi vé liên kết đang bị xóa.'
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;

        -- 11. news restore: author employee must be active
        ELSIF TG_TABLE_NAME = 'news' THEN
            SELECT deleted_at INTO v_parent_deleted
            FROM employee WHERE id = NEW.author_id;
            IF v_parent_deleted IS NOT NULL THEN
                RAISE EXCEPTION 'Không thể khôi phục bài viết khi nhân viên tác giả đang bị xóa.'
                    USING ERRCODE = 'check_violation';
            END IF;

        -- 12. notification restore: optional recipient account must be active
        ELSIF TG_TABLE_NAME = 'notification' THEN
            IF NEW.recipient_account_id IS NOT NULL THEN
                SELECT deleted_at INTO v_parent_deleted
                FROM account WHERE id = NEW.recipient_account_id;
                IF v_parent_deleted IS NOT NULL THEN
                    RAISE EXCEPTION 'Không thể khôi phục thông báo khi tài khoản người nhận đang bị xóa.'
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;
        END IF;

        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_guard_soft_delete_and_restore() IS 'Guards soft-delete and restore transitions across all 18 soft-deletable tables, enforcing parent integrity, settled payment protection, and auto-clearing deleted_by (TL-23, TL-25, TL-26, TL-39).';

CREATE TRIGGER trg_guard_soft_delete_and_restore_account
    BEFORE UPDATE OF deleted_at ON account
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_position
    BEFORE UPDATE OF deleted_at ON position
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_employee
    BEFORE UPDATE OF deleted_at ON employee
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_customer
    BEFORE UPDATE OF deleted_at ON customer
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_plate_blacklist
    BEFORE UPDATE OF deleted_at ON plate_blacklist
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_vehicle_type
    BEFORE UPDATE OF deleted_at ON vehicle_type
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_ticket_type
    BEFORE UPDATE OF deleted_at ON ticket_type
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_vehicle
    BEFORE UPDATE OF deleted_at ON vehicle
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_parking_lot
    BEFORE UPDATE OF deleted_at ON parking_lot
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_parking_floor
    BEFORE UPDATE OF deleted_at ON parking_floor
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_parking_zone
    BEFORE UPDATE OF deleted_at ON parking_zone
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_parking_slot
    BEFORE UPDATE OF deleted_at ON parking_slot
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_slot_reservation
    BEFORE UPDATE OF deleted_at ON slot_reservation
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_ticket
    BEFORE UPDATE OF deleted_at ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_parking_gate
    BEFORE UPDATE OF deleted_at ON parking_gate
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_payment
    BEFORE UPDATE OF deleted_at ON payment
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_news
    BEFORE UPDATE OF deleted_at ON news
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

CREATE TRIGGER trg_guard_soft_delete_and_restore_notification
    BEFORE UPDATE OF deleted_at ON notification
    FOR EACH ROW EXECUTE FUNCTION fn_guard_soft_delete_and_restore();

-- -----------------------------------------------------------------------------
-- 8.16. Trigger Function: fn_audit_soft_delete_and_restore()
-- Automatically writes SOFT_DELETE and RESTORE action audit records into
-- activity_log without violating its append-only immutability (TL-26).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_audit_soft_delete_and_restore()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
        INSERT INTO activity_log (actor_account_id, action, entity_type, entity_id, message)
        VALUES (
            NEW.deleted_by,
            'SOFT_DELETE',
            TG_TABLE_NAME,
            OLD.id,
            format('Xóa mềm %s (ID: %s) bởi tài khoản %s.', TG_TABLE_NAME, OLD.id, COALESCE(NEW.deleted_by::text, 'UNKNOWN'))
        );
    ELSIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
        INSERT INTO activity_log (actor_account_id, action, entity_type, entity_id, message)
        VALUES (
            NULL,
            'RESTORE',
            TG_TABLE_NAME,
            OLD.id,
            format('Khôi phục %s (ID: %s) từ thùng rác.', TG_TABLE_NAME, OLD.id)
        );
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_audit_soft_delete_and_restore() IS 'Logs SOFT_DELETE and RESTORE lifecycle transitions into activity_log (TL-26).';

CREATE TRIGGER trg_audit_soft_delete_and_restore_account
    AFTER UPDATE OF deleted_at ON account
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_position
    AFTER UPDATE OF deleted_at ON position
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_employee
    AFTER UPDATE OF deleted_at ON employee
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_customer
    AFTER UPDATE OF deleted_at ON customer
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_plate_blacklist
    AFTER UPDATE OF deleted_at ON plate_blacklist
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_vehicle_type
    AFTER UPDATE OF deleted_at ON vehicle_type
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_ticket_type
    AFTER UPDATE OF deleted_at ON ticket_type
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_vehicle
    AFTER UPDATE OF deleted_at ON vehicle
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_parking_lot
    AFTER UPDATE OF deleted_at ON parking_lot
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_parking_floor
    AFTER UPDATE OF deleted_at ON parking_floor
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_parking_zone
    AFTER UPDATE OF deleted_at ON parking_zone
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_parking_slot
    AFTER UPDATE OF deleted_at ON parking_slot
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_slot_reservation
    AFTER UPDATE OF deleted_at ON slot_reservation
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_ticket
    AFTER UPDATE OF deleted_at ON ticket
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_parking_gate
    AFTER UPDATE OF deleted_at ON parking_gate
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_payment
    AFTER UPDATE OF deleted_at ON payment
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_news
    AFTER UPDATE OF deleted_at ON news
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

CREATE TRIGGER trg_audit_soft_delete_and_restore_notification
    AFTER UPDATE OF deleted_at ON notification
    FOR EACH ROW EXECUTE FUNCTION fn_audit_soft_delete_and_restore();

-- -----------------------------------------------------------------------------
-- 8.17. Trigger Function: fn_guard_payment_update()
-- Enforces payment status transitions and settled-payment immutability (TL-42):
--   - Soft-delete guards:
--       * Mutating or transitioning a payment while in trash (deleted_at IS NOT NULL)
--         without restoring it first is strictly rejected (TL-26, TL-42).
--       * Settled payments (PAID, REFUNDED) can never be soft-deleted (PROP-DEL-PAYMENT-SETTLED, TL-39, TL-42).
--   - Status transition rules:
--       * UNPAID -> PAID or CANCELLED
--       * PAID -> REFUNDED only
--       * REFUNDED and CANCELLED are terminal statuses
--       * No transition back to UNPAID
--       * Invalid transitions raise check_violation with PROP-PAY-STATUS-TRANSITION.
--   - Settled payment immutability (OLD.status IN ('PAID', 'REFUNDED')):
--       * Modifying amount, method, paid_at, session_id, ticket_id, renewal_id,
--         or code is strictly rejected (check_violation, PROP-PAY-SETTLED-IMMUTABLE).
--       * Updating notes is permitted (harmless metadata for reconciliation).
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_guard_payment_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    -- 0. Disallow mutating or transitioning a soft-deleted payment without restoring it first
    IF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NOT NULL THEN
        RAISE EXCEPTION 'Không thể cập nhật hoặc chuyển trạng thái chứng từ thanh toán đang trong thùng rác.'
            USING ERRCODE = 'check_violation',
                  HINT = 'Cannot mutate a soft-deleted payment without restoring it first (TL-26, TL-42).';
    END IF;

    -- Disallow setting status to PAID or REFUNDED on a soft-deleted payment
    IF NEW.status IN ('PAID', 'REFUNDED') AND (NEW.deleted_at IS NOT NULL OR OLD.deleted_at IS NOT NULL) THEN
        RAISE EXCEPTION 'Chứng từ thanh toán đã thanh toán hoặc hoàn tiền không được phép ở trạng thái xóa mềm.'
            USING ERRCODE = 'check_violation',
                  HINT = 'Settled payment cannot be soft-deleted (PROP-DEL-PAYMENT-SETTLED, TL-39, TL-42).';
    END IF;

    -- 1. Check status transition validity if status is changing
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        -- No transition back to UNPAID is ever permitted
        IF NEW.status = 'UNPAID' THEN
            RAISE EXCEPTION 'Không thể chuyển trạng thái thanh toán ngược về chưa thanh toán (UNPAID).'
                USING ERRCODE = 'check_violation',
                      HINT = format('Invalid payment status transition from %s to %s (PROP-PAY-STATUS-TRANSITION, TL-42).', OLD.status, NEW.status);
        END IF;

        -- Transitions from UNPAID: only PAID or CANCELLED allowed
        IF OLD.status = 'UNPAID' THEN
            IF NEW.status NOT IN ('PAID', 'CANCELLED') THEN
                RAISE EXCEPTION 'Chuyển đổi trạng thái thanh toán không hợp lệ từ % sang %.', OLD.status, NEW.status
                    USING ERRCODE = 'check_violation',
                          HINT = format('Invalid payment status transition from %s to %s (PROP-PAY-STATUS-TRANSITION, TL-42).', OLD.status, NEW.status);
            END IF;

        -- Transitions from PAID: only REFUNDED allowed
        ELSIF OLD.status = 'PAID' THEN
            IF NEW.status <> 'REFUNDED' THEN
                RAISE EXCEPTION 'Chuyển đổi trạng thái thanh toán không hợp lệ từ % sang %.', OLD.status, NEW.status
                    USING ERRCODE = 'check_violation',
                          HINT = format('Invalid payment status transition from %s to %s (PROP-PAY-STATUS-TRANSITION, TL-42).', OLD.status, NEW.status);
            END IF;

        -- Terminal statuses: CANCELLED and REFUNDED cannot transition to anything
        ELSIF OLD.status IN ('CANCELLED', 'REFUNDED') THEN
            RAISE EXCEPTION 'Chứng từ thanh toán ở trạng thái kết thúc (%) không thể chuyển sang trạng thái khác (%).', OLD.status, NEW.status
                USING ERRCODE = 'check_violation',
                      HINT = format('Invalid payment status transition from %s to %s (PROP-PAY-STATUS-TRANSITION, TL-42).', OLD.status, NEW.status);
        END IF;
    END IF;

    -- 2. Enforce settled/refunded payment immutability
    IF OLD.status IN ('PAID', 'REFUNDED') THEN
        IF OLD.amount IS DISTINCT FROM NEW.amount
           OR OLD.method IS DISTINCT FROM NEW.method
           OR OLD.paid_at IS DISTINCT FROM NEW.paid_at
           OR OLD.session_id IS DISTINCT FROM NEW.session_id
           OR OLD.ticket_id IS DISTINCT FROM NEW.ticket_id
           OR OLD.renewal_id IS DISTINCT FROM NEW.renewal_id
           OR OLD.code IS DISTINCT FROM NEW.code THEN
            RAISE EXCEPTION 'Không thể chỉnh sửa thông tin tài chính hoặc liên kết của chứng từ thanh toán đã thanh toán hoặc đã hoàn tiền.'
                USING ERRCODE = 'check_violation',
                      HINT = 'Settled payment financial and link columns are immutable (PROP-PAY-SETTLED-IMMUTABLE, TL-42).';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_guard_payment_update() IS 'Guards payment status transitions and enforces settled-payment immutability (TL-42).';

CREATE TRIGGER trg_guard_payment_update
    BEFORE UPDATE ON payment
    FOR EACH ROW EXECUTE FUNCTION fn_guard_payment_update();

-- Harden privilege boundary: revoke direct PUBLIC EXECUTE on all 15 internal trigger functions
REVOKE ALL ON FUNCTION
    fn_update_row_version_and_timestamp(),
    fn_guard_parking_slot_status(),
    fn_sync_ticket_status(),
    fn_guard_slot_reservation_write(),
    fn_guard_slot_reservation_on_entry(),
    fn_sync_slot_status_on_traffic(),
    fn_sync_slot_status_on_ticket(),
    fn_sync_slot_status_on_reservation(),
    fn_prevent_activity_log_mutation(),
    fn_guard_hard_immutable_table(),
    fn_guard_slot_allowed_vehicle_type_delete(),
    fn_guard_prevent_plain_delete(),
    fn_guard_soft_delete_and_restore(),
    fn_audit_soft_delete_and_restore(),
    fn_guard_payment_update()
FROM PUBLIC;

-- =============================================================================
-- SECTION 9: ANALYTICAL & DASHBOARD VIEWS (TL-14, TL-15, TL-27, SRS 4.7)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 9.1. View: v_slot_occupancy_by_floor
-- Source: Frontend `Trang chủ — Smart Mobility.png` ("Tình trạng chỗ đỗ theo khu vực") &
--         `Sơ đồ bãi đậu xe — Smart Mobility.png` (6 KPI cards + floor/zone tabs), TL-14, TL-27
-- -----------------------------------------------------------------------------
CREATE VIEW v_slot_occupancy_by_floor AS
WITH open_sessions AS (
    SELECT DISTINCT l.slot_id
    FROM vehicle_entry_exit_log l
    LEFT JOIN vehicle v ON v.id = l.vehicle_id
    LEFT JOIN customer c ON c.id = v.customer_id
    WHERE l.exit_time IS NULL
      AND l.slot_id IS NOT NULL
      AND (l.vehicle_id IS NULL OR (v.deleted_at IS NULL AND c.deleted_at IS NULL))
),
active_tickets AS (
    SELECT DISTINCT t.slot_id
    FROM ticket t
    JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
    JOIN customer c ON c.id = t.customer_id AND c.deleted_at IS NULL
    WHERE t.deleted_at IS NULL
      AND t.status IN ('ACTIVE', 'RENEWING')
      AND CURRENT_TIMESTAMP >= t.effective_from
      AND CURRENT_TIMESTAMP < t.effective_to
),
active_reservations AS (
    SELECT DISTINCT r.slot_id
    FROM slot_reservation r
    LEFT JOIN vehicle v ON v.id = r.vehicle_id
    LEFT JOIN customer c ON c.id = r.customer_id
    WHERE r.deleted_at IS NULL
      AND r.status = 'ACTIVE'
      AND CURRENT_TIMESTAMP < r.reserved_until
      AND (r.vehicle_id IS NULL OR v.deleted_at IS NULL)
      AND (r.customer_id IS NULL OR c.deleted_at IS NULL)
),
slot_states AS (
    SELECT
        pl.id AS lot_id,
        pl.code AS lot_code,
        pl.name AS lot_name,
        pf.id AS floor_id,
        pf.code AS floor_code,
        pf.name AS floor_name,
        pz.id AS zone_id,
        pz.code AS zone_code,
        pz.name AS zone_name,
        ps.id AS slot_id,
        ps.status AS stored_status,
        CASE
            WHEN ps.status = 'MAINTENANCE' THEN 'MAINTENANCE'
            WHEN ps.status = 'CHARGING' THEN 'CHARGING'
            WHEN os.slot_id IS NOT NULL OR ps.status = 'OCCUPIED' THEN 'OCCUPIED'
            WHEN at.slot_id IS NOT NULL OR ar.slot_id IS NOT NULL OR ps.status = 'RESERVED' THEN 'RESERVED'
            ELSE 'AVAILABLE'
        END AS effective_status
    FROM parking_lot pl
    JOIN parking_floor pf ON pf.lot_id = pl.id AND pf.deleted_at IS NULL
    JOIN parking_zone pz ON pz.floor_id = pf.id AND pz.deleted_at IS NULL
    LEFT JOIN parking_slot ps ON ps.zone_id = pz.id AND ps.deleted_at IS NULL
    LEFT JOIN open_sessions os ON os.slot_id = ps.id
    LEFT JOIN active_tickets at ON at.slot_id = ps.id
    LEFT JOIN active_reservations ar ON ar.slot_id = ps.id
    WHERE pl.deleted_at IS NULL
)
SELECT
    lot_id,
    lot_code,
    lot_name,
    floor_id,
    floor_code,
    floor_name,
    zone_id,
    zone_code,
    zone_name,
    COUNT(slot_id)::BIGINT AS total_slots,
    COUNT(slot_id) FILTER (WHERE effective_status <> 'MAINTENANCE')::BIGINT AS operational_slots,
    COUNT(slot_id) FILTER (WHERE effective_status = 'AVAILABLE')::BIGINT AS available_slots,
    COUNT(slot_id) FILTER (WHERE effective_status = 'OCCUPIED')::BIGINT AS occupied_slots,
    COUNT(slot_id) FILTER (WHERE effective_status = 'RESERVED')::BIGINT AS reserved_slots,
    COUNT(slot_id) FILTER (WHERE effective_status = 'CHARGING')::BIGINT AS charging_slots,
    COUNT(slot_id) FILTER (WHERE effective_status = 'MAINTENANCE')::BIGINT AS maintenance_slots,
    COALESCE(
        ROUND(
            (COUNT(slot_id) FILTER (WHERE effective_status IN ('OCCUPIED', 'RESERVED', 'CHARGING'))::NUMERIC
             / NULLIF(COUNT(slot_id) FILTER (WHERE effective_status <> 'MAINTENANCE'), 0)) * 100,
            2
        ),
        0.00
    ) AS occupancy_rate_pct
FROM slot_states
GROUP BY lot_id, lot_code, lot_name, floor_id, floor_code, floor_name, zone_id, zone_code, zone_name;

COMMENT ON VIEW v_slot_occupancy_by_floor IS 'Floor- and zone-level parking slot capacity and real-time occupancy breakdown for Trang chủ and Sơ đồ bãi đậu xe (TL-02, TL-03, TL-14, TL-27, OQ-63).';

-- -----------------------------------------------------------------------------
-- 9.2. View: v_revenue_today_by_method
-- Source: Frontend `Trang chủ — Smart Mobility.png` ("Doanh thu hôm nay",
--         "Tiền mặt: 18% | QR: 82%"), TL-07, TL-14, TL-27
-- -----------------------------------------------------------------------------
CREATE VIEW v_revenue_today_by_method AS
WITH today_payments AS (
    SELECT
        p.method,
        p.amount
    FROM payment p
    LEFT JOIN ticket t ON t.id = p.ticket_id
    LEFT JOIN ticket_renewal tr ON tr.id = p.renewal_id
    LEFT JOIN ticket tr_t ON tr_t.id = tr.ticket_id
    WHERE p.deleted_at IS NULL
      AND p.status = 'PAID'
      AND COALESCE(p.paid_at, p.created_at)::DATE = CURRENT_DATE
      AND (p.ticket_id IS NULL OR t.deleted_at IS NULL)
      AND (p.renewal_id IS NULL OR tr_t.deleted_at IS NULL)
)
SELECT
    CURRENT_DATE AS revenue_date,
    COALESCE(SUM(amount), 0.00)::NUMERIC(12, 2) AS total_revenue,
    COALESCE(SUM(amount) FILTER (WHERE method = 'CASH'), 0.00)::NUMERIC(12, 2) AS cash_revenue,
    COALESCE(SUM(amount) FILTER (WHERE method = 'VIETQR'), 0.00)::NUMERIC(12, 2) AS vietqr_revenue,
    COALESCE(
        ROUND((SUM(amount) FILTER (WHERE method = 'CASH') / NULLIF(SUM(amount), 0)) * 100, 2),
        0.00
    ) AS cash_pct,
    COALESCE(
        ROUND((SUM(amount) FILTER (WHERE method = 'VIETQR') / NULLIF(SUM(amount), 0)) * 100, 2),
        0.00
    ) AS vietqr_pct
FROM today_payments;

COMMENT ON VIEW v_revenue_today_by_method IS 'Dashboard KPI card view computing today revenue split by CASH ("Tiền mặt") and VIETQR ("QR") on Trang chủ — Smart Mobility.png (TL-07, TL-14, TL-27).';

-- -----------------------------------------------------------------------------
-- 9.3. View: v_traffic_by_hour
-- Source: Frontend `Trang chủ — Smart Mobility.png` ("Lưu lượng xe vào / ra theo giờ"), TL-05, TL-14, TL-27
-- -----------------------------------------------------------------------------
CREATE VIEW v_traffic_by_hour AS
WITH active_sessions AS (
    SELECT
        l.entry_time,
        l.exit_time
    FROM vehicle_entry_exit_log l
    LEFT JOIN parking_slot ps ON ps.id = l.slot_id
    LEFT JOIN vehicle v ON v.id = l.vehicle_id
    LEFT JOIN customer c ON c.id = v.customer_id
    LEFT JOIN ticket t ON t.id = l.ticket_id
    WHERE (l.slot_id IS NULL OR ps.deleted_at IS NULL)
      AND (l.vehicle_id IS NULL OR (v.deleted_at IS NULL AND c.deleted_at IS NULL))
      AND (l.ticket_id IS NULL OR t.deleted_at IS NULL)
),
entry_hours AS (
    SELECT
        DATE_TRUNC('hour', entry_time) AS traffic_hour,
        COUNT(*)::BIGINT AS entry_count
    FROM active_sessions
    GROUP BY DATE_TRUNC('hour', entry_time)
),
exit_hours AS (
    SELECT
        DATE_TRUNC('hour', exit_time) AS traffic_hour,
        COUNT(*)::BIGINT AS exit_count
    FROM active_sessions
    WHERE exit_time IS NOT NULL
    GROUP BY DATE_TRUNC('hour', exit_time)
)
SELECT
    COALESCE(en.traffic_hour, ex.traffic_hour) AS traffic_hour,
    COALESCE(en.entry_count, 0)::BIGINT AS entry_count,
    COALESCE(ex.exit_count, 0)::BIGINT AS exit_count,
    (COALESCE(en.entry_count, 0) + COALESCE(ex.exit_count, 0))::BIGINT AS total_movements
FROM entry_hours en
FULL OUTER JOIN exit_hours ex ON en.traffic_hour = ex.traffic_hour
ORDER BY traffic_hour DESC;

COMMENT ON VIEW v_traffic_by_hour IS 'Hourly vehicle entry and exit traffic aggregation for the "Lưu lượng xe vào / ra theo giờ" chart on Trang chủ — Smart Mobility.png (TL-05, TL-14, TL-27).';

-- -----------------------------------------------------------------------------
-- 9.4. View: v_ai_recognition_stats
-- Source: Frontend `Trang chủ — Smart Mobility.png` ("Tỷ lệ nhận diện AI: 98.4%",
--         "Nhập thủ công: 1.6%", "4 Cổng quét tự động"), TL-05, TL-06, TL-14, TL-27
-- -----------------------------------------------------------------------------
CREATE VIEW v_ai_recognition_stats AS
SELECT
    COUNT(*)::BIGINT AS total_sessions,
    COUNT(*) FILTER (WHERE l.recognition_source = 'AI')::BIGINT AS ai_sessions,
    COUNT(*) FILTER (WHERE l.recognition_source = 'MANUAL')::BIGINT AS manual_sessions,
    COALESCE(
        ROUND((COUNT(*) FILTER (WHERE l.recognition_source = 'AI')::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2),
        0.00
    ) AS ai_recognition_rate_pct,
    COALESCE(
        ROUND((COUNT(*) FILTER (WHERE l.recognition_source = 'MANUAL')::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2),
        0.00
    ) AS manual_rate_pct,
    COALESCE(ROUND(AVG(l.ai_confidence), 2), 0.00) AS avg_ai_confidence,
    (
        SELECT COUNT(*)::BIGINT
        FROM parking_gate g
        JOIN parking_lot pl ON pl.id = g.lot_id AND pl.deleted_at IS NULL
        WHERE g.deleted_at IS NULL
          AND g.is_active = TRUE
          AND g.is_auto_scan = TRUE
    ) AS active_auto_scan_gates
FROM vehicle_entry_exit_log l
LEFT JOIN parking_slot ps ON ps.id = l.slot_id
LEFT JOIN vehicle v ON v.id = l.vehicle_id
LEFT JOIN customer c ON c.id = v.customer_id
LEFT JOIN ticket t ON t.id = l.ticket_id
WHERE (l.slot_id IS NULL OR ps.deleted_at IS NULL)
  AND (l.vehicle_id IS NULL OR (v.deleted_at IS NULL AND c.deleted_at IS NULL))
  AND (l.ticket_id IS NULL OR t.deleted_at IS NULL);

COMMENT ON VIEW v_ai_recognition_stats IS 'Dashboard KPI view computing AI vs manual plate recognition rates, average AI confidence, and active auto-scan gate count for Trang chủ — Smart Mobility.png (TL-05, TL-06, TL-14, TL-27).';

-- -----------------------------------------------------------------------------
-- 9.5. View: v_customer_status_summary
-- Source: Frontend `Khách hàng — Smart Mobility.png` ("Tổng khách hàng",
--         "Đang hoạt động", "Tạm ngừng", "Blacklist/Tạm khoá"), TL-08, TL-14, TL-27
-- -----------------------------------------------------------------------------
CREATE VIEW v_customer_status_summary AS
SELECT
    COUNT(*)::BIGINT AS total_customers,
    COUNT(*) FILTER (WHERE status = 'ACTIVE')::BIGINT AS active_customers,
    COUNT(*) FILTER (WHERE status = 'SUSPENDED')::BIGINT AS suspended_customers,
    COUNT(*) FILTER (WHERE status = 'BLACKLISTED')::BIGINT AS blacklisted_customers
FROM customer
WHERE deleted_at IS NULL;

COMMENT ON VIEW v_customer_status_summary IS 'Customer KPI summary cards by status (ACTIVE, SUSPENDED, BLACKLISTED) for Khách hàng — Smart Mobility.png (TL-08, TL-14, TL-27).';

-- -----------------------------------------------------------------------------
-- 9.6. View: v_revenue_statistics
-- Source: SRS 4.7.1 & TL-14, TL-27 (Monthly, quarterly, and annual revenue across active tickets and renewals)
-- -----------------------------------------------------------------------------
CREATE VIEW v_revenue_statistics AS
WITH financial_events AS (
    SELECT
        EXTRACT(YEAR FROM t.created_at)::INTEGER AS report_year,
        EXTRACT(QUARTER FROM t.created_at)::INTEGER AS report_quarter,
        EXTRACT(MONTH FROM t.created_at)::INTEGER AS report_month,
        1::BIGINT AS ticket_cnt,
        0::BIGINT AS renewal_cnt,
        t.price AS amount
    FROM ticket t
    JOIN customer c ON c.id = t.customer_id AND c.deleted_at IS NULL
    JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
    JOIN parking_slot ps ON ps.id = t.slot_id AND ps.deleted_at IS NULL
    WHERE t.deleted_at IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM payment p
          WHERE p.ticket_id = t.id
            AND p.deleted_at IS NOT NULL
      )
    UNION ALL
    SELECT
        EXTRACT(YEAR FROM tr.created_at)::INTEGER AS report_year,
        EXTRACT(QUARTER FROM tr.created_at)::INTEGER AS report_quarter,
        EXTRACT(MONTH FROM tr.created_at)::INTEGER AS report_month,
        0::BIGINT AS ticket_cnt,
        1::BIGINT AS renewal_cnt,
        tr.additional_price AS amount
    FROM ticket_renewal tr
    JOIN ticket t ON t.id = tr.ticket_id AND t.deleted_at IS NULL
    JOIN customer c ON c.id = t.customer_id AND c.deleted_at IS NULL
    JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
    JOIN parking_slot ps ON ps.id = t.slot_id AND ps.deleted_at IS NULL
    WHERE NOT EXISTS (
        SELECT 1
        FROM payment p
        WHERE p.renewal_id = tr.id
          AND p.deleted_at IS NOT NULL
    )
)
SELECT
    report_year,
    report_quarter,
    report_month,
    SUM(ticket_cnt)::BIGINT AS total_tickets_sold,
    SUM(renewal_cnt)::BIGINT AS total_renewals,
    COALESCE(SUM(amount), 0.00)::NUMERIC(12, 2) AS total_revenue
FROM financial_events
GROUP BY report_year, report_quarter, report_month
ORDER BY report_year DESC, report_quarter DESC, report_month DESC;

COMMENT ON VIEW v_revenue_statistics IS 'Monthly, quarterly, and annual financial revenue aggregation across active ticket sales and renewals excluding soft-deleted records (SRS 4.7.1, OQ-11, TL-14, TL-27).';

-- -----------------------------------------------------------------------------
-- 9.7. View: v_vehicle_traffic_daily
-- Source: SRS 4.7.2 & `Trang chủ — Smart Mobility.png` ("Lượt xe vào / ra hôm nay"), TL-14, TL-27
-- -----------------------------------------------------------------------------
CREATE VIEW v_vehicle_traffic_daily AS
WITH active_sessions AS (
    SELECT
        l.entry_time,
        l.exit_time
    FROM vehicle_entry_exit_log l
    LEFT JOIN parking_slot ps ON ps.id = l.slot_id
    LEFT JOIN vehicle v ON v.id = l.vehicle_id
    LEFT JOIN customer c ON c.id = v.customer_id
    LEFT JOIN ticket t ON t.id = l.ticket_id
    WHERE (l.slot_id IS NULL OR ps.deleted_at IS NULL)
      AND (l.vehicle_id IS NULL OR (v.deleted_at IS NULL AND c.deleted_at IS NULL))
      AND (l.ticket_id IS NULL OR t.deleted_at IS NULL)
),
entry_daily AS (
    SELECT
        entry_time::DATE AS traffic_date,
        COUNT(*)::BIGINT AS total_entries,
        COUNT(*) FILTER (WHERE exit_time IS NULL)::BIGINT AS currently_parked_count
    FROM active_sessions
    GROUP BY entry_time::DATE
),
exit_daily AS (
    SELECT
        exit_time::DATE AS traffic_date,
        COUNT(*)::BIGINT AS total_exits
    FROM active_sessions
    WHERE exit_time IS NOT NULL
    GROUP BY exit_time::DATE
)
SELECT
    COALESCE(en.traffic_date, ex.traffic_date) AS traffic_date,
    COALESCE(en.total_entries, 0)::BIGINT AS total_entries,
    COALESCE(ex.total_exits, 0)::BIGINT AS total_exits,
    COALESCE(en.currently_parked_count, 0)::BIGINT AS currently_parked_count
FROM entry_daily en
FULL OUTER JOIN exit_daily ex ON en.traffic_date = ex.traffic_date
ORDER BY traffic_date DESC;

COMMENT ON VIEW v_vehicle_traffic_daily IS 'Daily vehicle entry, exit, and currently parked counts for Trang chủ and SRS 4.7.2 excluding soft-deleted entities (TL-14, TL-27).';

-- -----------------------------------------------------------------------------
-- 9.8. View: v_customer_vehicle_summary
-- Source: SRS 4.7.2 & `Khách hàng` / `Quản lý xe`, TL-14, TL-27
-- -----------------------------------------------------------------------------
CREATE VIEW v_customer_vehicle_summary AS
WITH vehicle_counts AS (
    SELECT
        v.customer_id,
        COUNT(*)::BIGINT AS total_registered_vehicles
    FROM vehicle v
    JOIN vehicle_type vt ON vt.id = v.vehicle_type_id AND vt.deleted_at IS NULL
    WHERE v.deleted_at IS NULL
    GROUP BY v.customer_id
),
ticket_counts AS (
    SELECT
        t.customer_id,
        COUNT(*)::BIGINT AS total_active_tickets
    FROM ticket t
    JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
    JOIN parking_slot ps ON ps.id = t.slot_id AND ps.deleted_at IS NULL
    WHERE t.deleted_at IS NULL
      AND t.status IN ('ACTIVE', 'RENEWING')
      AND t.effective_to > CURRENT_TIMESTAMP
    GROUP BY t.customer_id
)
SELECT
    c.id AS customer_id,
    c.code AS customer_code,
    c.full_name,
    c.phone,
    c.status AS customer_status,
    COALESCE(vc.total_registered_vehicles, 0)::BIGINT AS total_registered_vehicles,
    COALESCE(tc.total_active_tickets, 0)::BIGINT AS total_active_tickets
FROM customer c
LEFT JOIN vehicle_counts vc ON vc.customer_id = c.id
LEFT JOIN ticket_counts tc ON tc.customer_id = c.id
WHERE c.deleted_at IS NULL;

COMMENT ON VIEW v_customer_vehicle_summary IS 'Per-customer summary of registered vehicles and active tickets using pre-aggregated CTEs to prevent Cartesian duplication (SRS 4.7.2, TL-14, TL-27).';

-- =============================================================================
-- SECTION 10: DATE-RANGE STATISTICAL FUNCTIONS (SRS 4.7.1 & 4.7.2, TL-14, TL-27, OQ-37)
-- =============================================================================

CREATE FUNCTION fn_stat_vehicles_by_day(p_from_date DATE, p_to_date DATE)
RETURNS TABLE (
    traffic_date DATE,
    total_entries BIGINT,
    total_exits BIGINT,
    distinct_vehicles BIGINT
)
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    IF p_from_date IS NULL OR p_to_date IS NULL OR p_from_date > p_to_date THEN
        RAISE EXCEPTION 'Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN QUERY
    SELECT
        l.entry_time::DATE AS traffic_date,
        COUNT(*)::BIGINT AS total_entries,
        COUNT(*) FILTER (WHERE l.exit_time IS NOT NULL AND l.exit_time::DATE BETWEEN p_from_date AND p_to_date)::BIGINT AS total_exits,
        COUNT(DISTINCT l.license_plate_norm)::BIGINT AS distinct_vehicles
    FROM vehicle_entry_exit_log l
    LEFT JOIN parking_slot ps ON ps.id = l.slot_id
    LEFT JOIN vehicle v ON v.id = l.vehicle_id
    LEFT JOIN customer c ON c.id = v.customer_id
    LEFT JOIN ticket t ON t.id = l.ticket_id
    WHERE l.entry_time::DATE BETWEEN p_from_date AND p_to_date
      AND (l.slot_id IS NULL OR ps.deleted_at IS NULL)
      AND (l.vehicle_id IS NULL OR (v.deleted_at IS NULL AND c.deleted_at IS NULL))
      AND (l.ticket_id IS NULL OR t.deleted_at IS NULL)
    GROUP BY l.entry_time::DATE
    ORDER BY traffic_date DESC;
END;
$$;

COMMENT ON FUNCTION fn_stat_vehicles_by_day(DATE, DATE) IS 'Date-range vehicle traffic statistics grouped by day excluding soft-deleted entities (SRS 4.7.2, OQ-37, TL-14, TL-27).';

CREATE FUNCTION fn_stat_vehicles_by_floor(p_from_date DATE, p_to_date DATE)
RETURNS TABLE (
    floor_id BIGINT,
    floor_code VARCHAR(20),
    floor_name VARCHAR(50),
    entry_count BIGINT,
    distinct_vehicle_count BIGINT,
    ticket_count BIGINT
)
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    IF p_from_date IS NULL OR p_to_date IS NULL OR p_from_date > p_to_date THEN
        RAISE EXCEPTION 'Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN QUERY
    WITH floor_logs AS (
        SELECT
            pf.id AS f_id,
            COUNT(l.id)::BIGINT AS entry_cnt,
            COUNT(DISTINCT l.license_plate_norm)::BIGINT AS distinct_veh_cnt
        FROM parking_floor pf
        JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.deleted_at IS NULL
        JOIN parking_zone pz ON pz.floor_id = pf.id AND pz.deleted_at IS NULL
        JOIN parking_slot ps ON ps.zone_id = pz.id AND ps.deleted_at IS NULL
        LEFT JOIN vehicle_entry_exit_log l
            ON l.slot_id = ps.id
           AND l.entry_time::DATE BETWEEN p_from_date AND p_to_date
           AND NOT EXISTS (
               SELECT 1
               FROM vehicle v
               LEFT JOIN customer c ON c.id = v.customer_id
               WHERE v.id = l.vehicle_id
                 AND (v.deleted_at IS NOT NULL OR c.deleted_at IS NOT NULL)
           )
           AND NOT EXISTS (
               SELECT 1
               FROM ticket lt
               WHERE lt.id = l.ticket_id
                 AND lt.deleted_at IS NOT NULL
           )
        WHERE pf.deleted_at IS NULL
        GROUP BY pf.id
    ),
    floor_tickets AS (
        SELECT
            pf.id AS f_id,
            COUNT(t.id)::BIGINT AS ticket_cnt
        FROM parking_floor pf
        JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.deleted_at IS NULL
        JOIN parking_zone pz ON pz.floor_id = pf.id AND pz.deleted_at IS NULL
        JOIN parking_slot ps ON ps.zone_id = pz.id AND ps.deleted_at IS NULL
        LEFT JOIN ticket t
            ON t.slot_id = ps.id
           AND t.deleted_at IS NULL
           AND t.created_at::DATE BETWEEN p_from_date AND p_to_date
           AND EXISTS (
               SELECT 1
               FROM vehicle v
               JOIN customer c ON c.id = v.customer_id AND c.deleted_at IS NULL
               WHERE v.id = t.vehicle_id
                 AND v.deleted_at IS NULL
           )
        WHERE pf.deleted_at IS NULL
        GROUP BY pf.id
    )
    SELECT
        pf.id AS floor_id,
        pf.code AS floor_code,
        pf.name AS floor_name,
        COALESCE(fl.entry_cnt, 0)::BIGINT AS entry_count,
        COALESCE(fl.distinct_veh_cnt, 0)::BIGINT AS distinct_vehicle_count,
        COALESCE(ft.ticket_cnt, 0)::BIGINT AS ticket_count
    FROM parking_floor pf
    JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.deleted_at IS NULL
    LEFT JOIN floor_logs fl ON fl.f_id = pf.id
    LEFT JOIN floor_tickets ft ON ft.f_id = pf.id
    WHERE pf.deleted_at IS NULL
    ORDER BY pf.sort_order ASC, pf.id ASC;
END;
$$;

COMMENT ON FUNCTION fn_stat_vehicles_by_floor(DATE, DATE) IS 'Date-range vehicle session and ticket allocation statistics grouped by parking_floor excluding soft-deleted records (SRS 4.7.2, TL-02, TL-14, TL-27, OQ-37).';

CREATE FUNCTION fn_stat_vehicles_by_customer(p_from_date DATE, p_to_date DATE)
RETURNS TABLE (
    customer_id BIGINT,
    customer_code VARCHAR(10),
    customer_name VARCHAR(45),
    registered_vehicle_count BIGINT,
    period_ticket_count BIGINT
)
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    IF p_from_date IS NULL OR p_to_date IS NULL OR p_from_date > p_to_date THEN
        RAISE EXCEPTION 'Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN QUERY
    WITH cust_vehicles AS (
        SELECT
            v.customer_id AS c_id,
            COUNT(v.id)::BIGINT AS veh_cnt
        FROM vehicle v
        JOIN vehicle_type vt ON vt.id = v.vehicle_type_id AND vt.deleted_at IS NULL
        WHERE v.deleted_at IS NULL
        GROUP BY v.customer_id
    ),
    cust_tickets AS (
        SELECT
            t.customer_id AS c_id,
            COUNT(t.id)::BIGINT AS tkt_cnt
        FROM ticket t
        JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
        JOIN parking_slot ps ON ps.id = t.slot_id AND ps.deleted_at IS NULL
        WHERE t.deleted_at IS NULL
          AND t.created_at::DATE BETWEEN p_from_date AND p_to_date
        GROUP BY t.customer_id
    )
    SELECT
        c.id AS customer_id,
        c.code AS customer_code,
        c.full_name AS customer_name,
        COALESCE(cv.veh_cnt, 0)::BIGINT AS registered_vehicle_count,
        COALESCE(ct.tkt_cnt, 0)::BIGINT AS period_ticket_count
    FROM customer c
    LEFT JOIN cust_vehicles cv ON cv.c_id = c.id
    LEFT JOIN cust_tickets ct ON ct.c_id = c.id
    WHERE c.deleted_at IS NULL
    ORDER BY period_ticket_count DESC, c.id ASC;
END;
$$;

COMMENT ON FUNCTION fn_stat_vehicles_by_customer(DATE, DATE) IS 'Date-range customer vehicle registration and ticket purchase statistics excluding soft-deleted records (SRS 4.7.2, OQ-37, TL-14, TL-27).';

CREATE FUNCTION fn_stat_revenue_by_period(p_from_date DATE, p_to_date DATE)
RETURNS TABLE (
    report_year INTEGER,
    report_quarter INTEGER,
    report_month INTEGER,
    total_tickets_sold BIGINT,
    total_renewals BIGINT,
    total_revenue NUMERIC(12, 2)
)
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    IF p_from_date IS NULL OR p_to_date IS NULL OR p_from_date > p_to_date THEN
        RAISE EXCEPTION 'Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN QUERY
    WITH period_events AS (
        SELECT
            EXTRACT(YEAR FROM t.created_at)::INTEGER AS r_year,
            EXTRACT(QUARTER FROM t.created_at)::INTEGER AS r_quarter,
            EXTRACT(MONTH FROM t.created_at)::INTEGER AS r_month,
            1::BIGINT AS t_cnt,
            0::BIGINT AS r_cnt,
            t.price AS amt
        FROM ticket t
        JOIN customer c ON c.id = t.customer_id AND c.deleted_at IS NULL
        JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
        JOIN parking_slot ps ON ps.id = t.slot_id AND ps.deleted_at IS NULL
        WHERE t.deleted_at IS NULL
          AND t.created_at::DATE BETWEEN p_from_date AND p_to_date
          AND NOT EXISTS (
              SELECT 1
              FROM payment p
              WHERE p.ticket_id = t.id
                AND p.deleted_at IS NOT NULL
          )
        UNION ALL
        SELECT
            EXTRACT(YEAR FROM tr.created_at)::INTEGER AS r_year,
            EXTRACT(QUARTER FROM tr.created_at)::INTEGER AS r_quarter,
            EXTRACT(MONTH FROM tr.created_at)::INTEGER AS r_month,
            0::BIGINT AS t_cnt,
            1::BIGINT AS r_cnt,
            tr.additional_price AS amt
        FROM ticket_renewal tr
        JOIN ticket t ON t.id = tr.ticket_id AND t.deleted_at IS NULL
        JOIN customer c ON c.id = t.customer_id AND c.deleted_at IS NULL
        JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
        JOIN parking_slot ps ON ps.id = t.slot_id AND ps.deleted_at IS NULL
        WHERE tr.created_at::DATE BETWEEN p_from_date AND p_to_date
          AND NOT EXISTS (
              SELECT 1
              FROM payment p
              WHERE p.renewal_id = tr.id
                AND p.deleted_at IS NOT NULL
          )
    )
    SELECT
        pe.r_year AS report_year,
        pe.r_quarter AS report_quarter,
        pe.r_month AS report_month,
        SUM(pe.t_cnt)::BIGINT AS total_tickets_sold,
        SUM(pe.r_cnt)::BIGINT AS total_renewals,
        COALESCE(SUM(pe.amt), 0.00)::NUMERIC(12, 2) AS total_revenue
    FROM period_events pe
    GROUP BY pe.r_year, pe.r_quarter, pe.r_month
    ORDER BY report_year DESC, report_quarter DESC, report_month DESC;
END;
$$;

COMMENT ON FUNCTION fn_stat_revenue_by_period(DATE, DATE) IS 'Date-range financial revenue aggregation across tickets and renewals excluding soft-deleted records (SRS 4.7.1, OQ-37, TL-14, TL-27).';

COMMIT;
