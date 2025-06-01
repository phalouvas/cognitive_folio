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
                method: "cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.fetch_selected_data",
                args: {
                    docnames: docnames,
                    with_fundamentals: false
                },
                freeze: true,
                freeze_message: __("Fetching Latest Data..."),
                callback: function(r) {
                    if (!r.exc) {
                        if (r.message && r.message.name) {
                            frappe.set_route("Form", "CF Security", r.message.name);
                        }
                        
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
                method: "cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.fetch_selected_data",
                args: {
                    docnames: docnames,
                    with_fundamentals: true
                },
                freeze: true,
                freeze_message: __("Fetching Latest Data..."),
                callback: function(r) {
                    if (!r.exc) {
                        if (r.message && r.message.name) {
                            frappe.set_route("Form", "CF Security", r.message.name);
                        }
                        
                        listview.refresh();
                    }
                }
            });
        });
    }
};
