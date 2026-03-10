# Cognitive Folio – AI Agent Instructions

## Overview
Cognitive Folio is a Frappe application for AI-optimized portfolio management, integrating security analysis, price tracking, news monitoring, and conversational chat via OpenAI/OpenWebUI. The app uses background jobs for long-running AI operations, real‑time notifications, and a custom variable‑substitution system for injecting financial data into prompts.

## Architecture & Key Components
- **Core Doctypes**: `CF Security`, `CF Portfolio`, `CF Portfolio Holding`, `CF Chat`, `CF Chat Message`, `CF Settings`, `CF AI Model`, `CF Prompt`, `CF Transaction`, `CF Dividend`.
- **AI Integration**: Centralized settings in `CF Settings` (OpenWebUI endpoint, API key, system prompt, model list). All AI calls use the `openai` Python package configured with `base_url` and `api_key`.
- **Background Jobs**: Long‑running AI tasks run on the `long` queue (30‑min timeout). Enqueue via `frappe.enqueue` or `frappe.utils.background_jobs.enqueue`.
- **Real‑time Events**: Use `frappe.publish_realtime` with event names `cf_job_completed` and `cf_streaming_update`. Include relevant IDs (`security_id`, `portfolio_id`, `chat_id`, `message_id`) in the payload.
- **Per-message context switch**: `CF Chat Message.implicit_chat_context` (`Use Connected Context`) controls whether linked security/portfolio context is injected into plain prompts.
- **Variable Substitution**: Prompts can contain `{{field}}` or `{{field.nested.path}}` placeholders that are replaced using `cognitive_folio.utils.helper.replace_variables`. Supports JSON fields and wildcards (`{{field.ARRAY.key}}`).

## AI Generation Flows
### Security‑Level AI
1. User triggers `CF Security.generate_ai_suggestion()` → queues `process_security_ai_suggestion` on `long` queue.
2. Background job fetches settings, builds prompt with variable substitution, calls OpenAI/OpenWebUI.
3. On success: creates a `CF Chat` and `CF Chat Message` record for audit, updates security fields (`ai_suggestion`, `suggestion_action`, etc.), commits, and emits `cf_job_completed` (success).
4. On error: logs via `frappe.log_error`, updates security with error message, emits `cf_job_completed` (error).

### Portfolio‑Level AI
- `CF Portfolio.generate_portfolio_ai_analysis()` → queues `process_portfolio_ai_analysis`.
- Similar pattern: uses portfolio’s `ai_prompt`, injects target‑vs‑actual allocations, saves HTML suggestion, creates chat audit trail, notifies via real‑time event.

### Chat Messages
- `CF Chat Message.process()` enqueues `process_in_background` → calls `send()`.
- `send()`: manages token budget with `tiktoken`, replays previous messages newest‑first, runs tool-orchestrated completion, and persists final response/tokens/runtime audit.
- `process_in_background()`: sets status to `Processing`, calls `send()`, then finalizes to `Success` (or `Failed` on errors) and emits `cf_job_completed`.
- Supports optional URL embedding (`fetch_urls`), PDF extraction.
- Supports optional connected-context prompt injection (`implicit_chat_context`) for chats linked to a security/portfolio.
- **Agentic tool calls**: `send()` always routes through the tool-call chain. The chain loops up to `max_tool_rounds`, executing tool calls and feeding results back until the model produces a final text answer.
- **Available tools**: `get_security_snapshot`, `get_portfolio_holdings`, `get_latest_security_news`, `web_search` (DuckDuckGo + Wikipedia, with `date_range`/`domain_filter`/`result_type`), `search_financial` (SEC EDGAR, Yahoo Finance, financial news), `fetch_url_content`.
- **Thinking mode / DeepSeek-Reasoner**: enabled via `model=deepseek-reasoner` or `thinking_enabled` setting. `_get_thinking_config` injects `extra_body={"thinking": ...}`. `reasoning_content` is preserved within a tool-call chain but stripped via `_clear_reasoning_content` at the start of each new user turn. A lightweight `_content_looks_like_dsml` sentinel catches the rare case where the model emits DSML markup instead of structured `tool_calls`, discarding the markup and triggering a forced synthesis pass.
- **Lifecycle cleanup**: `CF Chat Message.on_trash()` and `.on_cancel()` detach noncritical monitoring/compliance links so cancel/delete actions are not blocked by linked analytics records.

### Connected Context Injection
- Controlled by `CF Chat Message.implicit_chat_context` (checkbox).
- When enabled and chat is linked, prompt preamble may include:
`security.symbol`, `security.security_name`, `security.security_type`, `security.currency`, `portfolio.name`, `portfolio.base_currency`/`currency`, `portfolio.risk_profile`.
- Injection is skipped when explicit template tokens already exist in prompt (`{{...}}`, `((...))`, `[[...]]`, `***HOLDINGS***`).
- Runtime observability is recorded in `runtime_audit.context_injection` (`enabled`, `enabled_source`, `applied`, `fields_used`, `chars_added`, `reason`).

### Batch News Evaluation
- Scheduled task `auto_evaluate_holdings_news` runs daily at 4 AM for portfolios with `auth_fetch_prices` enabled.
- Calls `CF Portfolio.evaluate_holdings_news()` which queues a background job per holding.

