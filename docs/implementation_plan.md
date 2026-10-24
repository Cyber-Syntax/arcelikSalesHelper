# Technical Implementation Plan (agent-facing)

Source: PRD v0.3. This file is the working contract. Do not start a milestone until the previous one passes its exit checks.

## 0. Locked decisions

| Topic | Decision |
| --- | --- |
| Python | 3.11+; `pyproject.toml`; deps: `PySide6`, `platformdirs`; dev: `pytest`, `pytest-qt`, `ruff`, `mypy` |
| Money type | `decimal.Decimal` only. Never `float`. |
| Rounding | **None in calculations.** Rounding happens only in `format_try()` (display), using `ROUND_HALF_UP` to 2 places. |
| Decimal context | Module-level `localcontext` with `prec=60`, used for all arithmetic, so divisions such as `line / qty` stay effectively exact. |
| Storage of money | SQLite `TEXT` holding `str(Decimal)`, never REAL. Reload with `Decimal(s)`. |
| UI language | English |
| CSV | Comma-delimited, UTF-8 (accept BOM via `utf-8-sig`), columns exactly `product_name,regular_price,website_discounted_price` |
| CSV conflict key | `product_name.strip().casefold()` |
| Packaging | PyInstaller (one-folder), Windows and Linux |
| Style | Pure functions in `domain/`, with no imports from `PySide6`, `sqlite3`, or `infrastructure`. Frozen dataclasses for models. |

**Design rule for exactness:** line totals are authoritative. In manager total-line mode, `manager_line_total` is the entered value, and `manager_unit_value = line / qty` is a derived display value. It never feeds back into totals or the POS formula. Display of a non-terminating unit value is rounded only by the formatter.

## 1. Repository layout

Follow PRD section 9 exactly, plus:

```
pyproject.toml
README.md
src/arcelikSalesHelper/__init__.py
src/arcelikSalesHelper/paths.py            # platformdirs wrapper
src/arcelikSalesHelper/infrastructure/migrations/0001_initial.sql
tests/conftest.py                   # tmp_path DB fixtures, Qt app fixture
```

## 2. Milestone 1: Domain core (pure, no I/O)

**`domain/money.py`**

- `parse_money(text: str) -> Result[Decimal, str]` (no exceptions for bad user input).
- Accepted: `54.999,00`, `54999`, `54999.00`, `54.999`, `1.234.567,89`.
- Disambiguation rules, implemented and tested explicitly:
  - Contains both `.` and `,`: the last separator is the decimal mark; the other is the thousands separator.
  - Only `,`: decimal mark (at most one, 1 to 2+ digits after it).
  - Only `.`:
    - If it appears more than once, or is followed by exactly 3 digits with a ≤3-digit leading group, treat it as a thousands separator (`54.999` = 54999). Otherwise treat it as a decimal (`54999.00`, `12.5`).
    - Open ambiguity: `1.234` could be either. Choose thousands (Turkish convention) and surface a UI hint. Document this in the test names.
- Reject: empty, negative sign, letters, `NaN`/`Infinity`, multiple decimal marks, misplaced groups (`1.23.456`), scientific notation.
- Optional trailing `TL`/`TRY` is stripped; whitespace is trimmed.

**`domain/formatting.py`**

- `format_try(d: Decimal) -> str` gives `"54.999,00 TL"`. Quantize to 0.01 with `ROUND_HALF_UP`, group by `.`, decimal `,`.
- No locale dependency, so Windows and Linux behave identically.
- Also `format_decimal_exact(d)` for snapshot/debug views (the "exact value" tooltip).

**`domain/models.py`** (frozen dataclasses)

- `ManagerMode(Enum): UNIT, LINE`
- `LineInput`: `product_name, quantity:int, regular_price, website_price, coupon, gift_selected:bool, gift_name:str|None, manager_value:Decimal|None, manager_mode:ManagerMode|None, product_id:int|None`
- `LineResult`: `regular_total, website_total, coupon_total, effective_website_unit, effective_website_total, ten_pct_base, ten_pct_discount_unit, ten_pct_unit, ten_pct_total, manager_unit|None, manager_line_total|None, pos_amount|None, warnings: tuple[Warning,...]`
- `TransactionResult`: `lines`, `totals` (regular, website, effective website, 10% scenario, manager, POS; each `None` if any line lacks the input, and the UI must say "n/a: missing manager value on line N" rather than a partial sum)
- `Warning`: `code, message, line_index`

**`domain/validation.py`**

