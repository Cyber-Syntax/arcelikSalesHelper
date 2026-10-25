-- 0003: manually counted quantity per product, with an append-only change log.
-- NULL quantity = never counted (not the same as 0).
ALTER TABLE products ADD COLUMN quantity INTEGER CHECK (quantity IS NULL OR quantity >= 0);
ALTER TABLE products ADD COLUMN quantity_updated_at TEXT;

CREATE TABLE stock_history (
    id                INTEGER PRIMARY KEY,
    product_id        INTEGER NOT NULL REFERENCES products (id),
    quantity          INTEGER NOT NULL CHECK (quantity >= 0),
    previous_quantity INTEGER,
    source            TEXT NOT NULL CHECK (source IN ('manual', 'csv')),
    note              TEXT,
    changed_at        TEXT NOT NULL
);
CREATE INDEX ix_stock_history_product ON stock_history (product_id, id);

CREATE TRIGGER trg_stock_history_no_update
BEFORE UPDATE ON stock_history
BEGIN SELECT RAISE(ABORT, 'stock_history is immutable'); END;

CREATE TRIGGER trg_stock_history_no_delete
BEFORE DELETE ON stock_history
BEGIN SELECT RAISE(ABORT, 'stock_history is immutable'); END;