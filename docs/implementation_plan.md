# Technical Implementation Plan (agent-facing)

Source: PRD v0.5. This file is the working contract. Prioritize calculator productivity, then catalog productivity; keep scraping and shared PostgreSQL as later architectural milestones.

## Feedback implementation status

Status reflects code and documentation currently present. “Implemented” describes scope, not a claim that the acceptance tests or employee workflow review have passed.

| Feedback area | Status | Implemented / remaining |
| --- | --- | --- |
| Shared manager total in calculator | Implemented | Enter one manager total and allocate it by each line's regular total; per-line manager input remains available. |
| Product-free total calculator | Implemented | Aggregate regular, website, manager, and POS mode inputs work without selecting catalog products. |
| POS amount precision | Implemented | Each line POS-entry amount rounds half-up to two decimals; transaction POS total sums the rounded line amounts. |
| POS total allocation target | Remaining | Current allocation splits the manager total. A separate mode that accepts a final POS-entry target and distributes that exact target across product lines has not been implemented. Confirm which total employees intend to enter before building it. |
| Fixed and percentage POS modes | Implemented; detection remaining | Both modes remain selectable per line, including in the total-only workflow. Automatic detection of percentage offers is not implemented. |
| Third-party combined offers | Partial | The percentage POS formula remains available. A transaction-wide combined-offer rule and its input/source semantics still need employee confirmation; individual website prices remain unchanged. |
| Transaction price scenarios | Implemented | Regular and website totals plus 10%, 15%, 18%, and 20% totals appear in a collapsible section that opens by default. |
| Unit-price / line-total inputs | Implemented; clarity remaining | Both modes affect calculations. Review with employees whether the unit value and selected mode are clear enough in the result cards. |
| Product quantity / stock | Partial | On-hand count can be edited with product details or the count workflow; the dedicated count action remains a shortcut with count notes. Reserved and available quantities, reservations, and live stock synchronization remain deferred. |
| Bulk product actions | Implemented | Multi-select archive/restore is available. |
| Product deletion | Implemented | Confirmation is required; products referenced by calculation history cannot be permanently deleted and should be archived. |
| Product CSV export/import | Implemented | Export includes prices and known quantity; import supports the exported columns. |
| History customer/search/delete | Implemented | Customer display name is optional; history search matches customer/product names; confirmed deletion removes a whole snapshot and its lines. |
| Shared laptops / PostgreSQL | Deferred | Hosting, authentication, permissions, backup ownership, and offline behavior need a design before implementation. |
| Website scraping | Deferred | Requires authorized-source review, request limits, source-change handling, and failure behavior before implementation. |
| Product save from calculator | Remaining | One-off calculator products cannot yet be saved directly to the catalog. |
| POS operational verification | Remaining | Two-decimal entry formatting is implemented, but the formulas and exact AX/POS fields still need validation against a real, non-sensitive workflow example. |

## Milestone status

- **M1–M4: Implemented.** Localization, calculator/domain rules, exact arithmetic, SQLite migrations, catalog persistence, and stock-count foundations are present. Test/acceptance review remains outstanding.
- **M5: Implemented.** Shared manager total, weighted allocation, total-only calculation, retained per-line mode, and scenario totals are present.
- **M6: Implemented.** Quantity editing, multi-select archive/restore, safe deletion, and CSV export are present.
- **M7: Implemented with one remaining item.** Customer name, search, and whole-entry deletion are present; saving a one-off product directly from the calculator remains.
- **M8–M9: Implemented.** Verified backups and CSV import/export are present.
- **M10: Deferred.** Reservations, sale/open-account workflow, and reserved/available quantities.
- **M11: Partial.** Windows packaging runs in GitHub Actions. Linux packaging, platform validation, a reusable PyInstaller spec, and `scripts/smoke.py` remain.
- **Future architecture: Deferred.** Scraper integration and managed PostgreSQL sharing remain later milestones.

## 0. Locked decisions

