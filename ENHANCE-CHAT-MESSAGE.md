# Chat Message Enhancement Implementation Plan

## Overview
This document outlines a step-by-step implementation plan for enhancing the `CFChatMessage` functionality in the Cognitive Folio application. The current implementation in `/workspace/development/v16/apps/cognitive_folio/cognitive_folio/cognitive_folio/doctype/cf_chat_message/cf_chat_message.py` is robust but has grown to ~2,200 lines with multiple responsibilities. This plan focuses on modularization, improved agent capabilities, and enhanced web search functionality.

## Implementation Status (Updated: 2026-03-07)

### Completed
1. **Phase 1.1 (Base Service Classes)**
	- `PromptProcessor` created
	- `TokenManager` created
	- `ToolOrchestrator` created
	- `WebSearchService` created
	- `SettingsManager` created
2. **Phase 1.2 (Refactor CFChatMessage Class) - mostly complete**
	- Core logic extracted/delegated to services
	- Imports and wiring updated
	- Legacy compatibility wrappers removed to reduce code
3. **Phase 1.3 (Configuration Manager) - completed**
	- Typed/validated settings access centralized in `SettingsManager`
	- Runtime schema validation added
	- Environment-specific overrides implemented
	- Feature flags JSON support implemented
4. **Web Search Path Simplification**
	- Old non-tool web search path removed
	- Search is now tool-only (`web_search` and `search_financial` tools)
5. **Tool Mode Simplification**
	- `Enable Tool Calls` setting removed from `CF Settings`
	- Tool chain is now always enabled
6. **Phase 3 (Web Search Enhancement) - completed (scoped)**
	- Step 3.1 completed with ProviderRegistry, SerpAPI integration, and SEC real-time filings support under `sec_edgar`
	- Step 3.2 search quality stack completed (refiner, reranker, freshness, cross-source, authority)
	- Step 3.3 advanced search features completed (session tracker, semantic, trend, personalized)
7. **Phase 4 (Performance & Reliability) - completed (feature-flagged)**
	- Step 4.1 caching stack completed (search result cache, content summarization cache, tool result cache, predictive prefetch)
	- Step 4.2 resilience stack completed (circuit breaker, rate limiter, graceful provider fallback behavior, health snapshot)
	- Step 4.3 DB optimization stack completed (batch writer integration, connection/index/query optimization utilities, scheduled index maintenance)

### Partially Completed
1. **StreamingHandler usage**
	- Service exists, but the direct streaming fallback path was removed in favor of tool-only execution.
2. **Phase 2.1 (Agent Planning System)**
	- `QueryAnalyzer`, `ToolRecommender`, `PlanGenerator`, and `PlanExecutor` implemented.
	- `ToolOrchestrator` now performs pre-execution analysis and plan generation and stores plan metadata in runtime usage/audit.
	- Follow-up needed: calibration of intent heuristics and broader integration tests in environments without third-party preload regressions.

### Not Started
1. **Phase 5, Phase 6**
	- Security/compliance and monitoring/dashboard phases remain pending.
2. **Remaining Phase 2 completion work**
	- Phase 2.1 planner calibration in broader environments and Phase 2.3 memory-system completion beyond MVP.

### Scope Decisions Applied
1. **Backward compatibility is intentionally not preserved** for removed helper APIs and old fallback flows.
2. **Single execution strategy**: tool-orchestrated response generation only.

## Current State Analysis
The `CFChatMessage` class currently handles:
- Prompt processing with variable replacement
- PDF extraction and table conversion
- Web search across multiple providers (DuckDuckGo, Wikipedia, SEC EDGAR)
- Tool calling with caching and retry logic
- Streaming responses with real-time updates
- Token management and conversation summarization
- Error handling and audit logging

## Implementation Goals
1. **Modularize the monolithic class** into focused, testable components
2. **Enhance agent intelligence** with better tool selection and planning
3. **Improve web search reliability** with fallbacks and quality filtering
4. **Add advanced features** like vector memory and knowledge graphs
5. **Optimize performance** with better caching and database operations

## Phase 1: Foundation & Modularization (Week 1)

### Step 1.1: Create Base Service Classes
Create new Python modules in `/workspace/development/v16/apps/cognitive_folio/cognitive_folio/services/`:

1. **PromptProcessor** - Handle prompt variable replacement, PDF extraction, and content augmentation
2. **TokenManager** - Manage token counting, conversation trimming, and summarization
3. **ToolOrchestrator** - Coordinate tool execution, caching, and chaining
4. **WebSearchService** - Multi-provider search with fallback and quality filtering
5. **StreamingHandler** - Real-time response streaming with database optimization

