### Cognitive Folio

AI-Optimized Investing, Thoughtfully Engineered

---

## Table of Contents

- [Installation](#installation)
- [Financial Data Architecture](#financial-data-architecture)
- [Quick Start Guide](#quick-start-guide)
- [API & Developer Reference](#api--developer-reference)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app cognitive_folio
```

### Required Dependencies

```bash
# Core dependencies (required for all stocks)
cd frappe-bench
./env/bin/pip install yfinance openai

# SEC Edgar integration (required for US stocks only)
./env/bin/pip install sec-edgar-downloader python-xbrl lxml pdfplumber
```

---

## Financial Data Architecture

### Current Scope: US Stocks Only for Regulatory Filings

⚠️ **Important**: The current implementation focuses on **US-listed companies** for SEC Edgar integration. This provides:
- **High-quality data** from regulatory filings (10-K, 10-Q) with quality score 95
- **Automatic XBRL parsing** from SEC Edgar inline XBRL HTML files
- **Fallback to Yahoo Finance** (quality score 85) for non-US stocks or when SEC data is unavailable

**Future Phases**: Integration with Hong Kong (HKEX), UK (Companies House), EU (ESEF), Canada (SEDAR+), Japan (EDINET), and Australia (ASIC) regulatory databases are planned but not yet implemented.

### Why Structured Financial Data?

**Benefits:**
- ✅ **Consistent Format** - All companies use the same field structure
- ✅ **Historical Tracking** - Built-in time series with automatic YoY growth calculations
- ✅ **AI Efficiency** - Clean queries reduce token usage and improve response speed
- ✅ **Automatic Calculations** - Margins, ratios, and growth metrics computed on save
- ✅ **Data Quality** - Type enforcement, validation rules, and audit trails
- ✅ **Multi-Source Support** - SEC Edgar (US only), Yahoo Finance (global), PDFs, or manual entry

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/cognitive_folio
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
