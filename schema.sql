-- ============================================================================
-- VOLUME RECONCILIATION & MATERIAL TRACEABILITY SYSTEM
-- DDL Schema – PostgreSQL dialect
-- Dùng để tham khảo và cài đặt trực tiếp trên PostgreSQL production
-- For reference and direct PostgreSQL production setup
-- ============================================================================

-- Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── ENUMS ──────────────────────────────────────────────────────────────────

CREATE TYPE user_role AS ENUM ('admin', 'factory_staff', 'qc', 'auditor');
CREATE TYPE cert_standard AS ENUM ('GRS', 'GOTS', 'RCS', 'OCS');
CREATE TYPE tc_in_status  AS ENUM ('active', 'partially_used', 'fully_used', 'expired', 'cancelled');
CREATE TYPE tc_out_status AS ENUM ('draft', 'issued', 'cancelled');
CREATE TYPE batch_status  AS ENUM ('planned', 'in_progress', 'completed', 'cancelled');
CREATE TYPE stage_type    AS ENUM ('cutting', 'sewing', 'packing');
CREATE TYPE balance_status AS ENUM ('PASS', 'WARNING', 'FAIL', 'PENDING');
CREATE TYPE qty_type      AS ENUM ('certified', 'non_certified');

CREATE TYPE tx_type AS ENUM (
    'tc_in_receipt',
    'issue_cutting', 'cutting_output',  'cutting_loss',
    'issue_sewing',  'sewing_output',   'sewing_loss',
    'issue_packing', 'packing_output',  'packing_loss',
    'tc_out_sale', 'normal_sale', 'adjustment', 'return_in', 'return_out'
);

-- ─── USERS ──────────────────────────────────────────────────────────────────

CREATE TABLE users (
    id               SERIAL PRIMARY KEY,
    username         VARCHAR(50)  UNIQUE NOT NULL,
    email            VARCHAR(100) UNIQUE NOT NULL,
    hashed_password  VARCHAR(255) NOT NULL,
    full_name        VARCHAR(100),
    role             user_role    NOT NULL DEFAULT 'factory_staff',
    is_active        BOOLEAN      DEFAULT TRUE,
    last_login       TIMESTAMP,
    created_at       TIMESTAMP    DEFAULT NOW(),
    updated_at       TIMESTAMP    DEFAULT NOW()
);

-- ─── SUPPLIERS ──────────────────────────────────────────────────────────────

CREATE TABLE suppliers (
    id                      SERIAL PRIMARY KEY,
    code                    VARCHAR(50)  UNIQUE NOT NULL,
    name                    VARCHAR(200) NOT NULL,
    address                 TEXT,
    country                 VARCHAR(100),
    certification_body      VARCHAR(100),        -- Control Union, Bureau Veritas, etc.
    scope_cert_number       VARCHAR(100),        -- Scope Certificate number
    scope_cert_expiry       DATE,
    certification_standards VARCHAR(200),        -- comma-separated: 'GRS,GOTS'
    contact_name            VARCHAR(100),
    contact_email           VARCHAR(100),
    contact_phone           VARCHAR(50),
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMP DEFAULT NOW()
);

-- ─── BUYERS ─────────────────────────────────────────────────────────────────

