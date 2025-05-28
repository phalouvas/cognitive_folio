// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Portfolio", {
    refresh(frm) {
        // Only show buttons for saved documents (not new ones)
        if (!frm.is_new()) {

            if(frm.doc.ai_suggestion) {
                let md_html = frappe.markdown(frm.doc.ai_suggestion);
                frm.set_df_property('ai_suggestion_html', 'options', frm.doc.ai_suggestion);
            } else {
                frm.set_df_property('ai_suggestion_html', 'options',
                    `<div class="text-muted">No AI suggestion available.</div>`);
            }
            
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
            
            frm.add_custom_button(__('Fetch Fundamentals'), function() {
                frm.call({
                    method: 'fetch_holdings_data',
                    doc: frm.doc,
                    args: {
                        with_fundamentals: true
                    },
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
        }
    },

    onload(frm) {
        // Listen for realtime updates from portfolio AI analysis
        frappe.realtime.on('portfolio_ai_analysis_completed', (data) => {
            if (data.portfolio_id === frm.doc.name) {
                // Reload the document to get latest data
                frm.reload_doc();
                
                // Play notification sound
                try {
                    const audio = new Audio('/assets/cognitive_folio/sounds/notification.mp3');
                    audio.volume = 0.5;
                    audio.play();
                } catch (e) {
                    console.log('Audio play failed:', e);
                }
                
                // Show notification based on status
                if (data.status === 'success') {
                    frappe.show_alert({
                        message: __("Portfolio AI analysis completed successfully"),
                        indicator: "green"
                    });
                    
                    // Optionally open the created chat
                    if (data.chat_id) {
                        setTimeout(() => {
                            frappe.set_route('Form', 'CF Chat', data.chat_id);
                        }, 2000); // Wait 2 seconds before redirecting
                    }
                } else if (data.status === 'error') {
                    frappe.show_alert({
                        message: __("Portfolio AI analysis failed: " + data.error),
                        indicator: "red"
                    });
                }
            }
        });
    }
});