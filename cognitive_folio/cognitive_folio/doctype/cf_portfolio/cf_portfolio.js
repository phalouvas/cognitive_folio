// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Portfolio", {
    refresh(frm) {
        // Only show buttons for saved documents (not new ones)
        if (!frm.is_new()) {
            // Add "Fetch All Prices" button
            frm.add_custom_button(__('Fetch Holdings Prices'), function() {
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
            }, __('Actions'));

            frm.add_custom_button(__('Generate Holdings AI Suggestions'), function() {
                frappe.confirm(
                    __('This will generate AI suggestions for all holdings in this portfolio. This may take some time. Continue?'),
                    function() {
                        frappe.dom.freeze(__('Generating AI suggestions for all holdings...'));
                        
                        frm.call({
                            doc: frm.doc,
                            method: 'generate_holdings_ai_suggestions',
                            callback: function(r) {
                                frappe.dom.unfreeze();
                                
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: __('AI suggestions generated successfully for ' + r.message.count + ' holdings'),
                                        indicator: 'green'
                                    });
                                    frm.refresh();
                                } else {
                                    frappe.msgprint({
                                        title: __('Error'),
                                        indicator: 'red',
                                        message: r.message && r.message.error ? 
                                            r.message.error : __('Failed to generate AI suggestions')
                                    });
                                }
                            },
                            error: function() {
                                frappe.dom.unfreeze();
                                frappe.msgprint({
                                    title: __('Error'),
                                    indicator: 'red',
                                    message: __('An error occurred while generating AI suggestions')
                                });
                            }
                        });
                    }
                );
            }, __('Actions'));
        }
    }
});