- `validate_line(LineInput) -> tuple[Error,...]`: quantity ≥ 1 integer; prices ≥ 0; `0 ≤ coupon ≤ website_price`; manager mode required iff manager value is present; manager value ≥ 0.
- Soft warning (not an error): manager line total exceeds the applicable website total (`effective_website_total` for no-gift lines, and `website_total` for gift lines). Never alter the value.

**`domain/pricing.py`** (all pure)

- `effective_website_unit(website, coupon)`
- `ten_percent(base) -> (discount, price)` using `base * Decimal("0.10")`
- `discount_base(line)`: gift → `regular_price`; no gift → effective website unit
- `manager_totals(value, mode, qty) -> (unit, line)`
- `pos_amount(regular_total, website_total, manager_line_total)`: uses the **normal** website total, never the coupon price
- `calculate_line(LineInput) -> LineResult`
- `calculate_transaction(Sequence[LineInput]) -> TransactionResult`
- Option comparison: `build_options(result) -> (WebsiteOption, GiftOption | None)`. It only presents the two options; it never ranks them.

**Exit checks (M1):** all PRD acceptance examples are tested: 4. (three formats), 5 (coupon 50 on 4.000 → 3.950), 6, 7, 12 (`(5.000−4.000)+3.000 = 4.000`), both manager modes (`4.500×3=13.500`; `12.000` total), mixed gift/no-gift multi-line totals, and exactness (`Decimal("10")/3 × 3 == 10` for the manager total path). Use `hypothesis` optionally for the parse/format round trip.

## 3. Milestone 2: SQLite and product catalog

**`infrastructure/database.py`**

