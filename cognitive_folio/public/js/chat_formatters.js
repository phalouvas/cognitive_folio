// Chat formatting utilities for CF Chat Message
// Provides human-readable HTML displays for tokens and runtime_audit data

/**
 * Format tokens JSON data into human-readable HTML
 * @param {Object|string} tokensData - Tokens JSON object or string
 * @returns {string} HTML string with formatted tokens display
 */
function formatTokensForDisplay(tokensData) {
    if (!tokensData) {
        return '<div class="text-muted">No token data available</div>';
    }

    try {
        // Parse if string
        const tokens = typeof tokensData === 'string' ? JSON.parse(tokensData) : tokensData;
        
        if (!tokens || Object.keys(tokens).length === 0) {
            return '<div class="text-muted">No token data available</div>';
        }

        let html = `
            <div class="chat-tokens-display">
                <div class="token-summary frappe-card mb-3">
                    <h6 class="mb-2">Token Summary</h6>
                    <div class="row">
        `;

        // Token counts
        if (tokens.prompt_tokens !== undefined) {
            html += `
                <div class="col-sm-4 mb-2">
                    <div class="text-muted small">Prompt Tokens</div>
                    <div class="font-weight-bold">${formatNumber(tokens.prompt_tokens)}</div>
                </div>
            `;
        }

        if (tokens.completion_tokens !== undefined) {
            html += `
                <div class="col-sm-4 mb-2">
                    <div class="text-muted small">Completion Tokens</div>
                    <div class="font-weight-bold">${formatNumber(tokens.completion_tokens)}</div>
                </div>
            `;
        }

        if (tokens.total_tokens !== undefined) {
            html += `
                <div class="col-sm-4 mb-2">
                    <div class="text-muted small">Total Tokens</div>
                    <div class="font-weight-bold">${formatNumber(tokens.total_tokens)}</div>
                </div>
            `;
        }

        html += `
                    </div>
                </div>
        `;

        // Model and finish reason
        if (tokens.model || tokens.finish_reason) {
            html += `
                <div class="model-info frappe-card mb-3">
                    <h6 class="mb-2">Model Information</h6>
                    <div class="row">
            `;

            if (tokens.model) {
                html += `
                    <div class="col-sm-6 mb-2">
                        <div class="text-muted small">Model</div>
                        <div class="font-weight-bold">${escapeHtml(tokens.model)}</div>
                    </div>
                `;
            }

            if (tokens.finish_reason) {
                html += `
                    <div class="col-sm-6 mb-2">
                        <div class="text-muted small">Finish Reason</div>
                        <div class="font-weight-bold">${formatFinishReason(tokens.finish_reason)}</div>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // Duration and tool calls
        if (tokens.duration_ms !== undefined || tokens.tool_calls !== undefined) {
            html += `
                <div class="performance-info frappe-card mb-3">
                    <h6 class="mb-2">Performance</h6>
                    <div class="row">
            `;

            if (tokens.duration_ms !== undefined) {
                html += `
                    <div class="col-sm-6 mb-2">
                        <div class="text-muted small">Duration</div>
                        <div class="font-weight-bold">${formatDuration(tokens.duration_ms)}</div>
                    </div>
                `;
            }

            if (tokens.tool_calls !== undefined) {
                html += `
                    <div class="col-sm-6 mb-2">
                        <div class="text-muted small">Tool Calls</div>
                        <div class="font-weight-bold">${formatNumber(tokens.tool_calls)}</div>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // Tool execution details
        if (tokens.tool_calls_trace && Array.isArray(tokens.tool_calls_trace) && tokens.tool_calls_trace.length > 0) {
            html += `
                <div class="tool-execution-details frappe-card mb-3">
                    <h6 class="mb-2">Tool Execution Trace</h6>
                    <div class="table-responsive">
                        <table class="table table-sm table-bordered">
                            <thead>
                                <tr>
                                    <th>Round</th>
                                    <th>Tool</th>
                                    <th>Status</th>
                                    <th>Duration</th>
                                    <th>Query/Args</th>
                                </tr>
                            </thead>
                            <tbody>
            `;
            
            tokens.tool_calls_trace.forEach(toolCall => {
                const statusClass = toolCall.ok ? 'text-success' : 'text-danger';
                const statusText = toolCall.ok ? 'Success' : 'Failed';
                const duration = toolCall.duration_ms ? `${toolCall.duration_ms.toFixed(2)}ms` : 'N/A';
                let queryPreview = 'N/A';
                
                if (toolCall.args) {
                    if (toolCall.args.query) {
                        queryPreview = escapeHtml(toolCall.args.query.substring(0, 50) + (toolCall.args.query.length > 50 ? '...' : ''));
                    } else if (toolCall.args.identifier) {
                        queryPreview = `Identifier: ${escapeHtml(toolCall.args.identifier)}`;
                    } else if (toolCall.args.portfolio) {
                        queryPreview = `Portfolio: ${escapeHtml(toolCall.args.portfolio)}`;
                    }
                }
                
                html += `
                    <tr>
                        <td>${toolCall.round || 'N/A'}</td>
                        <td><code>${escapeHtml(toolCall.tool || 'N/A')}</code></td>
                        <td class="${statusClass}">${statusText}</td>
                        <td>${duration}</td>
                        <td title="${escapeHtml(JSON.stringify(toolCall.args || {}))}">${queryPreview}</td>
                    </tr>
                `;
            });
            
            html += `
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }

        // Tool metrics summary
        if (tokens.tool_metrics && Object.keys(tokens.tool_metrics).length > 0) {
            html += `
                <div class="tool-metrics-summary frappe-card mb-3">
                    <h6 class="mb-2">Tool Performance Metrics</h6>
                    <div class="row">
            `;
            
            Object.entries(tokens.tool_metrics).forEach(([toolName, metrics]) => {
                const successRate = metrics.success_rate !== undefined ? (metrics.success_rate * 100).toFixed(1) + '%' : 'N/A';
                const avgDuration = metrics.avg_duration_ms !== undefined ? `${metrics.avg_duration_ms.toFixed(2)}ms` : 'N/A';
                
                html += `
                    <div class="col-sm-6 mb-3">
                        <div class="frappe-card p-2">
                            <div class="font-weight-bold mb-1">${escapeHtml(toolName)}</div>
                            <div class="row small">
                                <div class="col-6">
                                    <div class="text-muted">Calls</div>
                                    <div>${formatNumber(metrics.calls || 0)}</div>
                                </div>
                                <div class="col-6">
                                    <div class="text-muted">Success Rate</div>
                                    <div class="${metrics.success_rate >= 0.9 ? 'text-success' : metrics.success_rate >= 0.7 ? 'text-warning' : 'text-danger'}">
                                        ${successRate}
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="text-muted">Avg Duration</div>
                                    <div>${avgDuration}</div>
                                </div>
                                <div class="col-6">
                                    <div class="text-muted">Retries</div>
                                    <div>${formatNumber(metrics.retries || 0)}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            html += `
                    </div>
                </div>
            `;
        }

        // Full details expandable section with human-readable breakdown
        html += `
            <div class="full-details frappe-card">
                <a href="#" class="details-toggle" onclick="toggleDetails(this); return false;">
                    <h6 class="mb-0 d-inline">
                        ${frappe.utils.icon('small-down', 'sm')}
                        Detailed Breakdown
                    </h6>
                </a>
                <div class="details-content mt-2" style="display: none;">
                    <div class="human-readable-details">
        `;
        
        // Add human-readable sections
        if (tokens.plan) {
            html += `
                <div class="mb-3">
                    <h6 class="mb-1">Execution Plan</h6>
                    <div class="pl-3">
                        <div><strong>Intent:</strong> ${escapeHtml(tokens.plan.intent || 'N/A')}</div>
                        <div><strong>Complexity:</strong> ${escapeHtml(tokens.plan.complexity || 'N/A')}</div>
                        <div><strong>Max Rounds:</strong> ${formatNumber(tokens.plan.max_rounds || 0)}</div>
                        <div><strong>Recommended Tools:</strong> ${escapeHtml((tokens.plan.recommended_tools || []).join(', ') || 'None')}</div>
                        <div><strong>Steps:</strong></div>
                        <ol class="pl-3">
                            ${(tokens.plan.steps || []).map(step => `<li>${escapeHtml(step)}</li>`).join('')}
                        </ol>
                    </div>
                </div>
            `;
        }
        
        if (tokens.planner) {
            html += `
                <div class="mb-3">
                    <h6 class="mb-1">Planner Configuration</h6>
                    <div class="pl-3">
                        <div><strong>Enabled:</strong> ${tokens.planner.enabled ? 'Yes' : 'No'}</div>
                        <div><strong>Inject System Plan:</strong> ${tokens.planner.inject_system_plan ? 'Yes' : 'No'}</div>
                        <div><strong>Enforce Recommended Tools:</strong> ${tokens.planner.enforce_recommended_tools ? 'Yes' : 'No'}</div>
                    </div>
                </div>
            `;
        }
        
        if (tokens.tool_execution) {
            html += `
                <div class="mb-3">
                    <h6 class="mb-1">Tool Execution Features</h6>
                    <div class="pl-3">
                        <div><strong>Composition Enabled:</strong> ${tokens.tool_execution.composition_enabled ? 'Yes' : 'No'}</div>
                        <div><strong>Self-Correction Enabled:</strong> ${tokens.tool_execution.self_correction_enabled ? 'Yes' : 'No'}</div>
                        <div><strong>Dynamic Registration:</strong> ${tokens.tool_execution.dynamic_registration_enabled ? 'Yes' : 'No'}</div>
                        <div><strong>Max Corrections per Call:</strong> ${formatNumber(tokens.tool_execution.max_corrections_per_call || 0)}</div>
                    </div>
                </div>
            `;
        }
        
        // Raw JSON as fallback
        html += `
                    </div>
                    <hr>
                    <h6 class="mb-2">Raw JSON Data</h6>
                    <pre class="bg-light p-3 rounded">${escapeHtml(JSON.stringify(tokens, null, 2))}</pre>
                </div>
            </div>
        `;

        html += `</div>`;
        return html;

    } catch (error) {
        console.error("Error formatting tokens:", error);
        return `<div class="text-danger">Error formatting token data: ${escapeHtml(error.message)}</div>`;
    }
}

/**
 * Format runtime_audit JSON data into human-readable HTML
 * @param {Object|string} auditData - Runtime audit JSON object or string
 * @returns {string} HTML string with formatted audit display
 */
function formatRuntimeAuditForDisplay(auditData) {
    if (!auditData) {
        return '<div class="text-muted">No runtime audit data available</div>';
    }

    try {
        // Parse if string
        const audit = typeof auditData === 'string' ? JSON.parse(auditData) : auditData;
        
        if (!audit || Object.keys(audit).length === 0) {
            return '<div class="text-muted">No runtime audit data available</div>';
        }

        let html = `
            <div class="chat-audit-display">
        `;

        // Augmentations and context
        if (audit.augmentations || audit.context_injection) {
            html += `
                <div class="augmentations-info frappe-card mb-3">
                    <h6 class="mb-2">Context & Augmentations</h6>
                    <div class="row">
            `;

            if (audit.augmentations) {
                const augCount = Array.isArray(audit.augmentations) ? audit.augmentations.length : 0;
                html += `
                    <div class="col-sm-6 mb-2">
                        <div class="text-muted small">Augmentations</div>
                        <div class="font-weight-bold">${formatNumber(augCount)}</div>
                    </div>
                `;
            }

            if (audit.context_injection) {
                const hasContext = audit.context_injection === true || 
                                 (typeof audit.context_injection === 'object' && 
                                  Object.keys(audit.context_injection).length > 0);
                html += `
                    <div class="col-sm-6 mb-2">
                        <div class="text-muted small">Context Injected</div>
                        <div class="font-weight-bold ${hasContext ? 'text-success' : 'text-muted'}">
                            ${hasContext ? 'Yes' : 'No'}
                        </div>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // Web search summary
        if (audit.web_search) {
            html += `
                <div class="web-search-info frappe-card mb-3">
                    <h6 class="mb-2">Web Search</h6>
                    <div class="row">
            `;

            // Handle different web search data structures
            let queryCount = 0;
            let resultCount = 0;
            
            if (audit.web_search.queries && Array.isArray(audit.web_search.queries)) {
                queryCount = audit.web_search.queries.length;
            } else if (audit.web_search.search_iterations !== undefined) {
                queryCount = audit.web_search.search_iterations;
            }
            
            if (audit.web_search.results && Array.isArray(audit.web_search.results)) {
                resultCount = audit.web_search.results.length;
            } else if (audit.web_search.results_count !== undefined) {
                resultCount = audit.web_search.results_count;
            }
            
            html += `
                <div class="col-sm-3 mb-2">
                    <div class="text-muted small">Enabled</div>
                    <div class="font-weight-bold ${audit.web_search.enabled ? 'text-success' : 'text-muted'}">
                        ${audit.web_search.enabled ? 'Yes' : 'No'}
                    </div>
                </div>
                <div class="col-sm-3 mb-2">
                    <div class="text-muted small">Search Iterations</div>
                    <div class="font-weight-bold">${formatNumber(queryCount)}</div>
                </div>
                <div class="col-sm-3 mb-2">
                    <div class="text-muted small">Results Found</div>
                    <div class="font-weight-bold">${formatNumber(resultCount)}</div>
                </div>
            `;
            
            if (audit.web_search.financial_searches !== undefined) {
                html += `
                    <div class="col-sm-3 mb-2">
                        <div class="text-muted small">Financial Searches</div>
                        <div class="font-weight-bold">${formatNumber(audit.web_search.financial_searches)}</div>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // Tool execution
        if (audit.tool_execution) {
            html += `
                <div class="tool-execution-info frappe-card mb-3">
                    <h6 class="mb-2">Tool Execution</h6>
                    <div class="row">
            `;

            if (audit.tool_execution.rounds !== undefined) {
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Rounds</div>
                        <div class="font-weight-bold">${formatNumber(audit.tool_execution.rounds)}</div>
                    </div>
                `;
            }

            if (audit.tool_execution.total_calls !== undefined) {
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Total Calls</div>
                        <div class="font-weight-bold">${formatNumber(audit.tool_execution.total_calls)}</div>
                    </div>
                `;
            }

            if (audit.tool_execution.duration_ms !== undefined) {
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Tool Time</div>
                        <div class="font-weight-bold">${formatDuration(audit.tool_execution.duration_ms)}</div>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // Monitoring and quality
        if (audit.monitoring_alerts || audit.quality_score !== undefined) {
            html += `
                <div class="monitoring-info frappe-card mb-3">
                    <h6 class="mb-2">Monitoring & Quality</h6>
                    <div class="row">
            `;

            if (audit.monitoring_alerts) {
                const alertCount = Array.isArray(audit.monitoring_alerts) ? audit.monitoring_alerts.length : 0;
                html += `
                    <div class="col-sm-6 mb-2">
                        <div class="text-muted small">Monitoring Alerts</div>
                        <div class="font-weight-bold ${alertCount > 0 ? 'text-warning' : 'text-success'}">
                            ${formatNumber(alertCount)}
                        </div>
                    </div>
                `;
            }

            if (audit.quality_score !== undefined) {
                const scoreClass = audit.quality_score >= 0.8 ? 'text-success' : 
                                 audit.quality_score >= 0.6 ? 'text-warning' : 'text-danger';
                html += `
                    <div class="col-sm-6 mb-2">
                        <div class="text-muted small">Quality Score</div>
                        <div class="font-weight-bold ${scoreClass}">
                            ${formatPercent(audit.quality_score)}
                        </div>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // Memory usage
        if (audit.memory_usage) {
            html += `
                <div class="memory-info frappe-card mb-3">
                    <h6 class="mb-2">Memory Usage</h6>
                    <div class="row">
            `;

            if (audit.memory_usage.context_tokens !== undefined) {
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Context Tokens</div>
                        <div class="font-weight-bold">${formatNumber(audit.memory_usage.context_tokens)}</div>
                    </div>
                `;
            }

            if (audit.memory_usage.memory_tokens !== undefined) {
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Memory Tokens</div>
                        <div class="font-weight-bold">${formatNumber(audit.memory_usage.memory_tokens)}</div>
                    </div>
                `;
            }

            if (audit.memory_usage.total_tokens !== undefined) {
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Total Memory Tokens</div>
                        <div class="font-weight-bold">${formatNumber(audit.memory_usage.total_tokens)}</div>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // Full details expandable section with human-readable breakdown
        html += `
            <div class="full-details frappe-card">
                <a href="#" class="details-toggle" onclick="toggleDetails(this); return false;">
                    <h6 class="mb-0 d-inline">
                        ${frappe.utils.icon('small-down', 'sm')}
                        Detailed Audit Breakdown
                    </h6>
                </a>
                <div class="details-content mt-2" style="display: none;">
                    <div class="human-readable-details">
        `;
        
        // Add human-readable sections for runtime audit
        
        // Model and augmentations
        html += `
            <div class="mb-3">
                <h6 class="mb-1">Model & Augmentations</h6>
                <div class="pl-3">
                    <div><strong>Model:</strong> ${escapeHtml(audit.model || 'N/A')}</div>
                    <div><strong>Augmentations:</strong> ${escapeHtml((audit.augmentations || []).join(', ') || 'None')}</div>
        `;
        
        if (audit.context_injection) {
            const context = audit.context_injection;
            html += `
                    <div><strong>Context Injection:</strong> ${context.enabled ? 'Enabled' : 'Disabled'}</div>
                    <div><strong>Applied:</strong> ${context.applied ? 'Yes' : 'No'}</div>
                    <div><strong>Fields Used:</strong> ${escapeHtml((context.fields_used || []).join(', ') || 'None')}</div>
                    <div><strong>Chars Added:</strong> ${formatNumber(context.chars_added || 0)}</div>
            `;
        }
        
        html += `
                </div>
            </div>
        `;
        
        // Memory usage
        if (audit.memory) {
            html += `
                <div class="mb-3">
                    <h6 class="mb-1">Memory Usage</h6>
                    <div class="pl-3">
                        <div><strong>Enabled:</strong> ${audit.memory.enabled ? 'Yes' : 'No'}</div>
                        <div><strong>Used:</strong> ${audit.memory.used ? 'Yes' : 'No'}</div>
            `;
            
            if (audit.memory.record) {
                const record = audit.memory.record;
                html += `
                        <div><strong>Stored:</strong> ${record.stored ? 'Yes' : 'No'}</div>
                        <div><strong>Short-term Items:</strong> ${record.short_term ? formatNumber(record.short_term.items || 0) : '0'}</div>
                        <div><strong>Vector Items:</strong> ${record.vector ? formatNumber(record.vector.items || 0) : '0'}</div>
                `;
            }
            
            html += `
                    </div>
                </div>
            `;
        }
        
        // Tools section
        if (audit.tools) {
            html += `
                <div class="mb-3">
                    <h6 class="mb-1">Tools Execution</h6>
                    <div class="pl-3">
                        <div><strong>Enabled:</strong> ${audit.tools.enabled ? 'Yes' : 'No'}</div>
                        <div><strong>Rounds:</strong> ${formatNumber(audit.tools.rounds || 0)}</div>
                        <div><strong>Calls:</strong> ${formatNumber(audit.tools.calls || 0)}</div>
                        <div><strong>Tools Used:</strong> ${escapeHtml((audit.tools.names || []).join(', ') || 'None')}</div>
            `;
            
            if (audit.tools.plan) {
                const plan = audit.tools.plan;
                html += `
                        <div><strong>Plan Intent:</strong> ${escapeHtml(plan.intent || 'N/A')}</div>
                        <div><strong>Plan Complexity:</strong> ${escapeHtml(plan.complexity || 'N/A')}</div>
                        <div><strong>Max Rounds:</strong> ${formatNumber(plan.max_rounds || 0)}</div>
                `;
            }
            
            html += `
                    </div>
                </div>
            `;
        }
        
        // Monitoring section
        if (audit.monitoring) {
            html += `
                <div class="mb-3">
                    <h6 class="mb-1">Monitoring & Quality</h6>
                    <div class="pl-3">
            `;
            
            if (audit.monitoring.quality_scores) {
                const scores = audit.monitoring.quality_scores;
                html += `
                        <div><strong>Quality Score:</strong> ${formatPercent(scores.quality_score || 0)}</div>
                        <div><strong>Relevance Score:</strong> ${formatPercent(scores.relevance_score || 0)}</div>
                        <div><strong>Completeness Score:</strong> ${formatPercent(scores.completeness_score || 0)}</div>
                        <div><strong>Grounding Score:</strong> ${formatPercent(scores.grounding_score || 0)}</div>
                `;
            }
            
            if (audit.monitoring.cost_metrics) {
                const cost = audit.monitoring.cost_metrics;
                html += `
                        <div><strong>Estimated Cost:</strong> $${(cost.estimated_cost_usd || 0).toFixed(6)}</div>
                        <div><strong>Tool Calls:</strong> ${formatNumber(cost.tool_calls || 0)}</div>
                        <div><strong>Recommendation:</strong> ${escapeHtml(cost.recommendation || 'N/A')}</div>
                `;
            }
            
            if (audit.monitoring.alerts) {
                html += `
                        <div><strong>Alerts Created:</strong> ${audit.monitoring.alerts.created ? 'Yes' : 'No'}</div>
                        <div><strong>Alert Count:</strong> ${formatNumber(audit.monitoring.alerts.count || 0)}</div>
                `;
            }
            
            html += `
                    </div>
                </div>
            `;
        }
        
        // Experiment section
        if (audit.experiment) {
            html += `
                <div class="mb-3">
                    <h6 class="mb-1">Experiment</h6>
                    <div class="pl-3">
                        <div><strong>Experiment:</strong> ${escapeHtml(audit.experiment.experiment || 'None')}</div>
                        <div><strong>Variant:</strong> ${escapeHtml(audit.experiment.variant || 'control')}</div>
                    </div>
                </div>
            `;
        }
        
        // Raw JSON as fallback
        html += `
                    </div>
                    <hr>
                    <h6 class="mb-2">Raw JSON Data</h6>
                    <pre class="bg-light p-3 rounded">${escapeHtml(JSON.stringify(audit, null, 2))}</pre>
                </div>
            </div>
        `;

        html += `</div>`;
        return html;

    } catch (error) {
        console.error("Error formatting runtime audit:", error);
        return `<div class="text-danger">Error formatting audit data: ${escapeHtml(error.message)}</div>`;
    }
}

// Helper functions
function formatNumber(num) {
    if (num === undefined || num === null) return 'N/A';
    return num.toLocaleString();
}

function formatDuration(ms) {
    if (ms === undefined || ms === null) return 'N/A';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
    return `${(ms / 60000).toFixed(2)}m`;
}

function formatPercent(value) {
    if (value === undefined || value === null) return 'N/A';
    return `${(value * 100).toFixed(1)}%`;
}

function formatFinishReason(reason) {
    if (!reason) return 'N/A';
    const reasonMap = {
        'stop': 'Normal completion',
        'length': 'Max tokens reached',
        'content_filter': 'Content filtered',
        'tool_calls': 'Tool calls requested',
        'function_call': 'Function call requested'
    };
    return reasonMap[reason] || reason;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Toggle function for expandable sections
function toggleDetails(element) {
    const content = element.parentElement.querySelector('.details-content');
    const icon = element.querySelector('.icon');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        if (icon) {
            icon.classList.remove('small-down');
            icon.classList.add('small-up');
        }
    } else {
        content.style.display = 'none';
        if (icon) {
            icon.classList.remove('small-up');
            icon.classList.add('small-down');
        }
    }
}

// Make functions available globally
window.formatTokensForDisplay = formatTokensForDisplay;
window.formatRuntimeAuditForDisplay = formatRuntimeAuditForDisplay;