CREATE TABLE buyers (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(50)  UNIQUE NOT NULL,
    name          VARCHAR(200) NOT NULL,
    address       TEXT,
    country       VARCHAR(100),
    contact_name  VARCHAR(100),
    contact_email VARCHAR(100),
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- ─── MATERIAL CATEGORIES ────────────────────────────────────────────────────

CREATE TABLE material_categories (
    id                     SERIAL PRIMARY KEY,
    code                   VARCHAR(50)   UNIQUE NOT NULL,
    name                   VARCHAR(100)  NOT NULL,
    fiber_type             VARCHAR(100),             -- Polyester, Cotton, Nylon
    certification_standard cert_standard,
    min_recycled_content   NUMERIC(5,2),             -- Minimum % by standard
    description            TEXT
);

-- ─── MATERIALS ──────────────────────────────────────────────────────────────

CREATE TABLE materials (
    id               SERIAL PRIMARY KEY,
    code             VARCHAR(100) UNIQUE NOT NULL,
    name             VARCHAR(200) NOT NULL,
    category_id      INTEGER REFERENCES material_categories(id),
    unit             VARCHAR(20) DEFAULT 'kg',
    recycled_content NUMERIC(5,2),        -- Actual % recycled content
    color            VARCHAR(50),
    composition      VARCHAR(200),        -- e.g., '100% rPET'
    description      TEXT,
    is_active        BOOLEAN DEFAULT TRUE
);

CREATE INDEX ix_material_code     ON materials(code);
CREATE INDEX ix_material_category ON materials(category_id);

-- ─── INCOMING TRANSACTION CERTIFICATES (In TC) ──────────────────────────────

CREATE TABLE tc_in (
    id                     SERIAL PRIMARY KEY,
    tc_number              VARCHAR(100) UNIQUE NOT NULL,
    issue_date             DATE NOT NULL,
    expiry_date            DATE,

    -- Parties
    supplier_id            INTEGER NOT NULL REFERENCES suppliers(id),

    -- Material
    material_id            INTEGER NOT NULL REFERENCES materials(id),
    material_description   TEXT,                    -- As stated on TC

    -- Certification
    certification_standard VARCHAR(20) NOT NULL,    -- GRS / GOTS / RCS / OCS
    certified_quantity     NUMERIC(15,3) NOT NULL,
    quantity_remaining     NUMERIC(15,3) NOT NULL,  -- Updated as allocations are made

    -- Financials
    unit_price             NUMERIC(15,4),
    currency               VARCHAR(10) DEFAULT 'USD',
    total_amount           NUMERIC(15,2),

    -- Reference documents
    invoice_number         VARCHAR(100),
    po_number              VARCHAR(100),
    shipment_date          DATE,
    received_date          DATE,
    certification_body     VARCHAR(100),

    status                 tc_in_status DEFAULT 'active',
    notes                  TEXT,
    created_by             INTEGER REFERENCES users(id),
    created_at             TIMESTAMP DEFAULT NOW(),
    updated_at             TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_tc_in_qty_positive       CHECK (certified_quantity > 0),
    CONSTRAINT chk_tc_in_remaining_nonneg   CHECK (quantity_remaining >= 0),
    CONSTRAINT chk_tc_in_remaining_lte      CHECK (quantity_remaining <= certified_quantity)
);

CREATE INDEX ix_tc_in_number   ON tc_in(tc_number);
CREATE INDEX ix_tc_in_supplier ON tc_in(supplier_id);
CREATE INDEX ix_tc_in_date     ON tc_in(issue_date);
CREATE INDEX ix_tc_in_material ON tc_in(material_id);

-- ─── OUTGOING TRANSACTION CERTIFICATES (Out TC) ─────────────────────────────

CREATE TABLE tc_out (
    id                     SERIAL PRIMARY KEY,
    tc_number              VARCHAR(100) UNIQUE NOT NULL,
    issue_date             DATE NOT NULL,

    -- Buyer
    buyer_id               INTEGER NOT NULL REFERENCES buyers(id),

    -- Product
    product_name           VARCHAR(200) NOT NULL,
    product_code           VARCHAR(100),
    style_number           VARCHAR(100),

    -- Certification
    certification_standard VARCHAR(20) NOT NULL,
    certified_quantity     NUMERIC(15,3) NOT NULL,

    -- Financials
    unit_price             NUMERIC(15,4),
    currency               VARCHAR(10) DEFAULT 'USD',
    total_amount           NUMERIC(15,2),

    -- Reference documents
    invoice_number         VARCHAR(100),
    po_number              VARCHAR(100),
    shipment_date          DATE,
    certification_body     VARCHAR(100),

    status                 tc_out_status DEFAULT 'draft',
    notes                  TEXT,
    created_by             INTEGER REFERENCES users(id),
    created_at             TIMESTAMP DEFAULT NOW(),
    updated_at             TIMESTAMP DEFAULT NOW(),

    CONSTRAINT chk_tc_out_qty_positive CHECK (certified_quantity > 0)
);

CREATE INDEX ix_tc_out_number ON tc_out(tc_number);
CREATE INDEX ix_tc_out_buyer  ON tc_out(buyer_id);
CREATE INDEX ix_tc_out_date   ON tc_out(issue_date);

-- ─── TC LINKAGE (In TC ↔ Out TC many-to-many) ───────────────────────────────

CREATE TABLE tc_linkage (
    id                 SERIAL PRIMARY KEY,
    tc_in_id           INTEGER NOT NULL REFERENCES tc_in(id)  ON DELETE CASCADE,
    tc_out_id          INTEGER NOT NULL REFERENCES tc_out(id) ON DELETE CASCADE,
    allocated_quantity NUMERIC(15,3) NOT NULL,    -- kg allocated from this In TC
    allocation_pct     NUMERIC(8,4),              -- % of In TC's certified_quantity
    notes              TEXT,
    created_by         INTEGER REFERENCES users(id),
    created_at         TIMESTAMP DEFAULT NOW(),

    CONSTRAINT uq_tc_linkage         UNIQUE (tc_in_id, tc_out_id),
    CONSTRAINT chk_linkage_qty_pos   CHECK  (allocated_quantity > 0)
);

-- ─── PRODUCTION BATCHES ─────────────────────────────────────────────────────

CREATE TABLE production_batches (
    id                 SERIAL PRIMARY KEY,
    batch_number       VARCHAR(100) UNIQUE NOT NULL,

    -- Product info
    product_name       VARCHAR(200) NOT NULL,
    product_code       VARCHAR(100),
    style_number       VARCHAR(100),
    order_number       VARCHAR(100),

    -- Source TC
    tc_in_id           INTEGER REFERENCES tc_in(id),

    -- Quantities
    planned_input_qty  NUMERIC(15,3),    -- kg planned input
    actual_input_qty   NUMERIC(15,3),    -- kg actual issued to cutting
    planned_output_qty NUMERIC(15,3),    -- kg planned output
    actual_output_qty  NUMERIC(15,3),    -- kg actual finished goods

    start_date         DATE NOT NULL,
    end_date           DATE,

    status             batch_status DEFAULT 'planned',
    notes              TEXT,
    created_by         INTEGER REFERENCES users(id),
    created_at         TIMESTAMP DEFAULT NOW(),
    updated_at         TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ix_batch_number ON production_batches(batch_number);
CREATE INDEX ix_batch_tc_in  ON production_batches(tc_in_id);
CREATE INDEX ix_batch_status ON production_batches(status);

-- ─── PRODUCTION STAGES ──────────────────────────────────────────────────────

CREATE TABLE production_stages (
    id              SERIAL PRIMARY KEY,
    batch_id        INTEGER NOT NULL REFERENCES production_batches(id) ON DELETE CASCADE,
    stage           stage_type NOT NULL,           -- cutting / sewing / packing
    stage_date      DATE NOT NULL,

    input_quantity  NUMERIC(15,3) NOT NULL,        -- kg going IN to this stage
    output_quantity NUMERIC(15,3) NOT NULL,        -- kg coming OUT of this stage
    -- loss_quantity = input - output  (computed in application layer)
    -- loss_pct      = loss / input * 100

    loss_reason     TEXT,
    operator_name   VARCHAR(100),
    verified_by     VARCHAR(100),
    notes           TEXT,
    created_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW(),

    CONSTRAINT uq_batch_stage          UNIQUE  (batch_id, stage),     -- 1 stage per batch
    CONSTRAINT chk_stage_input_pos     CHECK   (input_quantity > 0),
    CONSTRAINT chk_stage_output_nonneg CHECK   (output_quantity >= 0),
    CONSTRAINT chk_stage_output_lte    CHECK   (output_quantity <= input_quantity)
);

-- ─── STOCK TRANSACTIONS ─────────────────────────────────────────────────────
-- Sổ kho bất biến – ghi EVERY movement / Immutable stock ledger

CREATE TABLE stock_transactions (
    id               SERIAL PRIMARY KEY,
    transaction_date DATE         NOT NULL,
    transaction_type tx_type      NOT NULL,

    -- Reference keys (nullable – depends on transaction type)
    tc_in_id         INTEGER REFERENCES tc_in(id),
    tc_out_id        INTEGER REFERENCES tc_out(id),
    batch_id         INTEGER REFERENCES production_batches(id),
    stage_id         INTEGER REFERENCES production_stages(id),

    material_id      INTEGER NOT NULL REFERENCES materials(id),

    -- Sign convention: positive = stock IN, negative = stock OUT
    quantity         NUMERIC(15,3) NOT NULL,
    quantity_type    qty_type DEFAULT 'certified',
    running_balance  NUMERIC(15,3),               -- Balance AFTER this transaction

    reference_number VARCHAR(100),
    notes            TEXT,
    created_by       INTEGER REFERENCES users(id),
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ix_stock_date     ON stock_transactions(transaction_date);
CREATE INDEX ix_stock_material ON stock_transactions(material_id);
CREATE INDEX ix_stock_tc_in    ON stock_transactions(tc_in_id);
CREATE INDEX ix_stock_tc_out   ON stock_transactions(tc_out_id);
CREATE INDEX ix_stock_batch    ON stock_transactions(batch_id);

-- ─── MASS BALANCE PERIODS ───────────────────────────────────────────────────

CREATE TABLE mass_balance_periods (
    id                     SERIAL PRIMARY KEY,
    period_start           DATE NOT NULL,
    period_end             DATE NOT NULL,
    certification_standard VARCHAR(20) NOT NULL,
    material_id            INTEGER REFERENCES materials(id),

    -- Opening balance
    opening_stock_raw      NUMERIC(15,3) DEFAULT 0,
    opening_stock_wip      NUMERIC(15,3) DEFAULT 0,
    opening_stock_fg       NUMERIC(15,3) DEFAULT 0,

    -- Inputs
    certified_purchased    NUMERIC(15,3) DEFAULT 0,
    number_of_tc_in        INTEGER       DEFAULT 0,

    -- Production
    issued_to_production   NUMERIC(15,3) DEFAULT 0,

    cutting_input          NUMERIC(15,3) DEFAULT 0,
    cutting_output         NUMERIC(15,3) DEFAULT 0,
    cutting_loss           NUMERIC(15,3) DEFAULT 0,
    cutting_loss_pct       NUMERIC(8,4)  DEFAULT 0,

    sewing_input           NUMERIC(15,3) DEFAULT 0,
    sewing_output          NUMERIC(15,3) DEFAULT 0,
    sewing_loss            NUMERIC(15,3) DEFAULT 0,
    sewing_loss_pct        NUMERIC(8,4)  DEFAULT 0,

    packing_input          NUMERIC(15,3) DEFAULT 0,
    packing_output         NUMERIC(15,3) DEFAULT 0,
    packing_loss           NUMERIC(15,3) DEFAULT 0,
    packing_loss_pct       NUMERIC(8,4)  DEFAULT 0,

    total_process_loss     NUMERIC(15,3) DEFAULT 0,
    total_loss_pct         NUMERIC(8,4)  DEFAULT 0,

    -- Outputs
    certified_produced     NUMERIC(15,3) DEFAULT 0,
    certified_sold         NUMERIC(15,3) DEFAULT 0,
    number_of_tc_out       INTEGER       DEFAULT 0,

    -- Closing balance
    closing_stock_raw      NUMERIC(15,3) DEFAULT 0,
    closing_stock_fg       NUMERIC(15,3) DEFAULT 0,
    closing_stock_total    NUMERIC(15,3) DEFAULT 0,

    -- Reconciliation
    theoretical_closing    NUMERIC(15,3) DEFAULT 0,
    difference             NUMERIC(15,3) DEFAULT 0,    -- + surplus / – deficit
    difference_pct         NUMERIC(8,4)  DEFAULT 0,
    balance_status         balance_status DEFAULT 'PENDING',

    -- Audit metadata
    calculated_at          TIMESTAMP,
    calculated_by          INTEGER REFERENCES users(id),
    approved_by            INTEGER REFERENCES users(id),
    approved_at            TIMESTAMP,
    notes                  TEXT,

    created_at             TIMESTAMP DEFAULT NOW(),
    updated_at             TIMESTAMP DEFAULT NOW(),

    CONSTRAINT uq_mb_period     UNIQUE (period_start, period_end, certification_standard, material_id),
    CONSTRAINT chk_mb_period    CHECK  (period_end >= period_start)
);

-- ─── AUDIT LOG ──────────────────────────────────────────────────────────────

CREATE TABLE audit_logs (
    id             SERIAL PRIMARY KEY,
    table_name     VARCHAR(100) NOT NULL,
    record_id      INTEGER,
    action         VARCHAR(20)  NOT NULL,    -- INSERT / UPDATE / DELETE
    old_values     JSONB,
    new_values     JSONB,
    changed_fields TEXT,                    -- JSON array as text
    user_id        INTEGER REFERENCES users(id),
    ip_address     VARCHAR(45),
    user_agent     TEXT,
    created_at     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ix_audit_table_record ON audit_logs(table_name, record_id);
CREATE INDEX ix_audit_user         ON audit_logs(user_id);
CREATE INDEX ix_audit_created_at   ON audit_logs(created_at);

-- ─── SYSTEM SETTINGS ────────────────────────────────────────────────────────

CREATE TABLE system_settings (
    id          SERIAL PRIMARY KEY,
    key         VARCHAR(100) UNIQUE NOT NULL,
    value       TEXT,
    description TEXT,
    updated_by  INTEGER REFERENCES users(id),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- ─── DEFAULT SETTINGS ───────────────────────────────────────────────────────

INSERT INTO system_settings (key, value, description) VALUES
    ('mb_pass_threshold_pct',    '0.50', 'Mass Balance difference % that qualifies as PASS (default 0.5%)'),
    ('mb_warning_threshold_pct', '2.00', 'Mass Balance difference % that qualifies as WARNING (default 2.0%)'),
    ('cutting_loss_alert_pct',   '15.0', 'Cutting loss % that triggers alert (default 15%)'),
    ('sewing_loss_alert_pct',    '10.0', 'Sewing loss % that triggers alert (default 10%)'),
    ('packing_loss_alert_pct',   '5.0',  'Packing loss % that triggers alert (default 5%)'),
    ('company_name',             '',     'Factory name for reports'),
    ('cert_body',                '',     'Certification body name (e.g., Control Union)'),
    ('cert_number',              '',     'Factory Scope Certificate number'),
    ('currency',                 'USD',  'Default currency'),
    ('fiscal_year_start_month',  '1',    'Month that the fiscal year starts (1=Jan)');
