frappe.listview_settings['CF Security'] = frappe.listview_settings['CF Security'] || {};

frappe.listview_settings['CF Security'].onload = function(listview) {
    // Add "Fetch Latest Data" button under Actions
    if (frappe.model.can_create("CF Security")) {
        listview.page.add_action_item(__("Fetch Latest Data"), function() {
            const selected_docs = listview.get_checked_items();
            const docnames = listview.get_checked_items(true);

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Security"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.fetch_data_selected",
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
                frappe.throw(__("Please select at least one CF Security"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.fetch_data_selected",
                args: {
                    docnames: docnames
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
                frappe.throw(__("Please select at least one CF Security"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.generate_ai_suggestion_selected",
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
