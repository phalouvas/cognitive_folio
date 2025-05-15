// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Settings", {
    refresh(frm) {
        // Add button to check Open WebUI API connectivity
        frm.add_custom_button(__('Check API Connection'), function() {
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
    
    // Show loading indicator
    frappe.show_alert({
        message: __('Checking connection to Open WebUI API...'),
        indicator: 'blue'
    });
    
    // Make a server-side call to check connection
    frappe.call({
        method: 'check_openwebui_connection',
        doc: frm.doc,
        callback: function(response) {
            if (response.message && response.message.success) {
                frappe.show_alert({
                    message: __('Connection to Open WebUI API successful!'),
                    indicator: 'green'
                });
            } else {
                frappe.msgprint({
                    title: __('Connection Failed'),
                    indicator: 'red',
                    message: __('Failed to connect to Open WebUI API: ') + 
                        (response.message && response.message.error ? response.message.error : 'Unknown error')
                });
            }
        }
    });
}