| Topic            | Decision                                                                                                                                                                                                                            |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python           | 3.11+; `pyproject.toml`; deps: `PySide6`, `platformdirs`; dev: `pytest`, `pytest-qt`, `ruff`, `mypy`                                                                                                                                |
| Money type       | `decimal.Decimal` only. Never `float`.                                                                                                                                                                                              |
| Rounding         | General calculation details preserve exact `Decimal` values. POS-entry line amounts are rounded half-up to two fractional digits because the POS accepts kuruş precision only; transaction POS totals sum the rounded line amounts. |
| Decimal context  | Module-level `localcontext` with `prec=60`, used for all arithmetic, so divisions such as `line / qty` stay effectively exact.                                                                                                      |
| Storage of money | SQLite `TEXT` holding `str(Decimal)`, never REAL. Reload with `Decimal(s)`.                                                                                                                                                         |
| UI language      | Turkish only for the first release; all user-visible text must be Turkish. Internal identifiers, database schema names, and source-code comments may remain English. A language selector is deferred to a later enhancement.        |
| CSV              | Comma-delimited, UTF-8 (accept BOM via `utf-8-sig`); import requires `product_name,regular_price`, accepts optional `website_discounted_price,quantity`; export writes the same fields                                              |
| CSV conflict key | `product_name.strip().casefold()`                                                                                                                                                                                                   |
| Packaging        | PyInstaller (one-folder), Windows and Linux                                                                                                                                                                                         |
| Style            | Pure functions in `domain/`, with no imports from `PySide6`, `sqlite3`, or `infrastructure`. Frozen dataclasses for models.                                                                                                         |

**Design rule for exactness:** line totals are authoritative. In manager total-line mode, `manager_line_total` is the entered value, and `manager_unit_value = line / qty` is a derived display value. It never feeds back into totals or the POS formula. A non-terminating unit value is displayed exactly to the available `Decimal` precision; it is never rounded or silently shortened.

**Calculator workflow decision:** keep fixed-amount and percentage POS modes per line, with fixed amount as the default. Percentage mode remains available for third-party offers where the regular website discount does not describe the offer. Round each final line POS amount half-up to two fractional digits, then sum those entry amounts for the displayed transaction POS total. In shared-total mode, allocate the entered manager total by each line's regular total (`regular_price × quantity`) and place any finite-precision residue on the final nonzero-weight line so the allocation sum equals the input exactly. Per-line manager input and product-free total-only calculation remain available.

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

## 2. Milestone 1: Turkish localization (DONE)

- Centralize user-visible strings instead of scattering translated text across widgets and application services.
- Translate tab names, window titles, labels, buttons, placeholders, validation errors, warnings, tooltips, formula explanations, backup/settings messages, import/export dialogs, and history presentation.
- Keep internal Python names, database column names, migration identifiers, and CSV field names in English for compatibility and maintainability.
- Display historical calculations with Turkish labels without changing their stored normalized values or calculation facts.
- Add UI tests that assert the primary screens contain Turkish text and no known English labels remain.
- Do not introduce a language selector in this milestone; reserve a translation/catalog boundary for the later good-to-have feature.

**Exit checks (M1):** all current user-facing screens and error paths are translated, calculator/history snapshots render in Turkish, and focused UI/application tests pass.

## 3. Milestone 2: Calculator rules and domain correction

- Rename user-facing terminology from `website_price` to **website discounted price**. Preserve internal/database compatibility only where changing schema would be unnecessarily destructive; new APIs and UI labels must use the clearer term.
- Remove the unused additional coupon feature from calculator inputs, domain models, validation, pricing, history snapshots, CSV/UI surfaces, and tests. Do not retain an effective-price or coupon calculation.
- Keep both manager value modes: unit price and total line price.
- Keep quantity handling and line-total authority. In total-line mode, the entered manager value is the authoritative line total and the derived unit value is display-only.
- Standard 10% calculation:
  - gift selected: `regular_price × 0.90`;
  - no gift: `website_discounted_price × 0.90`.
