# Product Requirements Document (PRD)

**Project:** arcelikSalesHelper
**Document version:** 0.5
**Status:** Proposed

## 1. Project overview

Build a small, reliable desktop application for Windows and Linux to help an employee look up product pricing, compare website and gift-based sale options, calculate discount scenarios, and preserve calculation history. The first release will use **Python, PySide6, and SQLite**.

The app supports a workflow around the company's website and Microsoft Dynamics AX/POS. It is a personal productivity tool, not a replacement for the company's official systems. It must not modify Dynamics AX/POS, claim its stored data is an official record, or treat a calculation as manager-approved unless the relevant inputs were provided by the user.

The MVP records manually counted on-hand quantity to support catalog productivity. It does not claim live or official inventory accuracy. Reserved/available stock, multi-laptop sharing, and scraping are later milestones.

Pricing calculations should use functional programming as much as practical. Pure pricing, validation, parsing, formatting, and aggregation functions must remain independent of the UI and database. Class-based code is appropriate for PySide6 widgets, application lifecycle, persistence, and other infrastructure.

## 2. Goals

- Maintain a local catalog of product names and prices.
- Store the regular/first price and the normal website discounted price observed on the company selling website.
- Optionally store a default gift name and notes for a product.
- Calculate the standard 10% scenario.
- Compare a normal website-discount option with a gift option.
- Accept separate manager-provided boss discounted and boss gifted sale values, without modeling either as a fixed percentage.
- Support both unit-price and total-line-price modes for each manager-provided sale value.
- Calculate the POS-entry amount using the operational formula for the selected website or gift option.
- Support multiple products and quantities in one calculation.
- Let the manager provide one total sale value for a multi-product transaction and allocate it by each line's regular-price total, reconciling the allocations so they sum exactly to the entered total.
- Provide a product-free total-only calculation path as well as per-line manager values.
- Preserve fixed-amount and percentage POS modes; percentage mode remains available for third-party offers where the normal website discount does not describe the combined offer.
- Record a manually counted on-hand quantity per catalog product.
- Search and delete whole history entries, optionally labeled with a customer name.
- Export the product catalog to CSV.
- Preserve complete, immutable calculation snapshots because prices and promotions can change over time.
- Use one local SQLite database with robust automatic backups on Windows and Linux.
- Present TRY amounts in Turkish-style currency format: `.` separates thousands, `,` separates lira from the fractional amount, and the `TL` suffix is appended (for example `54.999,52 TL`). Preserve exact derived values in calculation details. POS-entry amounts are rounded half-up to two fractional digits because POS accepts kuruş precision only; transaction POS totals sum these rounded line-entry values.
- Present every user-visible label, message, warning, dialog, formula explanation, and history heading in Turkish for the first release. A language selector is deferred to a later enhancement.

## 3. MVP scope and non-goals

### Included in the MVP

- Manual product entry and editing.
- Optional manually counted on-hand quantity, entered in the product editor or stock-count workflow.
- Product name, regular price, and website discounted price.
- Optional saved gift name and notes.
- Single-product and multi-product calculations.
- Quantity per calculator line.
- Per-line gift selection and gift-name override.
- Temporary boss discounted and boss gifted values, each with unit or total-line mode.
- One shared manager total allocated across product lines by regular line totals, while retaining per-line input as an alternate.
- Product-free total-only calculation using transaction totals.
- Website and gift options displayed side by side.
- Complete calculation history.
- Optional customer name, history search, and confirmed deletion of a complete history entry.
- SQLite schema migrations and verified automatic backups.
- CSV export and preview-based CSV import.

### Non-goals for the MVP

- Product codes or barcode identifiers.
- Automatic website scraping from the GUI.
- Reserved/available stock, stock transfers, reservation workflows, or live warehouse claims.
- Editing or reconciling official Dynamics AX/POS data.
- Multi-user or network-shared database access.
- Automatic website scraping from the GUI.
- Customer account management or storage of personal data beyond an optional customer display name on a calculation.
- Automatic approval or selection of the manager's sale value.
- Excel export.

Website scraping may be developed later as a separate authorized tool or as an optional integration if an authorized API/feed exists. The MVP workflow is:

`external scraper or manual source -> CSV file -> arcelikSalesHelper import`

