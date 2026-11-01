# arcelikSalesHelper
# Development

To run a scrape again without waiting for the normal 24-hour cooldown, set
the development override before starting the application:

```bash
ARCELIK_SCRAPE_MIN_INTERVAL_SECONDS=0 uv run arcelikSalesHelper
```

The value is a non-negative number of seconds. The five-attempt rolling
30-day quota is not disabled by this override.

Scraper diagnostics are written to the application's rotating log file. Search
for `scrape started`, `category page started`, `category page parsed` and
`scrape diagnostics`; the crawl ID in brackets connects related entries.