- Discount amount is the selected 10% base multiplied by `0.10`; it is separate from the manager-provided value.
- Add a per-line POS calculation mode, defaulting to fixed amount. Fixed mode remains `(regular line total - website discounted line total) + manager line total`; percentage mode derives `rate = (regular price - website discounted price) / regular price` and calculates `manager line total / (1 - rate)`.
- Percentage mode applies only to the website/no-gift POS result. Gift POS remains the boss gifted line total. Display the selected mode and formula, and store the mode in calculation history.
- Update pure domain models, application result labels, formula explanations, and tests together. Results must remain hidden while input is invalid.

**Exit checks (M2):** the original fixed-amount examples and the new percentage example are tested exactly, gift/no-gift 10% bases are correct, both manager modes and quantities remain correct, per-line mode selection is retained in history, gift POS remains direct, and no coupon field or coupon terminology remains in the calculator flow.

## 4. Milestone 3: Domain core hardening (pure, no I/O)

**`domain/money.py`**

- `parse_money(text: str) -> Result[Decimal, str]` (no exceptions for bad user input).
- Accepted: `54.999,00`, `54.999,52`, `54999`, `54999.00`, `54.999`, `1.234.567,89`.
- Disambiguation rules, implemented and tested explicitly:
  - Contains both `.` and `,`: the last separator is the decimal mark; the other is the thousands separator.
  - Only `,`: decimal mark (at most one, 1 to 2+ digits after it).
  - Only `.`:
    - If it appears more than once, or is followed by exactly 3 digits with a ≤3-digit leading group, treat it as a thousands separator (`54.999` = 54999). Otherwise treat it as a decimal (`54999.00`, `12.5`).
    - Open ambiguity: `1.234` could be either. Choose thousands (Turkish convention) and surface a UI hint. Document this in the test names.
- Reject: empty, negative sign, letters, `NaN`/`Infinity`, multiple decimal marks, misplaced groups (`1.23.456`), scientific notation.
- Optional trailing `TL`/`TRY` is stripped; whitespace is trimmed.

**`domain/formatting.py`**

- `format_try(d: Decimal) -> str` gives `"54.999,52 TL"` for `Decimal("54999.52")`. Do not quantize, round, or pad/truncate the fractional part. Group the whole-lira portion by `.`, use `,` between lira and the exact fractional part, and append ` TL`.
- `100` kuruş is represented as `1,00 TL`, never as a kuruş value of `100`. Derived values such as `Decimal("100") / 3` must remain visibly exact rather than becoming a rounded two-digit currency value.
- Add formatting tests for `0,00 TL`, `0,01 TL`, `54.999,99 TL`, an exact value with more than two fractional digits, and carry behavior without display rounding.
- No locale dependency, so Windows and Linux behave identically.
- Also `format_decimal_exact(d)` for snapshot/debug views and exact-value display. General calculation fields preserve exact values; POS-entry amounts use the domain's half-up two-decimal result.

**`domain/models.py`** (frozen dataclasses)

- `ManagerMode(Enum): UNIT, LINE`
- `LineInput`: `product_name, quantity:int, regular_price, website_discounted_price, gift_selected:bool, gift_name:str|None, manager_value:Decimal|None, manager_mode:ManagerMode|None, pos_calculation_mode:PosCalculationMode (default FIXED_AMOUNT), product_id:int|None`
- `LineResult`: `regular_total, website_discounted_total, ten_pct_base, ten_pct_discount_unit, ten_pct_unit, ten_pct_total, manager_unit|None, manager_line_total|None, pos_amount|None, warnings: tuple[Warning,...]`
- `TransactionResult`: `lines`, `totals` (regular, website discounted, 10% scenario, manager, POS; each `None` if any line lacks the input, and the UI must explain the missing manager value rather than show a partial sum)
- `Warning`: `code, message, line_index`

**`domain/validation.py`**

- `validate_line(LineInput) -> tuple[Error,...]`: quantity ≥ 1 integer; prices ≥ 0; manager mode required iff manager value is present; manager value ≥ 0.
- Soft warning (not an error): manager line total exceeds the website discounted line total. Never alter the value.

**`domain/pricing.py`** (all pure)