The GUI must not depend on scraping behavior, website markup, or anti-bot workarounds.

## 4. Terminology and data

- **Product name:** The product's display name. Product codes are outside MVP scope.
- **Regular/first price:** The product's original price shown by the company website or used as the POS starting price.
- **Website discounted price:** The normal discounted price observed on the company website.
- **Gift:** A promotion included with a product. A saved product may have a default gift name, and the calculator may override it for the current transaction.
- **Gift option:** The option in which the customer receives the gift and the discount scenarios use the regular/first price as their base.
- **Boss discounted price:** A manually entered manager sale amount for the normal website/no-gift option. It is not a percentage.
- **Boss gifted price:** A manually entered manager sale amount for the gift option. It is not a percentage.
- **Manager value mode:** Whether a supplied boss price is a unit price or the total price for the entire calculator line.
- **Shared manager total:** One transaction-wide manager sale total, split proportionally to each product line's regular price multiplied by quantity. Fractional residue is assigned deterministically so allocated line totals add exactly to the entered total.
- **POS calculation mode:** Per-line choice between fixed-amount and percentage-based website/no-gift POS calculation. Defaults to fixed amount.
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
- Optional manually counted on-hand quantity and count timestamp.

Product codes are not required or modeled in the MVP.

### Calculator line fields

Each calculator line supports:

- Saved product selection through a searchable multi-select catalog, or a one-off product name.
- Quantity, defaulting to one.
- Regular price used.
- Website discounted price used.
- Gift selected/not selected.
- Gift name, using the saved default or a temporary override.
- Boss discounted price for the normal website/no-gift option, when supplied.
- Boss gifted price for the gift option, when supplied.
- A manager value mode for each sale value: unit price or total line price.
- Alternatively, one transaction-wide manager total allocated by regular line totals; the employee can switch back to per-line values.
- A product-free total-only path accepts regular total, website discounted total, manager total, and fixed or percentage POS mode.

All values used in a calculation must be copied into its history snapshot. Later product edits must not change old calculations.

## 5. Price input and validation behavior

Use Python's `Decimal` for monetary arithmetic. Never use binary floating-point for prices.

The application must accept:

- Turkish-style values such as `54.999,00` and `54.999,52`.
- Plain integer values such as `54999`.
- Standard decimal values such as `54999.00`.

Values are normalized internally and displayed consistently as Turkish TRY, for example `54.999,52 TL`. General calculation display preserves the exact `Decimal` value. POS-entry amounts are the exception: round half-up to two decimal places, including gift POS amounts, and total the rounded line entries. A value representing 100 kuruş carries into the lira portion as `1,00 TL`; it must never be displayed with a three-digit kuruş portion.

Validate that:

- Product prices are numeric and non-negative.
- Quantity is a positive whole number.
- Each supplied boss price is numeric and non-negative.
- The manager value mode is explicitly recorded separately for each supplied boss price.

The application may warn when a boss price is unexpectedly greater than the applicable website amount, but it must not silently reinterpret or replace the value.

## 6. Pricing and calculation requirements

### Rule A: Website discounted price

The website discounted price is the normal price observed on the website. It is stored and used directly; the first release has no additional coupon input.

For a quantity:

```text
regular_total = regular_price × quantity
website_discounted_total = website_discounted_price × quantity
```

### Rule B: Discount scenarios

The 10%, 15%, 18%, and 20% scenarios are separate from manager prices. Each uses the selected option's discount base:

- **No gift:** use the website discounted price as the discount base.
- **Gift selected:** use the regular/first price.

```text
discount_amount = discount_base × 0.10
scenario_price = discount_base - discount_amount
```

The UI must display the base, discount amount, resulting unit price, quantity, and resulting line total.
Transaction totals display regular total, website discounted total, and each scenario total in a collapsible price-scenarios section.

### Rule C: Manager-provided sale values

The manager may provide different sale values for the two mutually exclusive customer options. The calculator must keep these values separate:

- **Boss discounted price:** the manager's price for the normal website/no-gift option.
- **Boss gifted price:** the manager's price for the gift option.

The boss prices are manual sale values, not percentages. The application must support both unit-price and total-line-price modes for each value. The website/no-gift POS calculation mode is separate:

#### Unit-price mode

The entered amount is the sale price for one product.

