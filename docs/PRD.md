# Product Requirements Document (PRD)

**Project:** Business Helper  
**Document version:** 0.3  
**Status:** Proposed

## 1. Project overview

Build a small, reliable desktop application for Windows and Linux to help an employee look up product pricing, compare website and gift-based sale options, calculate discount scenarios, and preserve calculation history. The first release will use **Python, PySide6, and SQLite**.

The app supports a workflow around the company's website and Microsoft Dynamics AX/POS. It is a personal productivity tool, not a replacement for the company's official systems. It must not modify Dynamics AX/POS, claim its stored data is an official record, or treat a calculation as manager-approved unless the relevant inputs were provided by the user.

The application should remain useful without inventory tracking. Warehouse verification and deeper AX/POS integration are future possibilities, not MVP requirements.

Pricing calculations should use functional programming as much as practical. Pure pricing, validation, parsing, formatting, and aggregation functions must remain independent of the UI and database. Class-based code is appropriate for PySide6 widgets, application lifecycle, persistence, and other infrastructure.

## 2. Goals

- Maintain a local catalog of product names and prices.
- Store the regular/first price and the normal website discounted price observed on the company selling website.
- Optionally store a default gift name and notes for a product.
- Calculate the standard 10% scenario.
- Compare a normal website-discount option with a gift option.
- Accept a manager-provided sale value as a manually entered amount, without modeling it as a fixed percentage.
- Support both unit-price and total-line-price manager values.
- Calculate the POS-entry amount using the supplied operational formula.
- Support multiple products and quantities in one calculation.
- Preserve complete, immutable calculation snapshots because prices and promotions can change over time.
- Use one local SQLite database with robust automatic backups on Windows and Linux.
- Present TRY amounts in Turkish-style currency format, such as `153.345,56 TL`, preserving kuruş.

## 3. MVP scope and non-goals

### Included in the MVP

- Manual product entry and editing.
- Product name, regular price, and website discounted price.
- Optional saved gift name and notes.
- Single-product and multi-product calculations.
- Quantity per calculator line.
- Per-line gift selection and gift-name override.
- Temporary additional coupon override.
- Temporary manager-provided value with unit or total-line mode.
- Website and gift options displayed side by side.
- Complete calculation history.
- SQLite schema migrations and verified automatic backups.
- CSV import as the final MVP milestone.

### Non-goals for the MVP

- Product codes or barcode identifiers.
- Automatic website scraping from the GUI.
- Automatic warehouse tracking, stock transfers, or stock availability claims.
- Editing or reconciling official Dynamics AX/POS data.
- Multi-user or network-shared database access.
- Customer account management or storage of customer personal information.
- Automatic approval or selection of the manager's sale value.
- Excel export.

Website scraping may be developed later as a separate authorized tool or as an optional integration if an authorized API/feed exists. The MVP workflow is:

`external scraper or manual source -> CSV file -> Business Helper import`

The GUI must not depend on scraping behavior, website markup, or anti-bot workarounds.

## 4. Terminology and data

- **Product name:** The product's display name. Product codes are outside MVP scope.
- **Regular/first price:** The product's original price shown by the company website or used as the POS starting price.
- **Website discounted price:** The normal discounted price observed on the company website.
- **Additional coupon discount amount:** An extra monetary reduction applied after the normal website discounted price. It may vary by customer and is a temporary calculator input unless explicitly saved as a future product feature.
- **Effective website price:** `website_discounted_price - additional_coupon_discount_amount`.
- **Gift:** A promotion included with a product. A saved product may have a default gift name, and the calculator may override it for the current transaction.
- **Gift option:** The option in which the customer receives the gift and the discount scenarios use the regular/first price as their base.
- **Manager-provided value:** A manually entered sale amount supplied by the manager. It is not a percentage and must not be converted into one.
- **Manager value mode:** Whether the manager-provided value is a unit price or the total price for the entire calculator line.
- **POS-entry amount:** The value calculated for entry into Dynamics AX/POS. It is separate from the customer-facing website or manager option and remains labeled as requiring operational verification.

### Product fields

The MVP product record supports:

- Internal database ID.
- Product name.
- Regular/first price.
- Website discounted price.
- Optional default gift name.
- Optional notes.
- Created/updated timestamps.
- Archived status.

Product codes are not required or modeled in the MVP.

### Calculator line fields

Each calculator line supports:

- Product selection or one-off product name.
- Quantity, defaulting to one.
- Regular price used.
- Website discounted price used.
- Additional coupon amount for this calculation.
- Gift selected/not selected.
- Gift name, using the saved default or a temporary override.
- Manager-provided value.
- Manager value mode: unit price or total line price.

All values used in a calculation must be copied into its history snapshot. Later product edits must not change old calculations.

## 5. Price input and validation behavior

Use Python's `Decimal` for monetary arithmetic. Never use binary floating-point for prices.

The application must accept:

- Turkish-style values such as `54.999,00`.
- Plain integer values such as `54999`.
- Standard decimal values such as `54999.00`.

