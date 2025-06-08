frappe.listview_settings['CF Portfolio Holding'] = frappe.listview_settings['CF Portfolio Holding'] || {};

frappe.listview_settings['CF Portfolio Holding'].onload = function(listview) {
    // Add "Fetch Latest Data" button under Actions
    if (frappe.model.can_create("CF Portfolio Holding")) {
        listview.page.add_action_item(__("Fetch Latest Data"), function() {
            const selected_docs = listview.get_checked_items();
            const docnames = listview.get_checked_items(true);

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Portfolio Holding"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_portfolio_holding.cf_portfolio_holding.fetch_data_selected",
                args: {
                    docnames: docnames,
                    with_fundamentals: false
                },
                freeze: true,
                freeze_message: __("Processing..."),
                callback: function(r) {
                    if (!r.exc) {
                        listview.refresh();
                    }
                }
            });
        });

        listview.page.add_action_item(__("Fetch Fundamentals"), function() {
            const selected_docs = listview.get_checked_items();
            const docnames = listview.get_checked_items(true);

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Portfolio Holding"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_portfolio_holding.cf_portfolio_holding.fetch_data_selected",
                args: {
                    docnames: docnames,
                    with_fundamentals: true
                },
                freeze: true,
                freeze_message: __("Processing..."),
                callback: function(r) {
                    if (!r.exc) {
                        listview.refresh();
                    }
                }
            });
        });

        listview.page.add_action_item(__("Generate AI Suggestion"), function() {
            const selected_docs = listview.get_checked_items();
            const docnames = listview.get_checked_items(true);

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Portfolio Holding"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_portfolio_holding.cf_portfolio_holding.generate_ai_suggestion_selected",
                args: {
                    docnames: docnames,
                    with_fundamentals: true
                },
                freeze: true,
                freeze_message: __("Processing..."),
                callback: function(r) {
                    if (!r.exc) {
                        listview.refresh();
                    }
                }
            });
        });

        listview.page.add_action_item(__("Copy to Portfolio"), function() {
            const selected_docs = listview.get_checked_items();

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Portfolio Holding"));
                return;
            }

            // Show dialog to select target portfolio
            let dialog = new frappe.ui.Dialog({
                title: __('Copy Holdings to Portfolio'),
                fields: [
                    {
                        label: __('Target Portfolio'),
                        fieldname: 'target_portfolio',
                        fieldtype: 'Link',
                        options: 'CF Portfolio',
                        reqd: 1,
                        description: __('Select the portfolio where you want to copy the selected holdings')
                    }
                ],
                primary_action_label: __('Copy Holdings'),
                primary_action(values) {
                    if (!values.target_portfolio) {
                        frappe.throw(__("Please select a target portfolio"));
                        return;
                    }

                    // Prepare holdings data for copying
                    const holdings_data = selected_docs.map(doc => ({
                        portfolio: values.target_portfolio,
                        security: doc.security,
                        quantity: doc.quantity,
                        average_purchase_price: doc.average_purchase_price
                    }));

                    frappe.call({
                        method: "cognitive_folio.cognitive_folio.doctype.cf_portfolio_holding.cf_portfolio_holding.copy_holdings_to_portfolio",
                        args: {
                            holdings_data: holdings_data
                        },
                        freeze: true,
                        freeze_message: __("Copying holdings..."),
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.show_alert({
                                    message: __('Holdings copied successfully to {0}', [values.target_portfolio]),
                                    indicator: 'green'
                                });
                                dialog.hide();
                                listview.refresh();
                            }
                        }
                    });
                }
            });

            dialog.show();
        });
    }
};
