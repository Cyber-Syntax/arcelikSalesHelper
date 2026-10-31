# Scraping integration plan — Products tab "Güncelle"

Status: implementation plan, not code. This file replaces the earlier notes and
reference script; the script itself is not part of this document any more.

Sources: `docs/PRD.md`, `docs/implementation_plan.md`, `docs/employee_feedback.md`,
and the product/CSV-import/backup code currently in `src/arcelikSalesHelper`.

## 1. Goal

Add a **`Güncelle`** button to the Products tab that:

1. scrapes arcelik.com.tr for product names, regular prices and website
   discounted prices;
2. shows every change as old value → new value **before** writing anything;
3. takes a verified database backup before applying;
4. applies all approved changes in one transaction;
5. keeps the dialog open afterwards and shows exactly which product names and
   prices changed, with an option to export that report as CSV.

The feature is employee-triggered only. There is no background or scheduled
scraping.

## 2. Locked decisions

| Topic               | Decision                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Matching            | Normalized product name (`name_key`) only. No URL or product-code column. Product names already contain codes such as `ADE 500`.                                                                                                                                                                                                                                                                                                    |
| Renames             | Never automatic. If the website label differs, the catalog name stays unchanged.                                                                                                                                                                                                                                                                                                                                                    |
| New products        | Products found on the site but not in the catalog are always added as NEW rows. They are still visible and skippable in the preview.                                                                                                                                                                                                                                                                                                |
| Garanti items       | Ordinary products. Names such as `"ek garanti …"`, a regular price and no discount. No special column, no special UI.                                                                                                                                                                                                                                                                                                               |
| Empty scraped price | Keep the existing catalog value for that field. For a new product, store `0` (displayed as `—` for the regular price and `YOK` for the website price).                                                                                                                                                                                                                                                                              |
| Rate limit          | Hard 24-hour minimum interval and at most 5 runs per rolling 30 days. Attempts count, not only successes.                                                                                                                                                                                                                                                                                                                           |
| Backup              | Verified backup with reason `pre_scrape` before apply. If the backup fails, the apply is blocked; there is no override.                                                                                                                                                                                                                                                                                                             |
| After apply         | The dialog stays open on a result page with the full old → new table and a CSV report export.                                                                                                                                                                                                                                                                                                                                       |
| Transaction         | One transaction for the whole apply. Any error rolls everything back.                                                                                                                                                                                                                                                                                                                                                               |
| Removed discounts   | Because an empty website price means "old product", a discount removed from the site is not cleared automatically. This is shown as a row warning; the employee edits the product manually if needed which some of them can be still exists on branch. Also make sure to not override the product if already exist which some old product has product price on the current app database (e.g I added some old products and prices.) |

## 3. Scope

### In scope

- Scraper for the arcelik.com.tr sitemap, category listing pages and product
  cards, including `"ek garanti …"` items as ordinary products.
- In-memory mapping of scraped rows onto the existing CSV import pipeline.
- Products tab `Güncelle` button.
- Intro, progress, preview, apply-confirmation and result pages.
- Cooldown and quota enforcement stored in `app_metadata`.
- Verified pre-scrape backup.
- Change report (on screen and as CSV).
- Product add/edit dialog: blank regular and website prices are allowed.
- Tests, packaging and documentation.

### Out of scope