Status: **Completed** (with later simplification to tool-only runtime path)

### Step 1.2: Refactor CFChatMessage Class
1. Extract existing functionality into the new service classes
2. Maintain backward compatibility with existing API
3. Update imports and dependencies
4. Add dependency injection for service classes

Status: **Completed with scope change**

Note: Item 2 is intentionally superseded. Backward compatibility wrappers were removed to reduce code size and maintenance overhead.

### Step 1.3: Create Configuration Manager
1. **SettingsManager** - Centralize all configuration access with validation
2. Add schema validation for all settings
3. Implement feature flags for gradual rollouts
4. Add environment-specific configuration support

Status: **Completed**

Notes:
1. `SettingsManager` now supports typed access, schema validation, feature flags JSON, and environment-aware overrides.
2. `CF Settings` includes explicit `deployment_environment` and `feature_flags_json` fields.

## Phase 2: Enhanced Agent Capabilities (Week 2)

### Step 2.1: Implement Agent Planning System
1. **QueryAnalyzer** - Classify query intent and complexity
2. **PlanGenerator** - Create step-by-step execution plans before tool calls
3. **ToolRecommender** - Suggest relevant tools based on query analysis
4. **PlanExecutor** - Execute plans with monitoring and adjustment

Status: **Partially Completed**

Notes:
1. All four foundational classes are now implemented under `cognitive_folio/cognitive_folio/services/agent/`.
2. Planning is integrated into `ToolOrchestrator` before tool rounds execute.
3. Planner behavior is now configurable via `SettingsManager` (feature flags/env overrides), including intent markers, thresholds, plan-step bounds, and recommended-tool limits.
4. Orchestrator now records planner policy metadata in runtime usage and supports optional enforcement of recommended-tool execution.
5. Test-environment stabilization is still required for full completion: the fiscal-year overlap preload issue is mitigated via app `before_tests`, but full app-level preload still hits an external `erpnext_cyprus` Company override regression (`custom_chart` unbound).

### Step 2.2: Add Advanced Tool Features
1. **Tool composition** - Allow tools to chain with data dependencies
2. **Dynamic tool registration** - Enable plugins without code changes
3. **Tool learning** - Track effectiveness metrics for different query types
4. **Self-correction** - Allow agent to recognize and fix erroneous tool calls

Status: **Functionally Completed (with test-environment caveat)**

Notes:
1. Added `services/tooling/` modules: `ToolComposer`, `ToolRegistry`, `ToolEffectivenessTracker`, and `ToolSelfCorrector`.
2. `ToolOrchestrator` now supports placeholder-based tool composition, retry-on-failure self-correction, and per-tool effectiveness metrics in usage metadata.
3. Dynamic tool registration is enabled through Frappe hooks (`cognitive_folio_tool_definitions`, `cognitive_folio_tool_handlers`) with policy gating via settings feature flags.
4. Added a production plugin example (`normalize_ticker`) wired via hooks to validate dynamic registration end-to-end.
5. Tool execution policy and per-tool effectiveness metrics are now persisted in runtime audit payload for each message.
6. Added long-horizon daily rollups via `CF Tool Metric` Doctype and `ToolMetricsStore` persistence service.
7. Added observability UI artifacts: `Tool Metrics Trends` query report and trend charts (`Tool Calls Trend`, `Tool Avg Latency Trend`), plus workspace report link wiring.
8. Caveat: feature behavior is complete and module tests pass, but full app-level preload test runs still depend on upstream fixture stability (`Parent Account: Bank Accounts - _TC` in this environment).

### Step 2.3: Implement Agent Memory System
1. **VectorMemory** - Store and retrieve important facts using embeddings
2. **ConversationMemory** - Long-term memory across conversations
3. **KnowledgeExtractor** - Extract entities and relationships from responses
4. **MemoryManager** - Coordinate different memory types with prioritization

Status: **In Progress (MVP started)**

