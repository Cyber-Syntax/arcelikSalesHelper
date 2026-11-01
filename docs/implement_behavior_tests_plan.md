# Behavior Test Implementation Plan

**Status:** Active alpha testing plan  
**Scope:** Employee-visible behavior and stable business rules

## 1. Purpose

The application is still changing direction based on employee feedback.
SQLite may later be replaced by PostgreSQL, and UI, service, and module
boundaries may change. Tests must protect useful behavior without freezing the
current implementation.

The primary test question is:

> Can an employee complete the workflow and get the correct, safe result?

Tests should not require the current class names, SQL statements, widget
layout, or storage implementation unless those details are themselves a
requirement.

## 2. Testing principles

- Prefer behavior-focused integration tests over broad implementation
  coverage.
- Keep pure business-rule tests where the rule is stable and inexpensive to
  verify.
- Test complete workflows with realistic inputs and observable results.
- Use local fixtures and deterministic data; never depend on the live website
  in automated tests.
- Test failure and cancellation behavior, not only the successful path.
- Replace tests when the workflow changes instead of preserving obsolete
  assertions.
- Do not add tests solely to increase a coverage percentage.
- Keep test data non-sensitive and representative of employee usage.

## 3. Test layers

### 3.1 Stable business rules

Keep focused tests for rules that should survive architectural changes:

- Decimal price calculations and rounding.
- Website, manager, gift, and POS calculation rules.
- Product-name normalization and matching.
- Empty or missing price behavior.
- Import decisions: new, update, skip, unchanged, restore, and duplicate.
- Scrape cooldown, quota, cancellation, partial-result, and drop protection.
- Validation of required fields and invalid money values.

These tests should use plain values and avoid Qt, database connections, and
network requests.

### 3.2 Workflow integration tests

Prioritize tests that exercise an application workflow from input to result:

- Import a realistic CSV, preview its changes, approve selected rows, and
  verify the resulting catalog.
- Confirm that skipping conflicts preserves existing prices.
- Confirm that cancellation, backup failure, validation failure, or apply
  failure writes no partial product changes.
- Scrape fixture sitemap and listing pages, map products and prices, preview
  the changes, and apply them only after confirmation.
- Verify duplicate names, missing prices, malformed cards, pagination, page
  caps, partial crawls, and suspicious drops.
- Verify that every started crawl, including failed and cancelled runs, records an attempt and consumes cooldown/quota, while only an applied update records the update result.
  without an apply does not appear as a successful update.
- Calculate a realistic multi-product transaction and verify the visible
  totals, allocation, and POS-entry values.
- Save a calculation, reopen it from history, and verify that the stored
  snapshot remains unchanged when current product prices change.

The persistence adapter should be replaceable. When the project moves from
SQLite to PostgreSQL, keep these scenarios and change only the test fixture
that provisions the database.

### 3.3 Small UI behavior checks

Use GUI tests only for important user-visible boundaries:

- The employee can start the workflow from the relevant tab.
- Preview is shown before product data changes.
- Apply is disabled when there is no effect or when a required safety gate is
  not satisfied.
- Cancel returns to a safe screen and leaves product data unchanged.
- Important errors, warnings, and confirmation messages are visible.
- The main calculator and update result show the required Turkish labels and
  values.

Do not assert widget geometry, incidental labels, internal signal wiring, or
private helper calls unless they express a user requirement.

## 4. Fixtures and test data

Use deterministic fixtures for:

- Representative product catalog records.
- CSV files with valid, blank, duplicate, malformed, and legacy rows.
- Sitemap XML and category HTML containing regular products, discounted
  products, warranty products, missing prices, duplicate cards, and malformed
  cards.
- Employee calculation examples with one and multiple products.

Keep fixtures small and readable. Each fixture should explain the behavior it
represents. Do not make automated tests call the production website.

## 5. Priority scenarios

### Priority 1: safety and data integrity

1. Preview does not modify the catalog.
2. Approved changes apply together.
3. Skipped changes remain unchanged.
4. Backup, validation, cancellation, and apply failures do not partially
   modify the catalog.
5. A suspicious or incomplete scrape cannot be applied accidentally.

### Priority 2: employee workflows

1. CSV import works for a realistic catalog update.
2. Web update works from fixture pages through preview and apply.
3. Calculator results match approved employee examples.
4. History preserves the original calculation snapshot.

### Priority 3: edge cases

1. Missing or zero prices.
2. Duplicate and renamed products.
3. Pagination and page limits.
4. Empty results, malformed source data, and network failures.
5. Turkish formatting and user-visible warnings.

## 6. Handling the current test suite

The existing suite is migration material, not a permanent coverage contract.

- Keep passing tests that protect stable business behavior.
- Rewrite tests that describe a changed employee workflow.
- Remove tests that only duplicate implementation details.
- Isolate or defer tests for features whose requirements are still undecided.
- Do not spend alpha development time repairing unrelated brittle tests when
  the behavior they assert is no longer required.
- Before a release or major migration, run the Priority 1 and Priority 2
  scenarios as the acceptance gate.

## 7. Definition of done for a behavior change

A behavior change is ready when:

1. The living product or implementation document describes the intended
   behavior.
2. At least one realistic behavior test covers the main path.
3. Important failure or cancellation paths are covered when data safety is
   involved.
4. The test does not depend unnecessarily on the current storage or module
   structure.
5. Employee feedback and changed expectations are reflected in the scenario
   or fixture.