Values are normalized internally and displayed consistently as Turkish TRY, for example `54.999,00 TL`.

Validate that:

- Product prices are numeric and non-negative.
- Quantity is a positive whole number.
- Additional coupon amount is non-negative and does not exceed the website discounted price.
- Effective website price cannot be negative.
- Manager-provided value is numeric and non-negative.
- Manager value mode is explicitly recorded.

The application may warn when a manager-provided value is unexpectedly greater than the applicable website amount, but it must not silently reinterpret or replace the value.

## 6. Pricing and calculation requirements

### Rule A: Website price and coupon

`effective_website_price = website_discounted_price - additional_coupon_amount`

The UI must show the regular price, normal website discounted price, coupon amount, and effective website price separately.

The coupon amount is a temporary per-calculation override and must not overwrite saved product data automatically.

For a quantity:

```text
regular_total = regular_price × quantity
website_total = website_discounted_price × quantity
coupon_total = additional_coupon_amount × quantity
effective_website_total = effective_website_price × quantity
```

### Rule B: Standard 10% scenario

The standard 10% scenario is separate from the manager-provided value.

- **No gift:** use the effective website price as the discount base.
- **Gift selected:** use the regular/first price as the discount base.

```text
discount_amount = discount_base × 0.10
scenario_price = discount_base - discount_amount
```

The UI must display the base, discount amount, resulting unit price, quantity, and resulting line total.

### Rule C: Manager-provided sale value

The manager provides a manual sale value. The application must support both modes:

#### Unit-price mode

The entered amount is the sale price for one product.

```text
manager_line_total = manager_unit_value × quantity
```

#### Total-line-price mode

The entered amount is the sale price for the entire calculator line.

```text
manager_line_total = manager_line_value
manager_unit_value = manager_line_value / quantity
```

The UI must clearly display which mode was used. The application must not infer a percentage, compound the value with 10%, or automatically assign it to the product.

For a no-gift sale, the manager may provide a total below the website total, for example `12.000,00 TL` becoming `11.000,00 TL`.

For a gift sale, the manager value may be entered per unit, for example `4.500,00 TL × 3 = 13.500,00 TL`. The customer can compare this with the lower website price when the gift has greater practical value.

### Rule D: Website and gift comparison

When a gift is available, show both options side by side:

1. **Website discount option**
   - Uses the normal/effective website price.
   - Shows the standard 10% result where applicable.
2. **Gift option**
   - Shows the gift name.
   - Uses the regular price as the 10% discount base.
   - Shows the manager-provided value when supplied.

The application must not decide which option the customer should choose.

Gift selection is independent for each calculator line. A transaction may contain both gift and no-gift lines.

### Rule E: POS-entry amount

The supplied formula is:

```text
POS line amount =
(regular line total - normal website discounted line total)
+ manager-provided line total
```

The formula uses the **normal website discounted price**, not the customer-specific effective website price after an additional coupon.

For a single unit:

```text
(5.000,00 - 4.000,00) + 3.000,00 = 4.000,00 TL
```

For quantity, the regular and normal website prices are multiplied by quantity, and the manager value is normalized to its line total according to the selected manager value mode.

The POS result must be displayed separately as:

`POS-entry calculation (verify before use)`

The application must not claim that this result is an official or manager-approved POS instruction.

### Rule F: Transaction totals

For multiple calculator lines:

- Calculate every line independently.
- Preserve each line's selected gift state and manager value mode.
- Sum corresponding line totals for transaction totals.
- Show per-line details and totals.

At minimum, show totals for regular price, website option, effective website option, 10% scenario, manager option, and POS-entry amount when required inputs are present.

## 7. Main screens

### A. Products

- Search by product name.
- Add, edit, archive, and restore products.
- Display regular price, website discounted price, saved gift name, notes, and last-updated information.
- Do not require product codes.

### B. Multi-product calculator

- Add, remove, and reorder product lines.
- Select a saved product or enter a one-off product.
- Set quantity for each line.
- Override the coupon amount for the current calculation.
- Select gift/no-gift per line.
- Override the gift name per line.
- Enter a manager-provided value per line.
- Select unit-price or total-line-price manager mode.
- Show website and gift options side by side.
- Show per-line results and transaction totals.
- Show formulas, bases, input values, and warnings.
- Do not save temporary values to products automatically.

### C. Calculation history

Save complete immutable snapshots containing:

- Date and time.
- Product name and quantity.
- Regular, website, coupon, and effective prices used.
- Gift selection and gift name.
- Manager-provided value, normalized line total, and value mode.
- Website-option result.
- Gift-option result.
- 10% result.
- POS-entry result.
- Warnings and confirmation state shown at calculation time.

History must remain understandable after product prices, gift promotions, or notes change.

### D. CSV import

CSV import is the final MVP milestone. The required columns are exactly:

```text
product_name,regular_price,website_discounted_price
```

The importer must:

- Preview rows before applying changes.
- Accept Turkish-style and plain numeric prices.
- Validate every row and show row-specific errors.
- Ask the user for each product conflict.
- Support creating new products or updating/skipping a conflicting product according to the user's decision.
- Apply a valid import transactionally.
- Display an import summary.