Notes:
1. Added `services/memory/ConversationMemory` with cache-backed memory storage and DB fallback to recent successful chat messages.
2. Added `services/memory/MemoryManager` as a single entry point for memory retrieval and turn recording.
3. Integrated memory injection + turn recording into `CFChatMessage.send()` with runtime audit metadata under `runtime_audit.memory`.
4. Added `services/memory/KnowledgeExtractor` to capture compact turn facts (tickers, numeric values, and intent markers).
5. Upgraded `ConversationMemory` retrieval with relevance-aware selection using current prompt term overlap and bounded inclusion of relevant memories.
6. Expanded memory service unit tests to cover extraction, relevance ranking, and metadata delegation.
7. Added `services/memory/VectorMemory` for context-aware retrieval that prioritizes active portfolio/security scope and semantic term overlap.
8. Integrated `VectorMemory` into `MemoryManager` and `CFChatMessage.send()` with contextual metadata passed on retrieval and persistence.
9. Added `services/memory/EmbeddingProvider` and switched vector ranking to cosine similarity over deterministic local embeddings (with lexical fallback mode).
10. Added embedding-focused unit tests and expanded vector tests to validate ranking behavior in both embedding and lexical modes.
11. Added persistent vector-memory storage with new `CF Vector Memory` DocType and cache/store fallback retrieval in `VectorMemory`.
12. Added tests for DocType-backed persistence and store fallback reads when cache is empty.
13. Added retention controls for persistent vector memory (`max records per chat` and `max age days`) with pruning after successful writes.
14. Added unit tests validating retention pruning deletes overflow and expired rows.
15. Added scheduled daily cleanup task (`cleanup_vector_memory_store`) and scheduler hook to enforce retention even without new writes.
16. Added task-level tests for successful cleanup execution and failure handling.
17. Added `CF Memory Cleanup Metric` daily rollup DocType to track cleanup observability (runs, chats scanned, rows deleted, success/failure).
18. Added `CleanupMetricsStore` and wired cleanup task to persist metrics for both successful and failed runs.
19. Added `Memory Cleanup Metrics Trends` script report with date/status filters and workspace link for operations monitoring.
20. Added dashboard trend charts for cleanup observability: `Memory Cleanup Rows Deleted Trend` and `Memory Cleanup Failed Runs Trend`, wired into workspace layout.

## Phase 3: Web Search Enhancement (Week 3)

### Step 3.1: Expand Search Provider Ecosystem
1. **ProviderRegistry** - Manage multiple search providers with fallback chains
2. **Add Google Search API** integration (via SerpAPI or official API)
3. **Add Bing Search API** integration
4. **Add ArXiv API** for academic papers
5. **Add SEC API** for real-time filings and updates

Status: **Completed (scoped)**

Notes:
1. Added `services/search/ProviderRegistry` with configurable fallback chains and provider registration.
2. Refactored `WebSearchService` to route both general and financial search execution through the registry.
3. Added provider routing tests for fallback behavior and explicit source/provider hints.
4. Added SerpAPI provider integration (`serpapi`) for both `web_search` and `search_financial`, gated by settings/feature flags.
5. Extended `SettingsManager` with `get_search_provider_config()` for configurable general/financial provider chains and SerpAPI runtime options.
6. Added SEC real-time filings support (official SEC submissions JSON) under existing `sec_edgar` provider flow with ticker-based CIK resolution and result normalization.
7. Added SEC realtime settings controls (`search_sec_realtime_enabled`, `search_sec_user_agent`) with integration test coverage.
8. Scope decision: deferred Bing and ArXiv provider additions for now.

### Step 3.2: Implement Search Quality Improvements
1. **QueryRefiner** - Use LLM to improve search queries before execution
2. **ResultReranker** - Apply relevance scoring based on query intent
3. **DomainAuthorityScorer** - Prioritize authoritative sources
4. **FreshnessWeighting** - Balance recency vs. authority based on query type
5. **CrossSourceVerifier** - Fact-check information across multiple sources

Status: **Completed**

Notes:
1. Added `services/search/QueryRefiner` with deterministic normalization and optional LLM-backed extraction fallback.
2. Added `services/search/ResultReranker` with lexical relevance + domain authority + provider weighting.
3. Integrated refinement/reranking into `WebSearchService` for both general and financial search flows.
4. Added settings flags for `search_query_refiner_enabled`, `search_query_refiner_llm_enabled`, `search_result_reranker_enabled`, and `search_result_reranker_top_k`.
5. Added unit and integration tests for refiner/reranker behavior and pipeline wiring.
6. Added `services/search/FreshnessWeighting` and integrated recency-aware scoring into reranking for time-sensitive queries.
7. Added `services/search/CrossSourceVerifier` and integrated corroboration scoring across independent domains.
8. Extended search settings with `search_freshness_weighting_enabled`, `search_freshness_half_life_days`, `search_cross_source_verifier_enabled`, and `search_cross_source_min_sources`.
9. Extracted `services/search/DomainAuthorityScorer` and made authority scoring configurable via `search_domain_authority_enabled`, `search_domain_authority_default_weight`, and `search_domain_authority_weights`.
10. Upgraded `CrossSourceVerifier` with contradiction-aware confidence scoring and added tunables for contradiction penalty and confidence boost.

