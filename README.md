# arcelikSalesHelper
# Development

To run a scrape again without waiting for the normal 24-hour cooldown, set
the development override before starting the application:

```bash
ARCELIK_SCRAPE_MIN_INTERVAL_SECONDS=0 uv run arcelikSalesHelper
```

The value is a non-negative number of seconds. The five-attempt rolling
30-day quota is not disabled by this override.
