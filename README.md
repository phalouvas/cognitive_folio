### Cognitive Folio

AI-Optimized Investing, Thoughtfully Engineered

**What it does**: Portfolio management with AI-powered security analysis, price tracking, news monitoring, and conversational chat via OpenAI/OpenWebUI.

**Key Features**:
- Fetch prices & news for securities (yfinance)
- Generate AI suggestions & valuations
- Portfolio-level analysis with batch operations
- Chat with conversation history & export
- SEC Edgar financial data integration

### Quick Start

**Install**:
```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app cognitive_folio
```

**Dev Setup**:
```bash
cd apps/cognitive_folio
pre-commit install
```

**Configure** (in `CF Settings`):
- Set OpenAI/OpenWebUI endpoint URL & API key
- Test connection → auto-populate available models
- Set system prompt & URL-fetch limits

**Run**:
```bash
bench --site tmp.localhost migrate
bench start                         # Dev server
bench worker --queue long           # Background jobs in separate terminal
```

### Documentation

- **[Copilot Instructions](.github/copilot-instructions.md)** — Full technical details (AI flows, prompt templating, financial variables, debugging)
- **[Pre-commit]** — Uses ruff, eslint, prettier, pyupgrade

### License

mit

