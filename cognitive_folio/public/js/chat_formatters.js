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

        // Full details expandable section
        html += `
            <div class="full-details frappe-card">
                <a href="#" class="details-toggle" onclick="toggleDetails(this); return false;">
                    <h6 class="mb-0 d-inline">
                        ${frappe.utils.icon('small-down', 'sm')}
                        Full Token Details
                    </h6>
                </a>
                <div class="details-content mt-2" style="display: none;">
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

            if (audit.web_search.queries) {
                const queryCount = Array.isArray(audit.web_search.queries) ? audit.web_search.queries.length : 0;
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Queries</div>
                        <div class="font-weight-bold">${formatNumber(queryCount)}</div>
                    </div>
                `;
            }

            if (audit.web_search.results) {
                const resultCount = Array.isArray(audit.web_search.results) ? audit.web_search.results.length : 0;
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Results</div>
                        <div class="font-weight-bold">${formatNumber(resultCount)}</div>
                    </div>
                `;
            }

            if (audit.web_search.duration_ms !== undefined) {
                html += `
                    <div class="col-sm-4 mb-2">
                        <div class="text-muted small">Search Time</div>
                        <div class="font-weight-bold">${formatDuration(audit.web_search.duration_ms)}</div>
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

        // Full details expandable section
        html += `
            <div class="full-details frappe-card">
                <a href="#" class="details-toggle" onclick="toggleDetails(this); return false;">
                    <h6 class="mb-0 d-inline">
                        ${frappe.utils.icon('small-down', 'sm')}
                        Full Audit Details
                    </h6>
                </a>
                <div class="details-content mt-2" style="display: none;">
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