### Step 3.3: Add Advanced Search Features
1. **SemanticSearch** - Use embeddings for conceptual similarity matching
2. **TrendDetector** - Identify emerging topics across search results
3. **PersonalizedSearch** - Adapt search behavior based on user preferences
4. **SearchSessionTracker** - Maintain context across related searches

Status: **Completed**

Notes:
1. Added `services/search/SearchSessionTracker` with cache-backed session history for recent queries/providers/top URLs.
2. Integrated follow-up query expansion and per-search session recording into `WebSearchService` behind feature flags.
3. Added search settings controls for session tracking limits and follow-up expansion behavior.
4. Added dedicated unit tests for tracker behavior and integration assertions in web search/settings test suites.
5. Added `services/search/SemanticSearch` using deterministic local embeddings for conceptual similarity scoring.
6. Integrated optional semantic-score boosting into `ResultReranker` and runtime rerank options.
7. Added semantic search settings controls (`search_semantic_search_enabled`, `search_semantic_embedding_dims`, `search_semantic_score_weight`) and test coverage.
8. Added `services/search/TrendDetector` for repeated-theme detection across result sets.
9. Integrated optional trend-score boosting into reranking with configurable frequency and weight thresholds.
10. Added trend detector settings controls (`search_trend_detector_enabled`, `search_trend_min_frequency`, `search_trend_score_weight`) and test coverage.
11. Added `services/search/PersonalizedSearch` for lightweight preference-aware scoring across providers/domains/tickers.
12. Integrated optional personalized-score boosting into reranking with session-derived context from recent search history.
13. Added personalization settings controls (`search_personalized_search_enabled`, `search_personalized_score_weight`, `search_personalized_history_items`, `search_preferred_sources`, `search_preferred_domains`) and test coverage.

## Phase 4: Performance & Reliability (Week 4)

### Step 4.1: Implement Caching System
1. **SearchResultCache** - Cache results with TTL based on query type
2. **ContentSummarizationCache** - Store processed versions of frequently accessed pages
3. **ToolResultCache** - Enhance existing LRU cache with persistence
4. **PredictivePrefetching** - Anticipate follow-up searches based on conversation patterns

Status: **Completed (feature-flagged)**

Notes:
1. Added `services/performance/SearchResultCache` and wired cache lookups/writes into `WebSearchService.search_web_results()` and `search_financial_sources()`.
2. Added `services/performance/ContentSummarizationCache` and integrated cached URL-content extraction in `CFChatMessage._tool_fetch_url_content()`.
3. Added `services/performance/ToolResultCache` and integrated read-through caching in `CFChatMessage._execute_tool_call()` for read-only tool calls.
4. Added `services/performance/PredictivePrefetching` and optional prefetch follow-up execution in `WebSearchService` behind feature flags.

### Step 4.2: Add Circuit Breaker Pattern
1. **CircuitBreakerManager** - Monitor external API health and availability
2. **RateLimiter** - Respect provider rate limits with token bucket algorithm
3. **GracefulDegradation** - Maintain functionality when external services fail
4. **HealthDashboard** - Monitor system health and performance metrics

Status: **Completed (feature-flagged)**

Notes:
1. Added `services/performance/CircuitBreakerManager` and `RateLimiter` and wired both into provider execution paths in `WebSearchService`.
2. Added graceful provider fallback behavior by skipping unavailable/rate-limited providers and continuing through configured fallback chains.
3. Added `services/performance/HealthDashboard` and `WebSearchService.get_health_snapshot()` for provider health introspection.
4. Added scheduled health snapshot task `capture_search_reliability_health_snapshot`.

### Step 4.3: Database Optimization
1. **BatchDatabaseWriter** - Optimize multiple writes during streaming
2. **ConnectionPooling** - Manage database connections efficiently
3. **QueryOptimization** - Improve database query performance
4. **IndexManagement** - Add appropriate indexes for common queries

Status: **Completed (feature-flagged)**

Notes:
1. Added `services/performance/BatchDatabaseWriter`, `ConnectionPooling`, `QueryOptimization`, and `IndexManagement`.
2. Integrated `BatchDatabaseWriter` into `CFChatMessage.process_in_background()` for status/update write batching.
3. Added scheduled index maintenance task `run_phase4_index_maintenance` with explicit high-traffic index specs (`CF Chat Message`, `CF Tool Metric`, `CF Vector Memory`).
4. Added `SettingsManager.get_performance_config()` for typed control over cache/reliability/maintenance feature flags and thresholds.

