// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Portfolio", {
    refresh(frm) {
        // Only show buttons for saved documents (not new ones)
        if (!frm.is_new()) {

            if(frm.doc.ai_suggestion) {
                let md_html = frappe.markdown(frm.doc.ai_suggestion);
                frm.set_df_property('ai_suggestion_html', 'options', 
                    `<div class="markdown-preview">${md_html}</div>`);
            } else {
                frm.set_df_property('ai_suggestion_html', 'options',
                    `<div class="markdown-preview">No AI suggestion available.</div>`);
            }
            
            // Add "Fetch All Prices" button
            frm.add_custom_button(__('Fetch Prices'), function() {
                // Show loading indicator
                
                // Call server-side method to update prices
                frm.call({
                    method: 'fetch_all_prices',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: __('Updated prices for ' + r.message + ' securities'),
                                indicator: 'green'
                            }, 5);
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
            
            // Add "Generate Portfolio AI Analysis" button
            frm.add_custom_button(__('Generate AI Analysis'), function() {
                frappe.confirm(
                    __('This will generate an AI analysis for the entire portfolio. Continue?'),
                    function() {
                        frappe.dom.freeze(__('Generating portfolio analysis...'));
                        
                        frm.call({
                            doc: frm.doc,
                            method: 'generate_portfolio_ai_analysis',
                            callback: function(r) {
                                frappe.dom.unfreeze();
                                
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: __('Portfolio analysis generated successfully'),
                                        indicator: 'green'
                                    });
                                    frm.refresh();
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
                    }
                );
            }, __('Actions'));

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
                            frm.refresh();
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
        }
    }
});