// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Portfolio", {
    refresh(frm) {
        // Only show buttons for saved documents (not new ones)
        if (!frm.is_new()) {
            // Add "Fetch All Prices" button
            frm.add_custom_button(__('Fetch All Prices'), function() {
                // Show loading indicator
                frappe.dom.freeze(__('Updating prices for all securities...'));
                
                // Call server-side method to update prices
                frm.call({
                    method: 'cognitive_folio.cognitive_folio.doctype.cf_portfolio.cf_portfolio.fetch_all_prices',
                    args: {
                        portfolio_name: frm.doc.name // Pass the current document's name
                    },
                    callback: function(r) {
                        frappe.dom.unfreeze();
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
                        frappe.dom.unfreeze();
                        frappe.msgprint(__('An error occurred while updating prices.'));
                    }
                });
            }, __('Actions'));
        }
    }
});