```text
boss_line_total = boss_unit_value × quantity
```

#### Total-line-price mode

The entered amount is the sale price for the entire calculator line.

```text
boss_line_total = boss_line_value
boss_unit_value = boss_line_value / quantity
```

The UI must clearly display which mode was used for each boss price. The application must not treat a boss price itself as a percentage or automatically assign either boss price to the product. Percentage POS mode derives its rate from the regular and website discounted prices, independently of the standard 10% scenario.

For a no-gift sale, the manager may provide a boss discounted price below the website discounted price. The examples use `112.000,00 TL` and `43.500,00 TL`.

For a gift sale, the manager may provide a separate boss gifted price. The customer must choose either the normal website/no-gift option or the gift option; the application must not combine both offers into one result.

### Rule D: Website and gift comparison

When a gift is available, show both options side by side:

1. **Website discount option**
   - Uses the website discounted price.
   - Shows the standard 10% result where applicable.
   - Shows the boss discounted price when supplied.
2. **Gift option**
   - Shows the gift name.
   - Uses the regular price as the 10% discount base.
   - Shows the boss gifted price when supplied.

The application must not decide which option the customer should choose.

Gift selection is independent for each calculator line. A transaction may contain both gift and no-gift lines.

### Rule E: POS-entry amount

The POS amount depends on the selected option.

For the normal website/no-gift option:

In **fixed-amount** mode (the default):

```text
POS line amount =
(regular line total - website discounted line total)
+ boss discounted line total
```

The formula uses the **website discounted price**.

The discount amount used by this formula is:

```text
discount amount = regular price - website discounted price
```

In **percentage** mode, derive the website discount rate from the entered prices and gross up the boss line total by the remaining website-price ratio:

```text
website discount rate = (regular price - website discounted price) / regular price
POS line amount = boss discounted line total / (1 - website discount rate)
```

Use Decimal arithmetic at the configured precision for the formula, then round the final line POS-entry amount half-up to two decimal places. If regular price is zero, use the boss line total unchanged before this POS precision step because a percentage rate cannot be derived. The selected mode applies independently to each line and is recorded in history. Sum the rounded line POS amounts for the transaction POS total.

For the gift option, the POS system workflow is different:

```text
POS gifted line amount = boss gifted line total
```

The gift price is entered as zero in the POS gift workflow, while the original product price is entered, resulting in the boss gifted price as the final POS amount. The calculator must show this as a separate gift-option POS result and must not apply the no-gift formula to it.

For quantity, regular and website discounted prices are multiplied by quantity. Each boss price is normalized to its line total according to its selected manager value mode.

The POS result must be displayed separately as:

`POS-entry calculation (verify before use)`

The application must not claim that this result is an official or manager-approved POS instruction.

For a gift sale, the selected website/no-gift POS mode has no effect. Gift POS remains the boss gifted line total.

### Rule F: Transaction totals

For multiple calculator lines:

- Calculate every line independently.
- Preserve each line's selected gift state and each supplied boss price's value mode.
- Sum corresponding line totals for transaction totals.
- Show per-line details and totals.

At minimum, show totals for regular price, website discounted option, 10% scenario, boss discounted option, boss gifted option, and the option-specific POS-entry amount when required inputs are present.

### Examples calculated by a real employee using real products

NOTE: Two offer won't work together, customer need to choose one of them, either website discounted price or gift option. So, we need to show both options side by side to let the customer choose which one they want to use.

These examples are acceptance fixtures for the calculator. Amounts are shown with Turkish separators in the UI, while the source examples may use a decimal point.

#### Example 1: no gift

- first price: 145,298.00 (learned from the website/POS)
- discounted price: 132,798.00 (learned from the website/POS)
- Last/boss price: 112,000.00 (learned from the boss/manager)
- discounted price %10: 119.518,20 (132.798,00 * 0,9)
- POS: 124,500.00 (112,000,00 + 12,500,00)
- discount: 12.500,00 (145,298.00 - 132,798.00)

Expected rules:

```text
discount amount = 145.298,00 - 132.798,00 = 12.500,00 TL
POS = 112.000,00 + 12.500,00 = 124.500,00 TL
```

#### Example 2: no gift