## Phase 5: Security & Compliance (Week 5)

### Step 5.1: Content Security
1. **ContentSanitizer** - Remove malicious scripts/HTML from fetched content
2. **PrivacyPreserver** - Anonymize search queries where possible
3. **AccessControl** - Implement fine-grained permissions for different features
4. **AuditLogger** - Enhanced logging for security and compliance

### Step 5.2: Financial Compliance
1. **SearchComplianceTracker** - Log searches for regulatory requirements
2. **DataRetentionPolicy** - Implement proper data retention and deletion
3. **ExportCapabilities** - Enhanced data export for compliance reporting
4. **AccessAudit** - Track who accessed what information and when

## Phase 6: Monitoring & Evaluation (Week 6)

### Step 6.1: Implement Quality Metrics
1. **AnswerQualityScorer** - Track accuracy, completeness, and relevance
2. **ToolEffectivenessTracker** - Measure which tools contribute to successful answers
3. **CostOptimizer** - Balance between tool calls and direct answering
4. **UserFeedbackSystem** - Collect and incorporate user feedback

### Step 6.2: Add A/B Testing Framework
1. **ExperimentManager** - Coordinate different agent configurations
2. **MetricsCollector** - Gather performance data for experiments
3. **StatisticalAnalyzer** - Determine significant differences between approaches
4. **RolloutController** - Gradually deploy successful experiments

### Step 6.3: Create Monitoring Dashboard
1. **RealTimeMetrics** - Live monitoring of system performance
2. **AlertingSystem** - Notify administrators of issues
3. **PerformanceTrends** - Track system performance over time
4. **UsageAnalytics** - Understand how features are being used

## Implementation Guidelines

### Code Quality Standards
1. **Test Coverage** - Maintain 80%+ test coverage for all new code
2. **Type Hints** - Use Python type hints throughout
3. **Documentation** - Include docstrings and API documentation
4. **Error Handling** - Comprehensive error handling with user-friendly messages
5. **Logging** - Structured logging with appropriate log levels

### Migration Strategy
1. **Backward Compatibility** - Not a current goal; removed where it increased code complexity
2. **Feature Flags** - Use flags to control rollout of new features
3. **Gradual Migration** - Migrate functionality piece by piece
4. **Rollback Plan** - Have a clear plan to revert changes if needed

### Testing Approach
1. **Unit Tests** - Test individual components in isolation
2. **Integration Tests** - Test interactions between components
3. **End-to-End Tests** - Test complete workflows
4. **Performance Tests** - Ensure system meets performance requirements
5. **Security Tests** - Verify security measures are effective

## Success Criteria

### Functional Requirements
1. All existing functionality continues to work without modification
2. New features can be enabled/disabled via configuration
3. System performance improves or remains the same
4. Error rates decrease by at least 20%
5. User satisfaction increases based on feedback

### Technical Requirements
1. Code maintainability improves (reduced cyclomatic complexity)
2. Test coverage remains above 80%
3. Response times remain under 5 seconds for 95% of requests
4. System can handle 10x current load without degradation
5. All external dependencies have fallback mechanisms

## Risk Mitigation

### Technical Risks
1. **External API Dependencies** - Implement circuit breakers and fallbacks
2. **Performance Degradation** - Extensive performance testing at each phase
3. **Data Loss** - Comprehensive backup and recovery procedures
4. **Security Vulnerabilities** - Regular security reviews and penetration testing

### Project Risks
1. **Scope Creep** - Strict adherence to phased implementation
2. **Timeline Slippage** - Weekly progress reviews and adjustments
3. **Team Capacity** - Realistic estimates with buffer time
4. **Knowledge Transfer** - Documentation and pair programming

## Next Steps

1. **Review this plan** with the development team
2. **Prioritize phases** based on business value
3. **Estimate effort** for each phase
4. **Create detailed task breakdown** for Phase 1
5. **Begin implementation** with Step 1.1

## Notes for AI Agent Implementation

When implementing each step:
1. **Read the existing code** thoroughly to understand current patterns
2. **Maintain existing interfaces** where possible
3. **Add comprehensive tests** for new functionality
4. **Document changes** with clear commit messages
5. **Validate backward compatibility** after each change
6. **Consider Frappe framework conventions** and best practices
7. **Use existing utility functions** from `cognitive_folio/utils/` when appropriate
8. **Follow Python best practices** and the project's coding standards

This plan provides a structured approach to enhancing the chat message functionality while maintaining stability and gradually introducing improvements.