- `connect(path)`: `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `isolation_level=None` with explicit `BEGIN IMMEDIATE`.
- Migration runner: reads `migrations/NNNN_*.sql`, tracks `PRAGMA user_version`, applies each migration in its own transaction, and **requests a pre-migration backup via a callback before applying any pending migration** (wired in M6; stub in M2, with a test asserting the callback is called).
- Refuses to open a DB whose `user_version` is newer than the app knows, and shows a clear error.

**Schema (0001)**

```sql
app_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
products(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL, name_key TEXT NOT NULL,        -- casefold+strip
  regular_price TEXT NOT NULL, website_price TEXT NOT NULL,
  default_gift_name TEXT, notes TEXT,
  archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX ux_products_name_active ON products(name_key) WHERE archived=0;
pricing_history(id, product_id FK, regular_price, website_price, changed_at);  -- append-only, written on every price change
calculation_snapshots(id, created_at, app_version, schema_version,
   totals_json TEXT NOT NULL, confirmation_state TEXT, warnings_json TEXT NOT NULL);
calculation_lines(id, snapshot_id FK ON DELETE RESTRICT, line_index,
   product_id INTEGER NULL,            -- informational only; NOT a live FK dependency
   product_name TEXT NOT NULL, quantity INTEGER NOT NULL,
   regular_price, website_price, coupon, effective_website_unit,
   gift_selected INTEGER, gift_name,
   manager_value_entered TEXT, manager_mode TEXT, manager_line_total TEXT, manager_unit TEXT,
   result_json TEXT NOT NULL);        -- full LineResult, exact strings
```

- Immutability: `CREATE TRIGGER` that `RAISE(ABORT)` on `UPDATE`/`DELETE` of `calculation_snapshots` and `calculation_lines`. This is tested.
- Timestamps: UTC ISO-8601 stored; displayed in local time.

**`infrastructure/repositories.py`**

- `ProductRepository`: `add, update, archive, restore, get, search(query, include_archived)`. `search` is a case-insensitive `LIKE` on `name_key`, with `%`/`_` escaped.
- Handles Turkish casing: use `casefold()` in Python and store `name_key`. Do not rely on SQLite `lower()`.
- All multi-statement changes run inside a transaction (price change plus a `pricing_history` row).
- Restoring a product whose name collides with an active one returns a typed error.

**Exit checks (M2):** migration test from empty DB; refusal on a newer version; unique-name constraint; archive/restore; pricing_history written; triggers block mutation.

## 4. Milestone 3: Single-product calculator and app shell

- `main.py`: create `QApplication`, resolve paths, open DB (migrations), build `MainWindow` with 4 tabs (Products, Calculator, History, Settings). Set the app name and org via `QCoreApplication` before `platformdirs` calls.
- `ui/products_tab.py`: search box, table (`QAbstractTableModel`), add/edit dialog using `parse_money` with inline error text, an archive/restore toggle, and a "show archived" checkbox.
- `ui/calculator_tab.py` (single line first, structured so M4 reuses the row widget):
  - `CalculatorLineWidget` emits a `changed` signal. A controller builds a `LineInput` and calls the pure `calculate_line`. **No formulas inside widgets.**
  - Product picker (saved or "one-off"), quantity spinbox (≥1), coupon field (empty → 0), gift checkbox, gift name (prefilled from the product default, editable), manager value plus mode radio (Unit/Total line).
  - Result panel shows: regular, website, coupon, effective website, 10% base/discount/unit/total, manager mode and totals, and the POS block labeled exactly `POS-entry calculation (verify before use)`.
  - Formulas are shown as a collapsible "How this was calculated" section, generated from the `LineResult`.
  - Errors are shown inline, and results are hidden (not stale) while the input is invalid.
- Selecting a product copies values into the line. Edits to coupon, gift name, or manager value never write back to the product.
- "Save calculation" is enabled only when the input is valid (history is wired in M5).

## 5. Milestone 4: Multi-line calculator and comparison

- Line list with add/remove/reorder (move up/down buttons; drag-reorder is optional).
- Per-line gift state is independent. Per-line result card plus side-by-side **Website option | Gift option** panel (gift panel is visible only if the line has a gift selected or a gift name).
- No "recommended" badge and no coloring that implies a winner.
- Transaction totals panel (from `calculate_transaction`), with explicit "n/a" reasons.
- Extra tests: reordering preserves per-line state; removing a line recomputes totals; mixed gift/no-gift; the quantity > 1 examples from the PRD.

## 6. Milestone 5: History

- `application/history.py`: `build_snapshot(inputs, result, warnings, app_version) -> SnapshotRecord` (pure) and `HistoryRepository.save(...)`, which writes the snapshot and all lines in one transaction.
- The snapshot stores both the entered text and the normalized `Decimal` strings.
- `confirmation_state`: record what the UI displayed at save time. For the MVP this is the fixed value `"pos_unverified"`, plus warnings. Define it as an enum in `models.py` so it can be extended later.
- `ui/history_tab.py`: list by date, detail view rebuilt **only from stored snapshot rows**. It must never recompute using current product data. Render with the stored formatting, so changing the formatter later does not alter facts.
- No edit or delete UI for history. Optional "Load into calculator as new copy" is out of scope unless trivial.
- Tests: save, edit the product afterwards, and reload; the snapshot is unchanged. Triggers block UPDATE/DELETE.

## 7. Milestone 6: Backups

**`infrastructure/backups.py`**

- `create_backup(live_conn, backup_dir, reason) -> BackupResult`:
  1. Write to `backup_dir/.tmp-<ts>.sqlite` using `sqlite3.Connection.backup()` (source = live connection).
  2. Open the temp file, then run `PRAGMA integrity_check`, and require `"ok"`. Also check that `user_version` equals the live one.
  3. `fsync`, then `os.replace` to `src/arcelikSalesHelper-<UTC ts>-<reason>.sqlite`. Use a unique name; on collision append a counter.
  4. Only after success, rotate: keep the newest 30 *verified* backups. Never touch the live DB. Rotation errors are logged but do not mark the backup as failed.
  5. On any failure, delete the temp file, record the failure, and return an error result.
- Policy functions (pure, tested with a fake clock): `needs_startup_backup(last_success, now)` (none exists, or older than 24h), `needs_close_backup(db_changed)`.
- Track "database changed" with `PRAGMA data_version` or a dirty flag set by repositories. Prefer a dirty flag plus an `app_metadata` counter.
- Triggers: baseline after initial schema creation; startup; clean close (`closeEvent` and `aboutToQuit`); pre-migration (callback from M2); manual button.
- `app_metadata` keys: `last_backup_success_at`, `last_backup_path`, `last_backup_failure_at`, `last_backup_failure_message`. A later success clears the failure flag.
- Backup runs synchronously on startup and close (the DB is small). If it ever exceeds a threshold, move to `QThreadPool` with the same code.

**`ui/settings_tab.py`**: show DB path and backup dir (copyable, with an "Open folder" button), latest success time, a "Back up now" button with result feedback, and a persistent red banner (also visible on the main window) if the last automatic backup failed.

**`paths.py`**

- Windows: `platformdirs.user_data_dir(app, company)`, which maps to `%LOCALAPPDATA%\<Company>\<App>`.
- Linux: `platformdirs.user_data_dir(app)` (appauthor=False), which uses `$XDG_DATA_HOME` or `~/.local/share`.
- Create directories with `exist_ok=True`. Allow an env override `src/arcelikSalesHelper_DATA_DIR` for tests only.
- Open question to confirm before M8: the final `<CompanyName>` and `<AppName>` strings. Use placeholders `AppName="BusinessHelper"` and `CompanyName="BusinessHelper"` in a single constants module.

**Tests:** corrupted-temp detection (monkeypatch integrity result), retention (create 35, keep 30, newest preserved), failed backup does not delete old ones, live DB untouched, policy functions around the 24h boundary, and the failure banner state.

## 8. Milestone 7: CSV import

**`infrastructure/csv_import.py`** (parse and plan are pure; apply is transactional)

- `parse_csv(path) -> ParsedCsv`: open with `utf-8-sig`, `csv.DictReader` with `,` delimiter. The header must equal exactly the 3 required columns after strip (any missing or extra column is a file-level error naming the problem). Cap the file size and row count (for example 50 MB / 100k rows) to avoid freezing.
- Per-row validation using `parse_money` and the same product rules (non-negative, name non-empty). Errors carry the row number (1-based, counting the header as row 1), the column, and the message.
- Duplicate names inside the file (by `name_key`) are flagged as row errors that reference the first occurrence.
- `plan_import(rows, existing_by_key) -> ImportPlan` classifies each valid row as `NEW`, `CONFLICT`, or `UNCHANGED` (same prices, so auto-skip but still listed).
- `UNCHANGED` rows are listed but need no decision.
- Decisions: `CONFLICT` requires `UPDATE` or `SKIP` for **each** product. No "apply to all" in the MVP (the PRD says per conflict); a later enhancement may add it.
- `apply_plan(conn, plan, decisions) -> ImportSummary` runs in one transaction. On any error it rolls back everything. Updates write `pricing_history`. It never modifies gift name or notes of existing products.
- If any row has errors: block Apply by default. Offer "Import valid rows only" as an explicit choice, and state this in the summary. Decide this when building the UI; default is **block**, because the PRD says "validate every row" and "apply a valid import".
- A pre-import backup is recommended (the PRD only requires pre-migration/destructive). Take one, since bulk updates are effectively destructive.

**`ui` import dialog:** file picker, preview table (status, row #, name, old vs new prices, error), a per-conflict Update/Skip combo, and a summary dialog (created / updated / skipped / unchanged / errors).

**Tests:** both numeric styles, BOM, bad header, extra columns, blank lines, duplicates in file, row-specific errors, conflict update vs skip, rollback on a forced mid-apply failure, archived-product collision handling (define: an archived match is treated as a conflict with the option to update and restore, and confirm this in the UI text).

## 9. Milestone 8: Packaging and validation

- PyInstaller spec for Windows and Linux (build on each OS; no cross-compile). Include the migration `.sql` files as data (`importlib.resources` for loading, not `__file__` paths).
- Smoke script `scripts/smoke.py`: launch offscreen (`QT_QPA_PLATFORM=offscreen`), create a product, run a calculation, save it, back up, and exit. Run in CI on both OSes if CI is available.
- Manual checklist on real Windows and Linux machines: data dir location, first-run baseline backup, closing triggers a backup, number display `153.345,56 TL`, the CSV flow, and a fresh-install migration.
- Linux note: document the required system libraries for Qt (`libxcb-cursor0` and similar) in the README.

## 10. Test matrix (maps to PRD acceptance #19)

`test_money.py` parsing and formatting, round trip, and rejects · `test_pricing.py` coupon, gift/no-gift base, quantity, both manager modes, POS examples, exactness, no coupon in POS · `test_calculator.py` multi-line totals, n/a handling, independent gift state · `test_history.py` immutability · `test_csv_import.py` · `test_backups.py` · `test_database.py` migrations · `test_ui_*.py` with pytest-qt (a few key flows only).

## 11. Cross-cutting rules for me as the agent

1. No formulas in `ui/`. If I need one there, move it to `domain/pricing.py` first.
2. `domain/` must import nothing from Qt, sqlite3, or infrastructure (enforce with a simple test that scans imports).
3. No `float` anywhere. Add a test or a ruff rule that greps for `float(` in `domain/`.
4. Every user-visible error is a typed `Result` value, not an uncaught exception. Wrap the top level with an error dialog and a log file in the data dir.
5. Commit per milestone with its tests green. Run `ruff`, `mypy` (strict on `domain/`), and `pytest` before declaring done.
6. The POS label text is a constant used in the UI, history view, and tests: `POS-entry calculation (verify before use)`.
7. Never present results as official, approved, or recommended. Don't add wording like "best option".

## 12. Remaining open items (not blocking M1 to M5)

- Final company and app name for the Windows data directory (placeholder in use).
- Whether "Import valid rows only" should be offered (default: blocked until all rows are valid).
- Real, non-sensitive AX/POS example to validate the POS formula (PRD section 12). Capture it as a fixture test once available.

---

If you'd like, I can start on Milestone 1 (domain core and tests) next.
