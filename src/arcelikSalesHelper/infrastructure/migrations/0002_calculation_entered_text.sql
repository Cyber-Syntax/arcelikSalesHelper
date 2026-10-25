-- 0002: keep the text exactly as typed next to the normalized values.
-- ADD COLUMN does not fire the immutability triggers (they fire on row UPDATE/DELETE only).
ALTER TABLE calculation_lines ADD COLUMN entered_json TEXT NOT NULL DEFAULT '{}';