## Tool Call Chain & Thinking Mode
- **`_run_tool_call_chain`**: core agentic loop. Sends completion requests, executes returned tool calls, appends results, repeats. A synthesis nudge is injected 2 rounds before `max_tool_rounds`; on the final round `tools` is omitted entirely to force a text response.
- **DeepSeek-Reasoner DSML fallback**: if the model emits DSML markup (`<｜DSML｜…>`) in `content` instead of `tool_calls` (can happen when tools are absent on the last round), `_content_looks_like_dsml` detects it, the markup is discarded, and the post-loop forced synthesis call produces the real answer.
- **Multi-turn thinking**: `reasoning_content` is included in assistant messages within the same tool-call chain (required by the DeepSeek API). Before a new user turn, `_clear_reasoning_content` strips it from history to save bandwidth and avoid a 400 error.
- **Unsupported params**: `_strip_unsupported_request_params` dynamically removes parameters rejected by the endpoint (e.g. `temperature`, `top_p`, `seed`, `extra_body`) and retries automatically.

## Background Jobs & Queue Management
- Always use `queue="long"` and `timeout=1800` (30 minutes) for AI operations.
- Provide a unique `job_id` (e.g., `f"security_ai_suggestion_{self.name}_{frappe.utils.now()}"`) to prevent duplicate jobs.
- After enqueuing, show a user message: `_("AI suggestion generation has been queued. You will be notified when it's complete.")`.
- Use `frappe.db.commit()` after saving documents that will be read by the background job.

## Error Handling & Logging
- **Always wrap AI API calls in try‑except** and catch `requests.exceptions.RequestException` and generic `Exception`.
- Log errors with descriptive titles: `frappe.log_error(title="OpenWebUI API Error", message=str(e))`.
- Update the relevant document with an error indicator (e.g., `❌ **Error generating AI analysis**: {error}`) and set `status = "Failed"`.
- Notify the user of failures via `cf_job_completed` event with `status: 'error'`.
- For background jobs, ensure errors are logged even if the job crashes, and always attempt to update the document status.

## Real‑time Notifications
- Use `frappe.publish_realtime(event='cf_job_completed', ...)` to inform the frontend that a job finished.
- Include `user=frappe.session.user` to target the specific user.
- Payload must contain at least `status` ('success'/'error'), a human‑readable `message`, and the relevant ID (security_id, portfolio_id, chat_id).
- For tool-loop progress updates (when emitted), use `cf_streaming_update` with partial `message` and `reasoning` fields.

## Variable Substitution System
- Placeholders in prompts are replaced by `replace_variables(match, doc)`.
- Supports dot notation for JSON fields: `{{financial_data.balance_sheet.0.totalAssets}}`.
- Wildcard `ARRAY` returns comma‑separated values: `{{financial_data.ARRAY.totalAssets}}`.
- Variables are resolved from the document (`CF Security`, `CF Portfolio`, etc.) passed as the `doc` argument.
- See `cognitive_folio.utils.helper` for implementation details.

## Dependencies & Configuration
- **Python packages**: `yfinance`, `openai`, `edgartools`, `duckduckgo-search`, `tiktoken`. Installed automatically via `install.after_install`.
- **Frappe hooks**: Scheduled tasks defined in `hooks.py` (`scheduler_events`).
- **CF Settings**: Single‑doctype configuration for OpenAI/OpenWebUI endpoint, API key, system prompt, and model list. Use `settings.get_password('open_ai_api_key')` to retrieve the encrypted key. Also configures tool-call behaviour (`max_tool_rounds`, `max_tool_calls_per_round`, `tool_result_max_chars`) and web search (`web_search_providers`, `web_search_max_results`, `web_search_financial_domains`) and thinking mode (`thinking_enabled`, `thinking_type`, `thinking_budget_tokens`).
- **Model selection**: `default_ai_model` from settings; fallback to `"deepseek-reasoner"` if not set to favor more reliable complex financial analysis.

## Development Workflow
- **Pre‑commit**: Uses ruff (import sorting, linting, formatting), prettier (JavaScript/SCSS), eslint. Run `pre‑commit install` in the app directory.
- **Background workers**: Start with `bench worker --queue long` in a separate terminal during development.
- **Installation**: After `bench get‑app`, run `bench install‑app cognitive_folio` (triggers `after_install` which installs Python dependencies).

## Code Style & Conventions
- **Python**: Follow ruff rules (line‑length 110, target‑version py310). Use `snake_case` for functions/variables, `CamelCase` for classes.
- **JavaScript**: Prettier + eslint. Use `frappe.call` for AJAX, `frappe.msgprint` for user feedback.
- **DocTypes**: Keep controller files slim; move complex logic to utility modules. Use `@frappe.whitelist()` for exposed methods.
- **Error messages**: User‑friendly messages with `_()` translation wrapper. Log technical details with `frappe.log_error`.
- **Commit messages**: Conventional commits preferred.

## Common Pitfalls & Reminders
- **Token budgeting**: Always reserve space for response (~60k total context). Use `tiktoken` to count tokens, replay messages newest‑first.
- **Status finalization**: Ensure every background run transitions out of `Processing` to `Success` or `Failed`.
- **Prompt context safety**: Keep implicit connected-context concise and do not apply when explicit template tokens are present.
- **Duplicate jobs**: Use unique `job_id` based on document name and timestamp.
- **Missing dependencies**: If `openai` import fails, log instructions to run `bench pip install openai`.
- **SEC EDGAR integration**: Uses `edgartools`; CIK lookup via `CF Security.fetch_cik()`.
- **Yahoo Finance**: Guard with `YFINANCE_INSTALLED` flag; fallback gracefully.

## References
- `cognitive_folio/utils/helper.py` – variable substitution, JSON cleaning.
- `cognitive_folio/utils/url_fetcher.py` – URL embedding.
- `cognitive_folio/utils/markdown.py` – safe markdown‑to‑HTML conversion.
- `cognitive_folio/tasks.py` – scheduled tasks.
- `cognitive_folio/hooks.py` – app hooks, scheduler events.
- `cognitive_folio/install.py` – dependency installation.