CSV import does not include product codes, manager values, gift data, or other optional fields in the MVP.

### E. Settings and backups

- Show the active database and backup directory.
- Show the latest successful backup.
- Provide **Back up now**.
- Show a visible warning when the latest automatic backup failed.

## 8. Database, history, and backups

Use SQLite with versioned schema migrations and transactions for multi-field changes.

Suggested entities:

- `products`
- `calculation_snapshots`
- `calculation_lines`
- `pricing_history`
- `app_metadata`

Calculation snapshots and lines must preserve values as entered and normalized values used in the calculation. Product edits must not mutate historical snapshots.

Store the live database and a `backups/` directory using `platformdirs`:

- Windows: `%LOCALAPPDATA%/<CompanyName>/<AppName>/`
- Linux: `$XDG_DATA_HOME/<AppName>/`, falling back to `~/.local/share/<AppName>/`

Automatic backup requirements:

- Create application and backup directories on first launch.
- Create a verified baseline backup after initial schema creation.
- Create a startup backup when no backup exists or the latest successful backup is older than 24 hours.
- Create a backup on clean close when database content changed.
- Create a backup before migrations or destructive maintenance.
- Use SQLite's supported backup API rather than blindly copying a live database.
- Write to a temporary file, open it, run `PRAGMA integrity_check`, then rename it to the final timestamped filename.
- Keep the latest 30 verified backups.
- Delete old backups only after a new backup has completed and passed verification.
- Never delete the live database during rotation.
- Report backup success only after verification and visibly report failures.

Same-disk backups do not protect against disk failure. A company-approved external destination may be added later.

## 9. Suggested implementation structure

```text
src/arcelikSalesHelper/
├── main.py
├── domain/
│   ├── models.py
│   ├── money.py
│   ├── pricing.py
│   ├── validation.py
│   └── formatting.py
├── infrastructure/
│   ├── database.py
│   ├── repositories.py
│   ├── backups.py
│   └── csv_import.py
├── application/
│   ├── calculator.py
│   └── history.py
├── ui/
│   ├── main_window.py
│   ├── products_tab.py
│   ├── calculator_tab.py
│   ├── history_tab.py
│   └── settings_tab.py
└── tests/
    ├── test_money.py
    ├── test_pricing.py
    ├── test_calculator.py
    ├── test_csv_import.py
    └── test_backups.py
```

Pricing, parsing, validation, formatting, and aggregation functions should be pure and independently testable. UI code should orchestrate inputs and rendering, not contain pricing formulas.

## 10. MVP milestones

1. Functional money parsing, formatting, validation, and pricing calculations.
2. SQLite product catalog and migrations.
3. Single-product calculator.
4. Multi-product calculator with quantities and gift comparisons.
5. Complete calculation history.
6. Verified automatic backups.
7. CSV import as the final MVP milestone.
8. Windows and Linux packaging and validation.

## 11. Acceptance criteria

1. The PySide6 application launches on target Windows and Linux systems and stores SQLite data in the correct per-user data directory.
2. A user can add, search, edit, archive, and restore products using product name, regular price, website discounted price, optional gift name, and notes.
3. Product codes are not required for MVP operation.
4. The application accepts `54.999,00`, `54999`, and `54999.00`, and displays each as `54.999,00 TL`.
5. A coupon of `50,00 TL` applied to a website discounted price of `4.000,00 TL` produces an effective website price of `3.950,00 TL`.
6. A no-gift 10% scenario uses the effective website price as its base.
7. A gift 10% scenario uses the regular price as its base.
8. The calculator supports multiple product lines, quantities, and independent gift selections.
9. The calculator displays website and gift options side by side when a gift is available.
10. A manager value can be entered as either a unit price or a total line price, and the selected mode is visible in results and history.
11. The manager value is not converted into a percentage, compounded automatically, or silently assigned to a product.
12. The POS calculation uses `(regular line total - normal website discounted line total) + manager-provided line total` and does not substitute the effective coupon price.
13. The POS result is visibly labeled `POS-entry calculation (verify before use)`.
14. Transaction totals correctly sum independently calculated lines.
15. A complete immutable calculation snapshot preserves all product values, quantities, gift choices, manager values, modes, results, and warnings used at calculation time.
16. CSV import is the final MVP milestone and supports only `product_name,regular_price,website_discounted_price`.
17. CSV import accepts both Turkish-style and plain numeric values and asks the user per conflict.
18. Verified baseline, startup, clean-close, migration, manual, and retention backup behavior works as specified.
19. Automated tests cover parsing, formatting, coupon validation, gift/no-gift bases, quantity calculations, both manager value modes, POS examples, multi-line totals, immutable snapshots, CSV conflicts, and backup verification/retention.

## 12. Operational caution

The POS formula and the exact AX/POS field it represents must be validated against a real, non-sensitive workflow example before the application is used to guide an actual transaction. Until that validation is complete, POS results are informational only and must retain the verification warning.