- first price: 54,299.00 (learned from the website/POS)
- discounted price: 48,299.00 (learned from the website/POS)
- Last/boss price: 43,500.00 (learned from the boss/manager)
- discounted price %10: 43,469.1 (48,299.00 * 0,9)
- POS: 49,500.00 (43,500.00 + 6,000.00)
- discount: 6,000.00 (54,299.00 - 48,299.00)

Expected rules:

```text
discount amount = 54.299,00 - 48.299,00 = 6.000,00 TL
POS = 43.500,00 + 6.000,00 = 49.500,00 TL
```

#### Example 3: gift and no-gift options

- first price: 53.199
- discounted price: 45.199
- boss gifted price: 48.000,00
- boss discounted price: 38,000,00
- POS gifted: 48.000,00 (POS system directly make 0 to gift price and write the 53.199, so POS system gifted is directly became the boss gifted price)
- POS without gift: 46.000,00 (38.000,00 + 8.000,00)
- discount amount: 8.000,00 TL
- gift name: TKM 9961
- gift price: 14.539
- gift discounted price: 12.399

The two offers are alternatives:

```text
discount amount = 53.199,00 - 45.199,00 = 8.000,00 TL
POS without gift = 38.000,00 + 8.000,00 = 46.000,00 TL
POS gifted = 48.000,00 TL
```

The calculator must display `TKM 9961`, `14.539,00 TL`, and `12.399,00 TL` as gift information, 
while keeping the boss gifted price (`48.000,00 TL`) and boss discounted price (`38.000,00 TL`) as separate sale inputs.

#### Example 4: percentage-based website discount

- regular/first price: `38.299,00`
- website discounted price: `34.469,10`
- boss discounted price: `30.000,00`
- POS mode: percentage
- derived rate: `(38.299,00 - 34.469,10) / 38.299,00 = 10%`
- POS: `30.000,00 / (1 - 0,10) = 33.333,333…`; POS entry shown as `33.333,33 TL` after half-up rounding to kuruş.

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
- Select gift/no-gift per line.
- Override the gift name per line.
- Enter a boss discounted price and, when a gift is available, a separate boss gifted price.
- Select unit-price or total-line-price mode for each supplied boss price.
- Show website and gift options side by side.
- Show per-line results and transaction totals.
- Show formulas, bases, input values, and warnings.
- Do not save temporary values to products automatically.

### C. Calculation history

Save immutable calculation facts in complete snapshots containing:

- Date and time.
- Product name and quantity.
- Regular and website discounted prices used.
- Gift selection and gift name.
- Boss discounted price, boss gifted price, each normalized line total, and each selected value mode.
- Website-option result.
- Gift-option result.
- 10% result.
- POS-entry result.
- Warnings and confirmation state shown at calculation time.
- Optional customer display name.

History search matches customer or product names. Confirmed deletion removes the entire snapshot and its lines together; saved facts cannot be edited.

History must remain understandable after product prices, gift promotions, or notes change.

### D. CSV import

CSV export is available before import. It writes product name, regular price, website discounted price, and known quantity. CSV import uses the required `product_name` and `regular_price` columns with optional `website_discounted_price` and `quantity`:

```text
product_name,regular_price[,website_discounted_price][,quantity]
```

If the optional website discount column is omitted or a row's value is blank, the importer stores `0`, which the application displays as “YOK”.

The importer must:

- Preview rows before applying changes.
- Accept Turkish-style and plain numeric prices.
- Validate every row and show row-specific errors.
- Ask the user for each product conflict.
- Support creating new products or updating/skipping a conflicting product according to the user's decision.
- Apply a valid import transactionally.
- Display an import summary.

CSV import does not include product codes, boss prices, gift data, or other optional fields in the MVP.

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

- Windows: `%LOCALAPPDATA%/arcelikSalesHelper/arcelikSalesHelper/`
- Linux: `$XDG_DATA_HOME/arcelikSalesHelper/`, falling back to `~/.local/share/arcelikSalesHelper/`
- Database: `arcelikSalesHelper.sqlite`; backups use the `arcelikSalesHelper-` filename prefix.
- The test/portable data-directory override is `ARCELIKSALESHELPER_DATA_DIR`.
- Keep technical storage identifiers separate from the GUI display name, currently “Arcelik Satış Yardımcısı”.

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

