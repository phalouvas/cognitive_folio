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
    }
};
