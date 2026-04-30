// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Portfolio", {
    refresh(frm) {
        // Only show buttons for saved documents (not new ones)
        if (!frm.is_new()) {

            // Add "Fetch All Prices" button
            frm.add_custom_button(__('Fetch Latest Data'), function() {
                frm.call({
                    method: 'fetch_holdings_data',
                    args: {
                        with_fundamentals: false
                    },
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message) {
                            const summary = r.message;
                            if (summary.all_succeeded) {
                                frappe.show_alert({
                                    message: __('Updated {0} of {1} holdings successfully', [summary.updated, summary.total]),
                                    indicator: 'green'
                                }, 5);
                            } else {
                                frappe.msgprint({
                                    title: __('Partial Update'),
                                    indicator: 'orange',
                                    message: __('Updated {0} of {1} holdings. {2} holding(s) failed. Check the Error Log for details.', [summary.updated, summary.total, summary.failed])
                                });
                            }
                            frm.reload_doc();
                        }
                    },
                    error: function() {
                        // Unfreeze UI in case of an error
                        frappe.msgprint(__('An error occurred while updating prices.'));
                    }
                });
            }, __('Holdings'));
            
            frm.add_custom_button(__('Fetch Fundamentals'), function() {
                frm.call({
                    method: 'fetch_holdings_data',
                    doc: frm.doc,
                    args: {
                        with_fundamentals: true
                    },
                    callback: function(r) {
                        if (r.message) {
                            const summary = r.message;
                            if (summary.all_succeeded) {
                                frappe.show_alert({
                                    message: __('Updated {0} of {1} holdings successfully', [summary.updated, summary.total]),
                                    indicator: 'green'
                                }, 5);
                            } else {
                                frappe.msgprint({
                                    title: __('Partial Update'),
                                    indicator: 'orange',
                                    message: __('Updated {0} of {1} holdings. {2} holding(s) failed. Check the Error Log for details.', [summary.updated, summary.total, summary.failed])
                                });
                            }
                            frm.reload_doc();
                        }
                    },
                    error: function() {
                        // Unfreeze UI in case of an error
                        frappe.msgprint(__('An error occurred while updating prices.'));
                    }
                });
            }, __('Holdings'));

            frm.add_custom_button(__('Generate AI Suggestions'), function() {
                frappe.confirm(
                    __('This will queue AI suggestion generation for all holdings in the background. Continue?'),
                    function() {
                        frappe.show_alert({
                            message: __('Queueing AI suggestion jobs...'),
                            indicator: 'blue'
                        });
                        
                        frm.call({
                            doc: frm.doc,
                            method: 'generate_holdings_ai_suggestions',
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: __('Queued {0} AI suggestion jobs', [r.message.count]),
                                        indicator: 'green'
                                    });
                                } else {
                                    frappe.msgprint({
                                        title: __('Error'),
                                        indicator: 'red',
                                        message: r.message && r.message.error ? 
                                            r.message.error : __('Failed to queue AI suggestions')
                                    });
                                }
                            }
                        });
                    }
                );
            }, __('Holdings'));
            
            // Add button to update purchase prices from market data
            frm.add_custom_button(__('Update Purchase Prices'), function() {
                frappe.confirm(
                    __('This will update all holdings to use current market closing prices as purchase prices. This will affect profit/loss calculations. Continue?'),
                    function() {
                        
                        frm.call({
                            method: 'update_purchase_prices_from_market',
                            doc: frm.doc,
                            callback: function(r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: __('Updated purchase prices for ' + r.message + ' holdings'),
                                        indicator: 'green'
                                    });
                                    setTimeout(function() {
                                        frm.reload_doc();
                                    }, 5);
                                } else {
                                    frappe.msgprint({
                                        title: __('Error'),
                                        indicator: 'red',
                                        message: __('Failed to update purchase prices')
                                    });
                                }
                            },
                            error: function() {
                                frappe.msgprint(__('An error occurred while updating purchase prices.'));
                            }
                        });
                    }
                );
            }, __('Holdings'));

            // Add "Generate Portfolio AI Analysis" button
            frm.add_custom_button(__('Generate AI Analysis'), function() {
                frappe.dom.freeze(__('Generating portfolio analysis...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'generate_portfolio_ai_analysis',
                    callback: function(r) {
                        frappe.dom.unfreeze();
                        
                        if (r.message && r.message.success) {
                            frm.reload_doc();
                        } else {
                            frappe.msgprint({
                                title: __('Error'),
                                indicator: 'red',
                                message: r.message && r.message.error ? 
                                    r.message.error : __('Failed to generate portfolio analysis')
                            });
                        }
                    },
                    error: function() {
                        frappe.dom.unfreeze();
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('An error occurred while generating portfolio analysis')
                        });
                    }
                });
            }, __('Actions'));

            // Add button to calculate portfolio performance metrics
            frm.add_custom_button(__('Calculate Performance'), function() {
                frappe.dom.freeze(__('Calculating portfolio performance...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'calculate_portfolio_performance',
                    callback: function(r) {
                        frappe.dom.unfreeze();
                        
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Portfolio performance metrics calculated successfully'),
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        } else {
                            frappe.msgprint({
                                title: __('Error'),
                                indicator: 'red',
                                message: r.message && r.message.error ? 
                                    r.message.error : __('Failed to calculate portfolio performance')
                            });
                        }
                    },
                    error: function() {
                        frappe.dom.unfreeze();
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('An error occurred while calculating portfolio performance')
                        });
                    }
                });
            }, __('Actions'));

            frm.add_custom_button(__('Evaluate News'), function() {
                frm.call({
                    method: 'evaluate_holdings_news',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message) {
                            frm.reload_doc();
                        }
                    },
                    error: function() {
                        // Unfreeze UI in case of an error
                        frappe.msgprint(__('An error occurred while evaluating news.'));
                    }
                });
            }, __('Actions'));

            // Add "Ask AI" button — opens ph_agent chat with portfolio context
            frm.page.add_inner_button(__('Ask AI'), function() {
                // First find the Financial Advisor persona and its default LLM provider
                frappe.db.get_value('Persona', {persona_name: 'Financial Advisor'}, ['name', 'default_llm_provider'])
                    .then(pr => {
                        let persona = pr.message && pr.message.name;
                        let llm_provider = pr.message && pr.message.default_llm_provider;
                        if (!persona) {
                            frappe.msgprint(__('Financial Advisor persona not found. Please ensure ph_agent is installed.'));
                            return;
                        }
                        // If persona has no default provider, find the first enabled one
                        if (!llm_provider) {
                            frappe.db.get_value('LLM Provider', {is_enabled: 1}, 'name')
                                .then(lr => {
                                    llm_provider = lr.message && lr.message.name;
                                    _create_or_reopen_chat_session(frm, 'CF Portfolio', frm.doc.portfolio_name, persona, llm_provider);
                                });
                        } else {
                            _create_or_reopen_chat_session(frm, 'CF Portfolio', frm.doc.portfolio_name, persona, llm_provider);
                        }
                    });
            }, __('AI'));

            // Add "Chat Sessions" section — list past sessions for this portfolio
            _render_chat_sessions_section(frm, 'CF Portfolio', frm.doc.name);
        }
    },

    template_prompt(frm) {
        // When template_prompt field is changed, fetch the content from CF Prompt
        if (frm.doc.template_prompt) {
            frappe.db.get_value('CF Prompt', frm.doc.template_prompt, 'content')
                .then(r => {
                    if (r.message && r.message.content) {
                        frm.set_value('ai_prompt', r.message.content);
                    }
                });
        } else {
            // Clear prompt if template_prompt is cleared
            frm.set_value('ai_prompt', '');
        }
    }
});