- Storing the product URL or product code(this isn't exist on website) on products.
- Automatic renaming of catalog products.
- Automatic archiving or deletion of products missing from the site.
- A whitelist/blocklist editor in Settings. The crawler gets constants and a
  clear extension point; a UI can follow later.
- Using scraped prices in the calculator automatically. The existing
  `products_changed` signal refreshes the calculator product list only.
- Any scheduled, background or multi-user scraping.
- Changing the `name_key` algorithm to be Turkish-aware. It stays as it is
  because it is shared with uniqueness constraints and CSV import.

## 4. Architecture

Reuse the existing import engine instead of creating a second update path:

1. The scraper returns a list of `ScrapedProduct` values: name, optional
   regular price, optional website price, plus URL/code/title for logging only.
2. `scrape_import` resolves the effective prices (see section 6), attaches
   warnings, deduplicates by `name_key`, and builds an in-memory `ParsedCsv`
   with the new format value `SCRAPE`.
3. `plan_import` classifies each row as NEW, CONFLICT or UNCHANGED exactly as it
   does for CSV import.
4. The dialog renders the plan in a shared preview widget with per-row
   Güncelle/Atla decisions and bulk actions.
5. The employee confirms. A verified backup with reason `pre_scrape` is taken.
6. `apply_plan` runs in one transaction and writes `pricing_history` through
   the product repository.
7. The dialog switches to the result page and builds the change report from the
   applied plan.

No database migration is required. Cooldown/quota live in the existing
`app_metadata` key-value table, and garanti items are normal products.

## 5. Components

### 5.1 `infrastructure/scraper/` (new package)

**`models.py`**

- `ScrapedProduct`: frozen dataclass with `name`, `regular_price: Decimal | None`,
  `website_price: Decimal | None`, `code`, `title`, `url`. Only `name` and the
  two prices reach the catalog; the rest is for logging and debugging.
- `ScrapeProgress`: current category, categories done, categories total,
  products found so far.
- `ScrapeOutcome`: scraped products, per-request failures, categories attempted,
  categories failed, elapsed time, `cancelled` flag, fatal error if any.
- `ScrapeError`: code (`blocked`, `network`, `parse`, `cancelled`,
  `no_products`) and a Turkish message.

**`parser.py`** — pure functions, testable from saved HTML fixtures

- Parse the sitemap index, select the `PRODUCT` sitemaps, and extract product
  URLs.
- Derive category slugs from two-segment product paths.
- Parse a listing page into product cards. Selectors are constants in one
  place, based on the reference script: the product card container, the
  product link with `aria-label` or `js-prd-url`, the product name element, the
  regular price element, the discounted price element and the
  `data-product-code` attribute.
- Remove the `" ürün detaylarını incele"` suffix from the `aria-label`, collapse
  whitespace, and fall back to the visible name element when the label is
  missing.
- Parse price text with the existing `domain.money.parse_money_ex`; return
  `None` when the card has no numeric price. No second money parser.
- Deduplicate cards by product URL inside one page.
- Detect the "page has no cards" case separately from "page failed to load", so
  the crawler can tell a legitimate end of pagination from a broken page.

**`crawler.py`**

- Async entry point that receives a progress callback, a cancellation event and
  a configuration object.
- Session: `curl_cffi` async session with browser impersonation, Turkish
  `Accept-Language`, 20-second timeout and redirects allowed.
- Politeness: concurrency limited to 2, random delay of 0.5–1.5 seconds before
  every request, four retries with exponential backoff, and no custom
  User-Agent header.
- Crawl order: sitemap index → product sitemaps → category slugs → listing
  pages. Category slugs are filtered through `SCRAPE_CATEGORY_ALLOWLIST` and
  `SCRAPE_CATEGORY_BLOCKLIST` constants. An empty allowlist means all
  categories.
- Pagination: `?page=N`, stop when a page returns no new product URLs, when a
  page repeats already seen URLs, or after the page cap. The `?page=` scheme is
  an unverified assumption from the reference script and must be checked
  against real categories during phase 1.
- Cancellation: check the event before every request and between categories.
  A cancelled run returns a partial outcome marked `cancelled`, and the dialog
  discards it.
- Failure handling:
  - individual request failures are collected and do not abort the crawl;
  - repeated 403/429 responses abort the run with `blocked`, because continuing
    would risk an IP ban;
  - a zero-product crawl returns `no_products`;
  - parse failures are counted and reported.
- Progress is reported per category and per page, so the UI can show
  `Taranıyor: <kategori> (3/48 kategori)` and the number of products found.
- Logging: start time, category counts, product count, failures, duration and
  cancellation. Never log response bodies.

**`__init__.py`**

- Exports the public scraper API and keeps `curl_cffi`/`selectolax` imports
  inside the package, so the rest of the app does not depend on them at import
  time.

### 5.2 `infrastructure/scrape_import.py` (new)

- `resolve_effective_prices(scraped, existing)` implements the mapping table in
  section 6.
- `build_scrape_parsed(scraped, existing_by_key)` returns a `ParsedCsv` with
  `ImportFormat.SCRAPE`, the effective regular/website prices, and per-row
  warnings.
- Deduplicate scraped products by `name_key`: the first occurrence wins; later
  duplicates are dropped and logged. Because product names contain codes, this
  should be rare.
- Keep the scraped values alongside the effective values so the preview can
  show both "site: boş" and "mevcut fiyat korunuyor".
- Expose a small `ScrapePlanInfo` with counts: scraped, new, conflicts,
  unchanged, rows with no price, duplicate names.

### 5.3 `infrastructure/scrape_policy.py` (new)

Pure policy functions and constants:

- `SCRAPE_MIN_INTERVAL = 24 hours`
- `SCRAPE_QUOTA_LIMIT = 5`
- `SCRAPE_QUOTA_WINDOW = 30 days`
- `SCRAPE_SUSPICIOUS_DROP_RATIO = 0.5`
- `cooldown_remaining(last_attempt, now, minimum) -> timedelta | None`
- `attempts_in_window(attempts, now, window) -> tuple[datetime, ...]`
- `quota_reached(attempts, now, limit, window) -> bool`
- `is_scrape_allowed(last_attempt, attempts, now) -> ScrapeGate` with a reason
  enum: `OK`, `COOLDOWN`, `QUOTA`.
- `is_suspicious_drop(current_count, baseline_count, ratio) -> bool`.

All functions take an injected `now`, so tests use a fake clock.

### 5.4 `infrastructure/scrape_report.py` (new)

- Write the change report as UTF-8 with BOM so Excel opens Turkish characters
  correctly.
- Columns: `product_name`, `status`, `old_regular_price`,
  `new_regular_price`, `old_website_price`, `new_website_price`.
- Escape leading formula characters exactly like `csv_export.py`.
- Prices are written with `format_decimal_exact`; empty means "not applicable"
  for a new product's old value or a skipped row.
- Return the row count, following `export_products_csv`.

### 5.5 `ui/scrape_worker.py` (new)

- `QThread`-based worker with a `run` method that calls `asyncio.run` on the
  crawler.
- Signals: `progress(object)`, `finished(object)`, `failed(str)`.
- `cancel()` sets a thread-safe event; the crawler checks it.
- Lazy-imports the scraper package and converts `ImportError` into a Turkish
  "Güncelleme bileşeni yüklenemedi" failure instead of crashing the app.
- The dialog keeps a reference to the thread and worker, and waits for the
  thread to finish before closing the dialog, so no widget is touched after
  deletion.

### 5.6 `ui/plan_preview.py` (new, extracted from `ImportDialog`)

A reusable `PlanPreviewWidget` that owns:

- the preview table (status, product name, old → new regular, old → new website,
  decision/notes);
- per-conflict `QComboBox` decisions (Güncelle / Atla, and "Güncelle ve geri
  yükle" for archived matches);
- the counts label;
- the row-error table and the "import valid rows only" checkbox;
- bulk actions: **Tümünü güncelle**, **Tümünü atla**, **Yalnızca yenileri atla**;
- `decisions()`, `ready()` and a `changed` signal.

`ImportDialog` is refactored to use this widget, so CSV import and scraping
share one implementation. The CSV dialog gains the same bulk buttons as a side
benefit, which is already requested in `docs/todo.md`.

### 5.7 `ui/update_dialog.py` (new)

A `QDialog` with a stacked layout:

1. intro page;
2. progress page;
3. preview page (uses `PlanPreviewWidget`);
4. result page.

Responsibilities:

- read the scrape gate from `scrape_policy` and show the cooldown/quota state;
- start, cancel and collect the worker;
- build the plan with `build_scrape_parsed` + `plan_import`;
- run the pre-scrape backup and block on failure;
- call `apply_plan` with the decisions;
- build and show the result table and the CSV export;
- expose `applied_summary` so the Products tab knows whether to emit
  `products_changed`.

### 5.8 Changes to existing files

| File                                       | Change                                                                                                                                                                                         |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `infrastructure/csv_import.py`             | Add `ImportFormat.SCRAPE` and its format text. The parsing path is unchanged because the scrape plan is constructed in memory. `plan_import` and `apply_plan` already handle the price format. |
| `infrastructure/backups.py`                | Add `BackupReason.PRE_SCRAPE = "pre_scrape"`. The backup filename pattern already accepts it.                                                                                                  |
| `ui/import_dialog.py`                      | Use `PlanPreviewWidget`; optionally accept a prebuilt plan so the same preview can be opened without a file.                                                                                   |
| `ui/products_tab.py`                       | Add the `Güncelle` button, the running guard, the dialog call, the reload and the new `update_finished` signal.                                                                                |
| `ui/products_tab.py` (`ProductDialog`)     | Blank regular/website price is accepted as `Decimal(0)`; blank fields do not show `MONEY_EMPTY`.                                                                                               |
| `ui/products_tab.py` (`ProductTableModel`) | Regular price `0` is displayed as `—` (unknown), website price `0` stays `YOK`.                                                                                                                |
| `ui/main_window.py`                        | Connect `products_tab.update_finished` to the backup banner refresh and the settings refresh, like `import_finished`.                                                                          |
| `strings.py`                               | Add the Turkish strings listed in section 9.                                                                                                                                                   |
| `pyproject.toml`                           | Add `curl-cffi` and `selectolax` dependencies.                                                                                                                                                 |
| `uv.lock`                                  | Regenerate with `uv lock`.                                                                                                                                                                     |
| `arcelikSalesHelper.spec`                  | Collect the native libraries and data of `curl_cffi` and `selectolax`.                                                                                                                         |
| `tests/test_ui_localization.py`            | Include the new dialog in the English-label scan.                                                                                                                                              |

## 6. Scrape → catalog mapping rules

For an existing product matched by `name_key`:

| Scraped regular | Scraped website | Result                                                                  |
| --------------- | --------------- | ----------------------------------------------------------------------- |
| value           | value           | CONFLICT if either value differs from the catalog, otherwise UNCHANGED  |
| empty           | value           | Keep the catalog regular price; update the website price if it differs  |
| value           | empty           | Update the regular price; keep the catalog website price                |
| empty           | empty           | UNCHANGED, with the warning "Sitede fiyat yok; mevcut fiyat korunuyor." |

For a product not in the catalog:

- it becomes NEW;
- a missing regular or website price is stored as `0`;
- the row warning explains that the site did not provide that price.

Archived matches:

- `plan_import` already treats an archived match as a CONFLICT;
- the decision combo offers "Güncelle ve geri yükle";
- the row is marked with the archived suffix and a warning.

Additional row warnings:

- "Sitede indirimli fiyat yok; mevcut web fiyatı korunacak." when only the
  website price is empty for an existing product;
- "Bu ürün arşivde; güncellemek geri yükler.";
- "Tarama tamamlanmadı; bu sonuçlar eksik olabilir." when the crawl was
  partial.

Rows with no price at all for an existing product still appear as UNCHANGED so
the employee can see that the product was found, not silently ignored.

## 7. UI flow

### 7.1 Products tab

- New button `Güncelle` in the bottom action row, next to `CSV'den içe aktar`.
- Tooltip: "Web sitesinden ürün adlarını ve fiyatları güncelle".
- Enabled only when both a database connection and a `BackupManager` exist.
- The dialog is modal; a `_running` flag prevents a second dialog.
- After the dialog closes:
  - always `reload()` the table;
  - if changes were applied, emit `products_changed` (refreshes the calculator
    product list);
  - emit `update_finished` so the backup banner and settings tab refresh.

### 7.2 Intro page

Shows:

- the last successful update time, or "Henüz web sitesinden güncelleme
  yapılmadı.";
- the cooldown state and the remaining time;
- the rolling quota usage (`x/5` in the last 30 days);
- the warning that the site will be contacted, that a backup is taken first,
  and that only prices and new products are changed;
- a note that the operation can take several minutes and can be cancelled;
- **Taramayı başlat** (disabled while the gate is not `OK`) and **İptal**.

### 7.3 Progress page

- Indeterminate progress bar plus a status label with the current category,
  categories done/total and products found.
- **Taramayı iptal et**.
- Cancelling discards the partial result and writes no database changes.
- If the crawl fails with `blocked`, `no_products` or `network`, the dialog
  shows the Turkish error and returns to the intro page. The attempt still
  counts toward the cooldown/quota.

### 7.4 Preview page

- Table columns: Ürün, Durum, Eski normal, Yeni normal, Eski web, Yeni web,
  Karar / notlar.
- Statuses: Yeni, Çakışma, Değişmedi, and the archived marker.
- Per-row decisions for every CONFLICT; NEW rows are applied automatically but
  can be skipped with the bulk action or an individual decision.
- Bulk actions: Tümünü güncelle, Tümünü atla, Yalnızca yenileri atla.
- Counts line: scraped, new, conflicts, unchanged, rows with no price, errors.
- Warnings are shown in the last column.
- **Değişiklikleri uygula** is enabled only when every conflict has a decision
  and there is at least one actionable row.
- If the crawl was partial, a checkbox "Kısmi sonuçları uygula" must be ticked
  before apply is enabled.
- If the site-change guard fired, apply stays disabled and the reason is shown.

### 7.5 Apply confirmation

A confirmation dialog states:

- how many products will be updated;
- how many new products will be added;
- how many archived products will be restored;
- that a verified backup is taken first;
- that gift names, notes, counted quantities and archive state are not changed
  except for the explicit restore decision.

### 7.6 Result page

- Stays open after a successful apply; the Products tab behind it refreshes.
- Table columns: Ürün, Durum, Eski normal, Yeni normal, Eski web, Yeni web.
- Statuses: Güncellendi, Yeni eklendi, Geri yüklendi, Atlandı, Değişmedi.
- A checkbox "Değişmeyenleri de göster" hides unchanged rows by default.
- Counts summary at the top.
- **Raporu CSV olarak kaydet** writes the report with a file dialog; the
  success message shows the path.
- **Kapat** closes the dialog.
- If nothing changed, show "Değişiklik yok; güncelleme uygulanmadı." and do not
  take a backup.

## 8. Safety rules

### 8.1 Backup

- Before any write, run `BackupManager.run(BackupReason.PRE_SCRAPE)`.
- If the result is an error, show the Turkish error and **do not apply**. There
  is no "continue without backup" option for scraping, because this is a bulk
  price overwrite.
- If nothing is actionable, do not take a backup.
- The existing backup banner and rotation behavior are reused unchanged.

### 8.2 Transaction

- All writes go through `apply_plan` in a single transaction.
- Any repository error aborts the whole apply and rolls back.
- `pricing_history` is written by the repository for every price change, as it
  already is for CSV import and manual edits.

### 8.3 Never touched automatically

- product names (no renames);
- default gift names;
- notes;
- counted quantities and the stock log;
- archived state, except when the employee explicitly chooses "Güncelle ve geri
  yükle" for an archived match;
- products that are not in the scrape result (never archived or deleted).

### 8.4 Guards

- **Zero products**: the crawl is considered failed; no preview.
- **Suspicious drop**: if the current product count is below 50 % of the last
  successful crawl count, apply is blocked with "Site yapısı değişmiş
  olabilir". The baseline is stored in `app_metadata` after a successful crawl.
- **Partial crawl**: apply requires the explicit "Kısmi sonuçları uygula"
  checkbox.
- **Blocked site**: repeated 403/429 aborts the crawl and starts the cooldown,
  so a retry cannot hammer the site.
- **Single run**: the modal dialog and the running flag prevent parallel runs.

## 9. Rate limiting

Stored in `app_metadata`:

| Key                         | Meaning                                                                             |
| --------------------------- | ----------------------------------------------------------------------------------- |
| `last_scrape_attempt_at`    | UTC ISO timestamp written when a run starts                                         |
| `last_scrape_success_at`    | UTC ISO timestamp written when a crawl completes without a fatal error              |
| `scrape_attempts`           | JSON array of UTC ISO timestamps for the rolling 30-day quota, pruned on read/write |
| `last_scrape_product_count` | Product count of the last successful crawl, used by the drop guard                  |
| `last_scrape_change_count`  | Number of applied changes from the last run, informational                          |

Rules:

- The cooldown uses `last_scrape_attempt_at`, so a failed or cancelled run also
  starts the 24-hour wait.
- The quota counts attempts in the rolling 30-day window, not only successes.
- The gate is evaluated when the dialog opens and again when the employee
  clicks **Taramayı başlat**.
- The intro page shows the remaining cooldown and the quota usage.
- There is no GUI override. Constants can be changed by a developer, but the
  shipped defaults are 24 hours and 5 runs per 30 days.
- Every run writes a log entry with the gate decision, start/end time, category
  count, product count, failures and cancellation state.

## 10. Turkish UI strings

Add to `strings.py`; all user-visible text must be Turkish.

| Constant                     | Text                                                                                                  |
| ---------------------------- | ----------------------------------------------------------------------------------------------------- |
| `BTN_UPDATE_FROM_SITE`       | `Güncelle`                                                                                            |
| `TIP_UPDATE_FROM_SITE`       | `Web sitesinden ürün adlarını ve fiyatları güncelle`                                                  |
| `UPDATE_TITLE`               | `Web sitesinden güncelle`                                                                             |
| `UPDATE_LAST_RUN`            | `Son başarılı güncelleme: {when}`                                                                     |
| `UPDATE_NEVER_RUN`           | `Henüz web sitesinden güncelleme yapılmadı.`                                                          |
| `UPDATE_COOLDOWN`            | `Bir sonraki güncelleme {when} tarihinden sonra yapılabilir ({remaining} kaldı).`                     |
| `UPDATE_QUOTA`               | `Son 30 günde {used}/{limit} güncelleme kullanıldı.`                                                  |
| `UPDATE_BACKUP_NOTE`         | `Değişiklikler uygulanmadan önce doğrulanmış bir yedek alınır.`                                       |
| `UPDATE_START`               | `Taramayı başlat`                                                                                     |
| `UPDATE_CANCEL`              | `Taramayı iptal et`                                                                                   |
| `UPDATE_PROGRESS`            | `Taranıyor: {category} ({done}/{total} kategori)`                                                     |
| `UPDATE_PROGRESS_DETAIL`     | `{count} ürün bulundu`                                                                                |
| `UPDATE_PREVIEW_COLUMNS`     | `Ürün, Durum, Eski normal, Yeni normal, Eski web, Yeni web, Karar / notlar`                           |
| `UPDATE_APPLY_ALL`           | `Tümünü güncelle`                                                                                     |
| `UPDATE_SKIP_ALL`            | `Tümünü atla`                                                                                         |
| `UPDATE_SKIP_NEW`            | `Yalnızca yenileri atla`                                                                              |
| `UPDATE_APPLY`               | `Değişiklikleri uygula`                                                                               |
| `UPDATE_CONFIRM`             | `{updated} ürün güncellenecek, {created} yeni ürün eklenecek. Önce yedek alınacak. Devam edilsin mi?` |
| `UPDATE_BACKUP_FAILED_TITLE` | `Yedekleme başarısız`                                                                                 |
| `UPDATE_BACKUP_FAILED`       | `Doğrulanmış yedek alınamadığı için güncelleme uygulanmadı. {message}`                                |
| `UPDATE_FAILED_TITLE`        | `Güncelleme başarısız`                                                                                |
| `UPDATE_NOTHING`             | `Değişiklik yok; güncelleme uygulanmadı.`                                                             |
| `UPDATE_SITE_CHANGED`        | `Siteden beklenenden az ürün geldi. Site yapısı değişmiş olabilir; güncelleme durduruldu.`            |
| `UPDATE_PARTIAL`             | `Tarama tamamlanmadı ({done}/{total} kategori). Kısmi sonuçlar uygulanabilir.`                        |
| `UPDATE_PARTIAL_CHECK`       | `Kısmi sonuçları uygula`                                                                              |
| `UPDATE_RESULT_TITLE`        | `Güncelleme tamamlandı`                                                                               |
| `UPDATE_RESULT_COLUMNS`      | `Ürün, Durum, Eski normal, Yeni normal, Eski web, Yeni web`                                           |
| `UPDATE_SHOW_UNCHANGED`      | `Değişmeyenleri de göster`                                                                            |
| `UPDATE_EXPORT_REPORT`       | `Raporu CSV olarak kaydet`                                                                            |
| `UPDATE_EXPORT_DONE`         | `Değişiklik raporu kaydedildi: {path}`                                                                |
| `UPDATE_STATUS_UPDATED`      | `Güncellendi`                                                                                         |
| `UPDATE_STATUS_CREATED`      | `Yeni eklendi`                                                                                        |
| `UPDATE_STATUS_RESTORED`     | `Geri yüklendi`                                                                                       |
| `UPDATE_STATUS_SKIPPED`      | `Atlandı`                                                                                             |
| `UPDATE_STATUS_UNCHANGED`    | `Değişmedi`                                                                                           |
| `UPDATE_STATUS_ERROR`        | `Hatalı`                                                                                              |
| `UPDATE_WARN_NO_PRICE`       | `Sitede fiyat yok; mevcut fiyat korunacak.`                                                           |
| `UPDATE_WARN_NO_WEBSITE`     | `Sitede indirimli fiyat yok; mevcut web fiyatı korunacak.`                                            |
| `UPDATE_WARN_ARCHIVED`       | `Bu ürün arşivde; güncellemek geri yükler.`                                                           |
| `UPDATE_WARN_PARTIAL`        | `Tarama tamamlanmadı; bu sonuçlar eksik olabilir.`                                                    |
| `UPDATE_SCRAPER_MISSING`     | `Güncelleme bileşeni yüklenemedi. Uygulamayı yeniden kurun.`                                          |
| `UPDATE_BLOCKED`             | `Site isteği reddetti (403/429). Daha sonra tekrar deneyin.`                                          |
| `UPDATE_NO_PRODUCTS`         | `Siteden hiç ürün alınamadı. Site yapısı değişmiş olabilir.`                                          |
| `PH_PRICE_OPTIONAL`          | `boş bırakılırsa bilinmiyor`                                                                          |
| `NO_PRICE`                   | `—`                                                                                                   |

The existing `NO_WEBSITE_DISCOUNT = "YOK"` and `NONE_DASH` values are reused
where they already fit.

## 11. Product dialog: empty prices

- `regular_edit` and `website_edit` may be left blank.
- Blank regular price becomes `Decimal(0)`; blank website price becomes
  `Decimal(0)`.
- Blank fields do not show the `MONEY_EMPTY` error. A hint such as
  "boş bırakılırsa bilinmiyor" is shown instead.
- The products table shows `—` for a regular price of `0` and `YOK` for a
  website price of `0`.
- This matches the existing `ProductDraft` validation, which already allows
  zero, so no domain or schema change is needed.
- Known consequence: a product with a zero regular price can still be added to
  the calculator; its totals will be zero. That is acceptable for now and is
  not changed by this feature.

## 12. Dependencies and packaging

- Add `curl-cffi` and `selectolax` to `[project].dependencies` in
  `pyproject.toml`; regenerate `uv.lock`.
- Keep both imports inside `infrastructure/scraper/` and lazy-load the package
  in the worker, so a missing native library cannot prevent the app from
  starting.
- PyInstaller:
  - collect the `curl_cffi` package, its `libcurl` shared libraries and its
    data files;
  - collect the `selectolax` package and its compiled extension;
  - verify a one-folder build on Linux and Windows, because the existing
    packaging milestone requires both.
- CI: the normal test run must not touch the network. A single
  `@pytest.mark.network` test can be run manually; it is skipped by default.
- Add a smoke check that imports the scraper package in the packaged build.

## 13. Tests

### `tests/test_scraper.py`

- Parse a saved sitemap index and product sitemaps.
- Parse listing fixtures with:
  - a product with a regular price and a discounted price;
  - a product with only a regular price;
  - a product with no price;
  - the `" ürün detaylarını incele"` suffix;
  - an `"ek garanti …"` item treated as a normal product;
  - a duplicate URL on the same page.
- Price parsing through `parse_money_ex`, including Turkish thousands and
  decimal separators.
- Crawler loop with a fake session:
  - retries and backoff on transient errors;
  - abort on repeated 403/429;
  - stop pagination when a page repeats;
  - cancellation returns a partial outcome;
  - zero products returns `no_products`.
- One optional network test, marked `network`, skipped by default.

### `tests/test_scrape_import.py`

- Effective-price rules from section 6, including both empty fields.
- New product with empty prices becomes `0`.
- Archived match becomes CONFLICT with the restore option.
- Deduplication by `name_key`.
- Warnings are attached to the right rows.
- `plan_import` classification for NEW / CONFLICT / UNCHANGED.
- `apply_plan` updates prices, writes `pricing_history`, adds new products and
  restores an archived product only when chosen.
- Forced mid-apply failure rolls everything back.

### `tests/test_scrape_policy.py`

- Cooldown boundary at exactly 24 hours and just below/above it.
- Rolling 30-day quota with fake timestamps.
- Failed attempts count toward the quota.
- Suspicious-drop guard at the 50 % boundary and with no baseline.

### `tests/test_update_dialog.py`

- Intro page shows the gate state and disables start during cooldown/quota.
- Preview shows old → new values and the product names.
- Per-row decisions and bulk actions.
- Apply is disabled until every conflict is decided.
- Backup is called exactly once, before `apply_plan`, with `PRE_SCRAPE`.
- Backup failure blocks the apply.
- No backup is taken when there are no changes.
- Result page lists the changed names and prices.
- CSV report export writes the expected columns.
- Cancellation during progress discards the result and writes nothing.

### `tests/test_ui.py` and `tests/test_ui_localization.py`

- `Güncelle` button exists with the exact Turkish text.
- The button is disabled when the connection or backup manager is missing.
- The new dialog contains no English labels.
- Product dialog accepts blank prices and the table shows `—` / `YOK`.

### Coverage

The project requires at least 80 % coverage. Network-only branches are either
covered through a fake session or excluded with a documented pragma; the
preference is a fake session.

## 14. Documentation updates

- `docs/implement_scrapping.md`: this plan (replaces the earlier notes and
  script).
- `docs/implementation_plan.md`:
  - change the "Website scraping" row from Deferred to Implemented
    (employee-triggered, rate-limited);
  - add a milestone section with the scope and exit checks from this plan;
  - update the "Later milestones" bullet that currently defers scraping.
- `docs/PRD.md`: add a short deviation note, because the PRD says the GUI must
  not depend on scraping behavior or anti-bot workarounds. Record that scraping
  is an optional, isolated, employee-triggered integration with hard rate
  limits, and that the app still works fully without it.
- `docs/todo.md`:
  - mark "allow csv import without money" as done once the product dialog
    change lands;
  - add the scraping item and its status.
- `CHANGELOG.md`: entry for the new feature, the new dependencies and the
  backup reason.
- `README.md`: short note that the update feature needs network access and is
  rate-limited.

## 15. Implementation phases

### Phase 1 — scraper core

- Add dependencies.
- Implement models, parser and crawler.
- Add HTML/sitemap fixtures and parser/crawler tests.
- Verify the real pagination and selectors against a few categories with a
  manual network run.

Exit check: a manual run produces a plausible product list with names and
prices, and the fixture tests pass without network access.

### Phase 2 — mapping and plan

- Implement `scrape_import`.
- Implement the empty-price rules and warnings.
- Reuse `plan_import` and `apply_plan`.
- Add mapping and apply tests, including rollback.

Exit check: a scraped list becomes a correct NEW/CONFLICT/UNCHANGED plan and
applies atomically.

### Phase 3 — policy and bookkeeping

- Implement `scrape_policy`.
- Write and read the `app_metadata` keys.
- Add fake-clock tests.

Exit check: cooldown and quota block the right runs, and a failed attempt still
counts.

### Phase 4 — shared preview and dialog

- Extract `PlanPreviewWidget` from `ImportDialog`.
- Refactor `ImportDialog` to use it.
- Implement `UpdateDialog` with the four pages.
- Implement the worker and cancellation.

Exit check: the full flow works against a fake scraper result; no network is
needed for the UI tests.

### Phase 5 — Products tab and result report

- Add the `Güncelle` button and signals.
- Wire the backup and the result page.
- Implement the CSV report.
- Refresh the products table and the calculator.

Exit check: applying a fake plan updates the table, writes pricing history,
creates a backup, and shows the old → new report.

### Phase 6 — packaging, docs and validation

- Update the PyInstaller spec.
- Build and smoke-test on Linux and Windows.
- Update the docs listed in section 14.
- Run `ruff`, `mypy`, `pytest` with the coverage threshold.
- Do one controlled real run on a small category set, then a full run only
  after the preview looks correct.

Exit check: packaged app starts, the scraper imports, and the full flow works
with a real backup.

## 16. Risks and mitigations

| Risk                                                   | Mitigation                                                                                                                                                         |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Company IP gets banned                                 | Hard 24-hour cooldown, 5 runs per 30 days, concurrency 2, jitter, retries with backoff, abort on repeated 403/429, employee-triggered only, no background runs.    |
| The site's terms or the PRD's anti-bot rule            | The integration is isolated, optional and documented as a deviation. Confirm with the company that scraping is allowed before enabling it in production.           |
| Site markup changes                                    | Selectors live in one module; fixture tests; a zero-product crawl is treated as a failure, not as "everything is gone"; the drop guard blocks a suspicious result. |
| Pagination assumption is wrong                         | Verify `?page=` against real categories in phase 1; log per-category counts; stop safely when a page repeats.                                                      |
| A wrong category floods the catalog with new products  | Category allow/blocklist constants; the preview lists every NEW row; bulk "Yalnızca yenileri atla"; the apply confirmation states the new-product count.           |
| A website rename creates a duplicate product           | Accepted for now because names contain codes. The preview shows the new name; the employee can skip it or rename manually.                                         |
| Empty discount keeps a stale website price             | Explicit row warning; the employee can edit the product manually. Documented in this plan and in the dialog text.                                                  |
| Turkish `name_key` mismatch (`I`/`ı`/`İ`)              | The catalog and the website use the same Turkish names; test with real data. Do not change `name_key` without a separate migration and uniqueness review.          |
| Long crawl blocks the UI                               | Worker thread, progress, cancel, and a note on the intro page.                                                                                                     |
| `curl_cffi` native library missing in a packaged build | `collect_all` in the spec, lazy import, clear Turkish error, smoke test on both operating systems.                                                                 |
| Backup fails mid-flow                                  | Hard stop before any write; the existing failure banner is refreshed.                                                                                              |
| Partial crawl applied as if complete                   | The "Kısmi sonuçları uygula" checkbox is required, plus a row warning.                                                                                             |

## 17. Acceptance criteria

- The Products tab shows a `Güncelle` button with the exact Turkish text.
- The button is disabled without a database connection or backup manager.
- A run is blocked during the 24-hour cooldown and after 5 attempts in 30 days.
- The intro page shows the last success, the cooldown and the quota.
- The progress page shows category progress and can be cancelled.
- The preview shows every scraped product with its name, status and old → new
  regular/website prices.
- Conflicts require a decision; bulk actions work; new products can be skipped.
- Nothing is written before the apply confirmation.
- A verified `pre_scrape` backup is created before the first write; a backup
  failure blocks the apply.
- The apply is one transaction and rolls back completely on failure.
- Gift names, notes, counted quantities and archive state are unchanged unless
  the employee explicitly chose to restore an archived product.
- Empty scraped prices keep the existing values; new products store `0`.
- The result page shows the changed product names and prices and can export the
  report as CSV.
- The products table and the calculator refresh after an apply.
- All new text is Turkish and the localization tests pass.
- `ruff`, `mypy` and `pytest` pass with the coverage threshold.
- The docs listed in section 14 are updated.
