-- 0001_initial
-- Do NOT add BEGIN / COMMIT / PRAGMA user_version here: the migration runner
-- wraps each file in one transaction and sets user_version itself.

CREATE TABLE app_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

INSERT INTO app_metadata (key, value)
VALUES ('db_created_at', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

CREATE TABLE products (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL CHECK (length(trim(name)) > 0),
    name_key          TEXT NOT NULL CHECK (length(name_key) > 0),
    regular_price     TEXT NOT NULL,   -- str(Decimal), never REAL
    website_price     TEXT NOT NULL,
    default_gift_name TEXT,
    notes             TEXT,
    archived          INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

-- Only ACTIVE products must have unique names; archived ones may collide.
CREATE UNIQUE INDEX ux_products_name_active ON products (name_key) WHERE archived = 0;

CREATE TABLE pricing_history (
    id            INTEGER PRIMARY KEY,
    product_id    INTEGER NOT NULL REFERENCES products (id),
    regular_price TEXT NOT NULL,
    website_price TEXT NOT NULL,
    changed_at    TEXT NOT NULL
);
CREATE INDEX ix_pricing_history_product ON pricing_history (product_id, id);

CREATE TABLE calculation_snapshots (
    id                 INTEGER PRIMARY KEY,
    created_at         TEXT NOT NULL,
    app_version        TEXT NOT NULL,
    schema_version     INTEGER NOT NULL,
    totals_json        TEXT NOT NULL,
    confirmation_state TEXT,
    warnings_json      TEXT NOT NULL
);

CREATE TABLE calculation_lines (
    id                     INTEGER PRIMARY KEY,
    snapshot_id            INTEGER NOT NULL
                           REFERENCES calculation_snapshots (id) ON DELETE RESTRICT,
    line_index             INTEGER NOT NULL,
    product_id             INTEGER,        -- informational only, deliberately NOT a foreign key
    product_name           TEXT NOT NULL,
    quantity               INTEGER NOT NULL,
    regular_price          TEXT NOT NULL,
    website_price          TEXT NOT NULL,
    coupon                 TEXT NOT NULL,
    effective_website_unit TEXT NOT NULL,
    gift_selected          INTEGER NOT NULL CHECK (gift_selected IN (0, 1)),
    gift_name              TEXT,
    manager_value_entered  TEXT,
    manager_mode           TEXT,
    manager_line_total     TEXT,
    manager_unit           TEXT,
    result_json            TEXT NOT NULL,
    UNIQUE (snapshot_id, line_index)
);

-- Immutability: history can only ever be appended to.
CREATE TRIGGER trg_calculation_snapshots_no_update
BEFORE UPDATE ON calculation_snapshots
BEGIN SELECT RAISE(ABORT, 'calculation_snapshots is immutable'); END;

CREATE TRIGGER trg_calculation_snapshots_no_delete
BEFORE DELETE ON calculation_snapshots
BEGIN SELECT RAISE(ABORT, 'calculation_snapshots is immutable'); END;

CREATE TRIGGER trg_calculation_lines_no_update
BEFORE UPDATE ON calculation_lines
BEGIN SELECT RAISE(ABORT, 'calculation_lines is immutable'); END;

CREATE TRIGGER trg_calculation_lines_no_delete
BEFORE DELETE ON calculation_lines
BEGIN SELECT RAISE(ABORT, 'calculation_lines is immutable'); END;

CREATE TRIGGER trg_pricing_history_no_update
BEFORE UPDATE ON pricing_history
BEGIN SELECT RAISE(ABORT, 'pricing_history is immutable'); END;

CREATE TRIGGER trg_pricing_history_no_delete
BEFORE DELETE ON pricing_history
BEGIN SELECT RAISE(ABORT, 'pricing_history is immutable'); END;