/**
 * Create or reopen a ph_agent Chat Session linked to a document.
 */
function _create_or_reopen_chat_session(frm, ref_doctype, title, persona, llm_provider) {
    if (!llm_provider) {
        frappe.msgprint(__('No LLM Provider found. Please configure one in PH Agent > LLM Provider.'));
        return;
    }
    
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Chat Session',
            filters: {
                reference_doctype: ref_doctype,
                reference_name: frm.doc.name,
                user: frappe.session.user,
                status: 'Open'
            },
            fieldname: ['name', 'title']
        },
        callback: function(r) {
            if (r.message && r.message.name) {
                // Reopen existing session
                window.open('/app/chat?session=' + r.message.name, '_blank');
            } else {
                // Create new session
                frappe.call({
                    method: 'frappe.client.insert',
                    args: {
                        doc: {
                            doctype: 'Chat Session',
                            title: title,
                            persona: persona,
                            llm_provider: llm_provider,
                            reference_doctype: ref_doctype,
                            reference_name: frm.doc.name,
                            user: frappe.session.user,
                            status: 'Open',
                            is_temporary: 0
                        }
                    },
                    callback: function(create_r) {
                        if (create_r.message && create_r.message.name) {
                            window.open('/app/chat?session=' + create_r.message.name, '_blank');
                            frm.reload_doc();
                        }
                    }
                });
            }
        }
    });
}

/**
 * Render a "Chat Sessions" section on the form showing past ph_agent sessions
 * linked to this document.
 */
function _render_chat_sessions_section(frm, ref_doctype, ref_name) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Chat Session',
            filters: {
                reference_doctype: ref_doctype,
                reference_name: ref_name,
                user: frappe.session.user
            },
            fields: ['name', 'title', 'modified', 'persona', 'status'],
            order_by: 'modified desc',
            limit_page_length: 10
        },
        callback: function(r) {
            if (!r.message || r.message.length === 0) return;
            
            let rows = r.message.map(s => {
                let status_badge = s.status === 'Open' 
                    ? '<span class="indicator green">Open</span>'
                    : '<span class="indicator grey">' + s.status + '</span>';
                let modified = frappe.datetime.comment_when(s.modified);
                return `<tr>
                    <td><a href="/app/chat?session=${s.name}" target="_blank">${s.title || s.name}</a></td>
                    <td>${s.persona || '-'}</td>
                    <td>${status_badge}</td>
                    <td>${modified}</td>
                </tr>`;
            }).join('');
            
            let html = `<div class="frappe-control" style="margin-top: 15px;">
                <label class="control-label" style="margin-bottom: 5px;">${__('Chat Sessions')}</label>
                <div class="control-value">
                    <table class="table table-bordered table-hover" style="margin-bottom: 0;">
                        <thead><tr>
                            <th>${__('Session')}</th>
                            <th>${__('Persona')}</th>
                            <th>${__('Status')}</th>
                            <th>${__('Last Activity')}</th>
                        </tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>`;
            
            // Add the HTML after the main form actions
            if (frm.fields_dict.chat_sessions_html) {
                frm.set_df_property('chat_sessions_html', 'options', html);
            }
        }
    });
}