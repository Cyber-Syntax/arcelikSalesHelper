-- Confirmed product deletion removes its catalog audit rows only when no
-- calculation snapshot refers to it. Calculation history remains protected.
DROP TRIGGER IF EXISTS trg_pricing_history_no_delete;
DROP TRIGGER IF EXISTS trg_stock_history_no_delete;