- `ten_percent(base) -> (discount, price)` using `base * Decimal("0.10")`
- `discount_base(line)`: gift → `regular_price`; no gift → `website_discounted_price`
- `manager_totals(value, mode, qty) -> (unit, line)`
- `pos_amount(regular_total, website_discounted_total, manager_line_total, mode)`: supports fixed-amount and percentage gross-up modes; round the final line result half-up to two digits for POS entry
- `calculate_line(LineInput) -> LineResult`
- `calculate_transaction(Sequence[LineInput]) -> TransactionResult`
- Option comparison: `build_options(result) -> (WebsiteOption, GiftOption | None)`. It only presents the two options; it never ranks them.

**Exit checks (M3):** all parsing, formatting, validation, pricing, mixed gift/no-gift totals, manager-mode, quantity, POS, and exactness tests pass. Use `hypothesis` optionally for the parse/format round trip.

## 5. Milestone 4: SQLite and product catalog

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
  regular_price TEXT NOT NULL, website_discounted_price TEXT NOT NULL,
  default_gift_name TEXT, notes TEXT,
  archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX ux_products_name_active ON products(name_key) WHERE archived=0;
pricing_history(id, product_id FK, regular_price, website_discounted_price, changed_at);  -- append-only, written on every price change
calculation_snapshots(id, created_at, app_version, schema_version,
   totals_json TEXT NOT NULL, confirmation_state TEXT, warnings_json TEXT NOT NULL);
calculation_lines(id, snapshot_id FK ON DELETE RESTRICT, line_index,
   product_id INTEGER NULL,            -- informational only; NOT a live FK dependency
   product_name TEXT NOT NULL, quantity INTEGER NOT NULL,
   regular_price, website_discounted_price,
   gift_selected INTEGER, gift_name,
   manager_value_entered TEXT, manager_mode TEXT, manager_line_total TEXT, manager_unit TEXT,
   pos_calculation_mode TEXT NOT NULL DEFAULT 'fixed_amount',
   result_json TEXT NOT NULL);        -- full LineResult, exact strings
