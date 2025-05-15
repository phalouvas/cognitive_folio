// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Settings", {
    refresh(frm) {
        // Add button to check Open WebUI API connectivity
        frm.add_custom_button(__('Refresh AI Models'), function() {
            check_openwebui_connection(frm);
        });
    },
});

function check_openwebui_connection(frm) {
    // Save the form first to ensure all values are up to date
    if(frm.doc.__unsaved) {
        frappe.throw(__('Please save the document before checking connection'));
        return;
    }
    
    frappe.dom.freeze(__('Connecting to Open WebUI API and fetching models...'));
    
    // Make a server-side call to check connection
    frappe.call({
        method: 'check_openwebui_connection',
        doc: frm.doc,
        callback: function(response) {
            frappe.dom.unfreeze();
            
            if (response.message && response.message.success) {
                frappe.show_alert({
                    message: __('Connection to Open WebUI API successful!'),
                    indicator: 'green'
                });
                frm.refresh();
            } else {
                frappe.msgprint({
                    title: __('Connection Failed'),
                    indicator: 'red',
                    message: __('Failed to connect to Open WebUI API: ') + 
                        (response.message && response.message.error ? response.message.error : 'Unknown error')
                });
            }
        },
        error: function(err) {
            // Also unfreeze in case of error
            frappe.dom.freeze();
            
            frappe.msgprint({
                title: __('Error'),
                indicator: 'red',
                message: __('An error occurred while connecting to Open WebUI API: ') + 
                    (err.message || 'Unknown error')
            });
        }
    });
}