1. Turkish-only localization of every user-visible string.
2. Preserve existing fixed/percentage POS rules and finish exact domain arithmetic.
3. Calculator productivity: shared manager total with weighted allocation, product-free total-only mode, and retained per-line mode.
4. Catalog productivity: edit product quantity, bulk archive/restore, safe confirmed deletion, and CSV export.
5. History productivity: optional customer name, search, and confirmed whole-entry deletion.
6. CSV import preview and conflict handling, compatible with exported quantity data.
7. Verified automatic backups and Windows/Linux packaging.
8. Reservation states and reserved/available quantity, after the on-hand workflow is established.
9. Authorized scraper integration with bounded update frequency and failure reporting.
10. Multi-laptop PostgreSQL access after hosting, permissions, backups, and offline behavior are designed.

## 11. Acceptance criteria

1. The PySide6 application launches on target Windows and Linux systems and stores SQLite data in the correct per-user data directory.
2. A user can add, search, edit, archive, and restore products using product name, regular price, website discounted price, optional gift name, and notes.
3. Product codes are not required for MVP operation.
4. The application accepts `54.999,00`, `54.999,52`, `54999`, and `54999.00`, and displays them with Turkish separators and a `TL` suffix without changing their exact values.
5. General calculation display preserves exact derived decimal values, including values with more than two fractional digits; POS-entry values are rounded half-up to two fractional digits.
6. A no-gift 10% scenario uses the website discounted price as its base.
7. A gift 10% scenario uses the regular price as its base.
8. Currency formatting represents 100 kuruş as the next lira (`1,00 TL`), never as a three-digit kuruş value.
9. The calculator supports multiple product lines, quantities, and independent gift selections.
10. The calculator displays website and gift options side by side when a gift is available.
11. Separate boss discounted and boss gifted prices can be entered, each as either a unit price or a total line price, and each selected mode is visible in results and history.
12. Boss prices are not themselves converted into percentages or compounded with the separate standard 10% scenario; percentage POS mode derives its rate only from regular and website discounted prices. Boss prices are never silently assigned to a product.
13. For the website/no-gift option, fixed-amount mode calculates `(regular line total - website discounted line total) + boss discounted line total`; percentage mode derives the rate from regular and website discounted prices and gross-ups the boss line total by `1 / (1 - rate)`. Fixed amount is the default.
14. For the gift option, the POS calculation is the boss gifted line total; the gift POS workflow represents the gift price as zero and writes the original product price.
15. The POS result is visibly labeled `POS-entry calculation (verify before use)`.
16. Transaction totals correctly sum independently calculated lines.
17. A complete immutable calculation snapshot preserves all product values, quantities, gift choices, boss prices, modes, results, and warnings used at calculation time.
18. All user-visible application text is Turkish; internal identifiers and CSV field names may remain English.
19. CSV import requires `product_name,regular_price` and optionally accepts `website_discounted_price`.
20. CSV import accepts both Turkish-style and plain numeric values and asks the user per conflict.
21. Verified baseline, startup, clean-close, migration, manual, and retention backup behavior works as specified.
22. Automated tests cover parsing, exact formatting, values with more than two fractional digits, carry behavior, gift/no-gift bases, quantity calculations, both manager value modes for both boss prices, the three real examples, option-specific POS calculations, multi-line totals, immutable snapshots, Turkish presentation, CSV conflicts, and backup verification/retention.
23. Calculator users can search active products by name, select several across different queries, add them as lines in one action, and add one-off products without a per-line product dropdown.
24. A shared manager total is allocated by regular line total and the allocations sum exactly to that input; fixed and percentage POS modes still apply per line.
25. A product-free total-only calculation accepts aggregate regular, website, and manager values.
26. Product editing can record on-hand quantity; bulk archive and confirmed deletion are available, with deletion blocked when calculation history references the product.
27. History can be searched by customer/product name and a confirmed action deletes the complete entry and its lines.
28. Product CSV export can be imported again, including quantity where known.
29. Every POS line amount is rounded half-up to two decimals, and transaction POS total equals the sum of rounded line amounts.

## 12. Operational caution

The POS formula and the exact AX/POS field it represents must be validated against a real, non-sensitive workflow example before the application is used to guide an actual transaction. Until that validation is complete, POS results are informational only and must retain the verification warning.