```

- Immutability: triggers reject `UPDATE` of `calculation_snapshots` and `calculation_lines`. The repository may delete a complete snapshot and its lines together after explicit user confirmation; individual lines cannot be deleted independently.
- Timestamps: UTC ISO-8601 stored; displayed in local time.

**`infrastructure/repositories.py`**

- `ProductRepository`: `add, update, archive, restore, get, search(query, include_archived)`. `search` is a case-insensitive `LIKE` on `name_key`, with `%`/`_` escaped.
- Handles Turkish casing: use `casefold()` in Python and store `name_key`. Do not rely on SQLite `lower()`.
- All multi-statement changes run inside a transaction (price change plus a `pricing_history` row).
- Restoring a product whose name collides with an active one returns a typed error.

**Exit checks (M4):** migration test from empty DB; refusal on a newer version; unique-name constraint; archive/restore; pricing_history written; triggers block mutation.

## 6. Milestone 5: Calculator productivity workflows

- `main.py`: create `QApplication`, resolve paths, open DB (migrations), build `MainWindow` with 4 tabs (Products, Calculator, History, Settings). Set the app name and org via `QCoreApplication` before `platformdirs` calls.
- `ui/calculator_tab.py`:
  - `CalculatorLineWidget` emits a `changed` signal. A controller builds a `LineInput` and calls the pure `calculate_line`. **No formulas inside widgets.**
  - Keep searchable multi-select product staging, one-off lines, quantity and gift choices.
  - Add a shared manager-total field. Allocate by regular line total and display the allocated manager line total on each card. Keep a switch to per-line manager value entry.
  - Add a product-free total-only mode with aggregate regular price, website discounted price, manager total, and the existing fixed/percentage POS mode choice.
  - Percentage POS mode remains available for third-party offers; do not remove or silently reinterpret either existing POS formula.
  - Result panel shows: regular, website discounted, 10% base/discount/unit/total, manager mode and totals, and the POS block labeled exactly `POS-entry calculation (verify before use)`.
  - Show transaction totals for regular, website discounted, 10%, 15%, 18%, 20%, and POS; keep price scenarios collapsible.
  - Formulas are shown as a collapsible "How this was calculated" section, generated from the `LineResult`.
  - Errors are shown inline, and results are hidden (not stale) while the input is invalid.
- Adding a saved product copies its name, prices, and default gift into the line. Later catalog edits or refreshes never change existing calculator lines; edits to gift name or manager value never write back to the product.
- "Save calculation" is enabled only when inputs are valid; total-only calculations are saved as a one-line snapshot.

## 7. Milestone 6: Catalog productivity

- Product edit includes optional counted on-hand quantity and preserves the stock count log.
- Support extended row selection and confirmed bulk archive/restore.
- Product CSV export writes the currently filtered products and is import-compatible, including quantity when known.
- Offer confirmed permanent deletion for one product only when no calculation snapshot references it; delete its product and stock audit rows in the same transaction. Archive remains the normal removal path.
- Retain existing multi-line behavior, gift comparison, line ordering, and exact transaction totals.

## 8. Milestone 7: History and calculator save actions

- `application/history.py`: `build_snapshot(inputs, result, warnings, app_version) -> SnapshotRecord` (pure) and `HistoryRepository.save(...)`, which writes the snapshot and all lines in one transaction.
- The snapshot stores both the entered text and the normalized `Decimal` strings.
- `confirmation_state`: record what the UI displayed at save time. For the MVP this is the fixed value `"pos_unverified"`, plus warnings. Define it as an enum in `models.py` so it can be extended later.
- Add an optional customer display name when saving; do not collect customer account or contact data.
- `ui/history_tab.py`: searchable list by customer/product name, detail view rebuilt **only from stored snapshot rows**. It must never recompute using current product data.
- Add confirmed deletion of one whole snapshot and all its lines in one transaction. Calculation facts cannot be edited; update triggers remain, while delete triggers are removed only as required for this explicit workflow.
- Add explicit "Save product" and "Save calculation/history" actions to the calculator. A one-off product may be saved to the product catalog; an existing product's price must not be silently overwritten. If entered prices differ, require an explicit update decision and write pricing history.
- Verify customer name persistence, search, deletion confirmation, and whole-entry deletion. Triggers block UPDATE; whole-entry DELETE is available only through the repository transaction.

## 9. Milestone 8: Backups

**`infrastructure/backups.py`**

- `create_backup(live_conn, backup_dir, reason) -> BackupResult`:
  1. Write to `backup_dir/.tmp-<ts>.sqlite` using `sqlite3.Connection.backup()` (source = live connection).
  2. Open the temp file, then run `PRAGMA integrity_check`, and require `"ok"`. Also check that `user_version` equals the live one.
  3. `fsync`, then `os.replace` to `src/arcelikSalesHelper-<UTC ts>-<reason>.sqlite`. Use a unique name; on collision append a counter.
  4. Only after success, rotate: keep the newest 30 _verified_ backups. Never touch the live DB. Rotation errors are logged but do not mark the backup as failed.
  5. On any failure, delete the temp file, record the failure, and return an error result.
- Policy functions (pure, tested with a fake clock): `needs_startup_backup(last_success, now)` (none exists, or older than 24h), `needs_close_backup(db_changed)`.
- Track "database changed" with `PRAGMA data_version` or a dirty flag set by repositories. Prefer a dirty flag plus an `app_metadata` counter.
- Triggers: baseline after initial schema creation; startup; clean close (`closeEvent` and `aboutToQuit`); pre-migration (callback from M2); manual button.
- `app_metadata` keys: `last_backup_success_at`, `last_backup_path`, `last_backup_failure_at`, `last_backup_failure_message`. A later success clears the failure flag.
- Backup runs synchronously on startup and close (the DB is small). If it ever exceeds a threshold, move to `QThreadPool` with the same code.

**`ui/settings_tab.py`**: show DB path and backup dir (copyable, with an "Open folder" button), latest success time, a "Back up now" button with result feedback, and a persistent red banner (also visible on the main window) if the last automatic backup failed.

**`paths.py`**

- Windows: `platformdirs.user_data_dir("arcelikSalesHelper", "arcelikSalesHelper")`, mapping to `%LOCALAPPDATA%\arcelikSalesHelper\arcelikSalesHelper`.
- Linux: `platformdirs.user_data_dir("arcelikSalesHelper", appauthor=False)`, using `$XDG_DATA_HOME` or `~/.local/share`.
- Use `arcelikSalesHelper.sqlite` for the live database and `arcelikSalesHelper-` for backup filenames. The test/portable data-directory override is `ARCELIKSALESHELPER_DATA_DIR`.
- Keep the GUI display name separate and user-facing; its current value is “Arcelik Satış Yardımcısı”.
- Do not migrate the previous `BusinessHelper` data directory or settings; the renamed identity uses a fresh directory and leaves old files untouched.

**Tests:** corrupted-temp detection (monkeypatch integrity result), retention (create 35, keep 30, newest preserved), failed backup does not delete old ones, live DB untouched, policy functions around the 24h boundary, and the failure banner state.

## 10. Milestone 9: CSV export and import

**`infrastructure/csv_export.py` and `infrastructure/csv_import.py`** (export is deterministic; import parsing/planning are pure and apply is transactional)

- Export `product_name,regular_price,website_discounted_price,quantity`; unknown quantities are blank and prices are exact canonical decimals.
- `parse_csv(path) -> ParsedCsv`: open with `utf-8-sig`, `csv.DictReader` with `,` delimiter. Require `product_name,regular_price`; allow `website_discounted_price,quantity`; reject unknown columns. Cap the file size and row count (for example 50 MB / 100k rows).
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

## 11. Later milestones: reservations, scraping, and shared data

- Add reservations, sale/open-account states, and reserved/available quantity after the on-hand counting workflow is established and reservation lifecycle details are agreed.
- Evaluate authorized scraper integration separately, with bounded update frequency, source-change handling, and clear failures. Do not rely on anti-bot workarounds.
- Design multi-laptop PostgreSQL access after choosing hosting, authentication/permissions, backups, and offline behavior. Do not share a live SQLite file over a network drive.
- If employees need a target POS-total allocator, first distinguish whether its target is manager sale value or final POS-entry amount. This is separate from allocation of one shared manager total.

## 12. Milestone 11: Packaging and validation

- PyInstaller spec for Windows and Linux (build on each OS; no cross-compile). Include the migration `.sql` files as data (`importlib.resources` for loading, not `__file__` paths).
- Smoke script `scripts/smoke.py`: launch offscreen (`QT_QPA_PLATFORM=offscreen`), create a product, run a calculation, save it, back up, and exit. Run in CI on both OSes if CI is available.
- Manual checklist on real Windows and Linux machines: data dir location, first-run baseline backup, closing triggers a backup, number display `153.345,56 TL`, the CSV flow, and a fresh-install migration.
- Linux note: document the required system libraries for Qt (`libxcb-cursor0` and similar) in the README.

## 13. Test matrix (maps to PRD acceptance #19)

`test_money.py` parsing and formatting, round trip, and rejects · `test_pricing.py` gift/no-gift base, quantity, both manager modes, POS examples, exactness, and no coupon surface · `test_calculator.py` multi-line totals, n/a handling, independent gift state · `test_history.py` immutability and Turkish presentation · `test_csv_import.py` · `test_backups.py` · `test_database.py` migrations · `test_ui_*.py` with pytest-qt (a few key flows only).

## 14. Cross-cutting rules for me as the agent

1. No formulas in `ui/`. If I need one there, move it to `domain/pricing.py` first.
2. `domain/` must import nothing from Qt, sqlite3, or infrastructure (enforce with a simple test that scans imports).
3. No `float` anywhere. Add a test or a ruff rule that greps for `float(` in `domain/`.
4. Every user-visible error is a typed `Result` value, not an uncaught exception. Wrap the top level with an error dialog and a log file in the data dir.
5. Commit per milestone with its tests green. Run `ruff`, `mypy` (strict on `domain/`), and `pytest` before declaring done.
6. The POS label text is a constant used in the UI, history view, and tests: `POS-entry calculation (verify before use)`.
7. Never present results as official, approved, or recommended. Don't add wording like "best option".

---

The immediate calculator priority is shared manager-total entry and product-free total-only calculation. Preserve fixed and percentage POS modes throughout.
