# Project Guidelines

## Product direction

This is an alpha employee productivity application. Requirements, workflows,
and architecture may change after employee feedback.

[docs/PRD.md](docs/PRD.md) and
[docs/implementation_plan.md](docs/implementation_plan.md) are living
documents. Read them before making changes that affect product behavior, and
update them when a decision or workflow changes.

## Basic behavior

- The calculator must show correct, understandable price results.
- Product and history data must be preserved unless the user explicitly
  changes or deletes it.
- Imports and web updates must preview changes before writing them.
- Approved changes must be applied consistently; rejected, cancelled, failed,
  or blocked operations must not partially change product data.
- User-visible text is Turkish unless the living product documents explicitly
  change that decision.
- Scraping is employee-triggered. It must handle missing prices, duplicates,
  partial results, rate limits, cancellation, and source changes without
  silently corrupting the catalog.

## Testing

Prefer behavior-focused integration tests over tests coupled to internal
classes, widget layout, SQL statements, or module structure. Test what an
employee can observe and what the business workflow guarantees.

Keep a small set of stable domain-rule tests for calculations, validation,
matching, price handling, and scrape policy. Use representative fixtures for
scraping and import workflows. When the persistence layer changes, preserve
the behavior scenarios and replace the storage-specific test setup.

See [docs/implement_behavior_tests_plan.md](docs/implement_behavior_tests_plan.md)
for the testing approach and priority scenarios.
