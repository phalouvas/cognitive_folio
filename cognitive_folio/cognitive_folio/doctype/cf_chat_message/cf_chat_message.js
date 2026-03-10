// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Chat Message", {
    
    refresh(frm) {
        set_model_options_from_settings(frm);
        format_tokens_and_audit_data(frm);

        frm.add_custom_button(__('Send'), function() {
            frm.call({
                doc: frm.doc,
                method: 'process',
                callback: function(r) {
                    if (!r.exc) {
                        frappe.show_alert({
                            message: __('Message sent for processing'),
                            indicator: 'blue'
                        });
                        if (frm.doc.chat) {
                            window.location.href = `/app/cf-chat/${frm.doc.chat}`;
                        }
                    }
                }
            });
        }).addClass('btn-primary');
        
        // Add button to refresh formatted display
        if (!frm.is_new() && (frm.doc.tokens || frm.doc.runtime_audit)) {
            frm.add_custom_button(__('Refresh Formatted Display'), function() {
                format_tokens_and_audit_data(frm, true);
                frappe.show_alert({
                    message: __('Formatted display refreshed'),
                    indicator: 'green'
                });
            }, __('Actions'));
        }
    },
    
    template_prompt(frm) {
        // When template_prompt field is changed, fetch the content from CF Prompt
        if (frm.doc.template_prompt) {
            frappe.db.get_value('CF Prompt', frm.doc.template_prompt, 'content')
                .then(r => {
                    if (r.message && r.message.content) {
                        frm.set_value('prompt', r.message.content);
                    }
                });
        } else {
            // Clear prompt if template_prompt is cleared
            frm.set_value('prompt', '');
        }
    }
});

function set_model_options_from_settings(frm) {
    frappe.call({
        method: 'cognitive_folio.cognitive_folio.doctype.cf_chat.cf_chat.get_available_ai_models'
    }).then((r) => {
        const models = (r.message || []).filter((model) => !!model);

        if (!models.length) {
            return;
        }

        if (frm.doc.model && !models.includes(frm.doc.model)) {
            models.unshift(frm.doc.model);
        }

        const modelOptions = [''].concat(models).join('\n');
        frm.set_df_property('model', 'options', modelOptions);
        frm.refresh_field('model');
    }).catch(() => {
        // Keep existing static options if model fetch fails
    });
}

/**
 * Format tokens and runtime audit data into human-readable HTML
 * @param {Object} frm - Form object
 * @param {boolean} forceRefresh - Whether to force refresh even if HTML already exists
 */
function format_tokens_and_audit_data(frm, forceRefresh = false) {
    // Load formatting utilities
    frappe.require([
        '/assets/cognitive_folio/js/chat_formatters.js',
        '/assets/cognitive_folio/css/chat_audit.css'
    ], function() {
        // Format tokens if data exists
        if (frm.doc.tokens && (forceRefresh || !frm.doc.tokens_html)) {
            try {
                const tokensHtml = window.formatTokensForDisplay(frm.doc.tokens);
                frm.set_df_property('tokens_html', 'options', tokensHtml);
            } catch (error) {
                console.error('Error formatting tokens:', error);
                frm.set_df_property('tokens_html', 'options', 
                    `<div class="text-danger">Error formatting token data: ${error.message}</div>`);
            }
        }
        
        // Format runtime audit if data exists
        if (frm.doc.runtime_audit && (forceRefresh || !frm.doc.runtime_audit_html)) {
            try {
                const auditHtml = window.formatRuntimeAuditForDisplay(frm.doc.runtime_audit);
                frm.set_df_property('runtime_audit_html', 'options', auditHtml);
            } catch (error) {
                console.error('Error formatting runtime audit:', error);
                frm.set_df_property('runtime_audit_html', 'options', 
                    `<div class="text-danger">Error formatting audit data: ${error.message}</div>`);
            }
        }
        
        // Refresh fields to show formatted content
        frm.refresh_field('tokens_html');
        frm.refresh_field('runtime_audit_html');
    });
}