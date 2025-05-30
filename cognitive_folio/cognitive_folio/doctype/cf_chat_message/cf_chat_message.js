// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Chat Message", {
    
    after_save(frm) {
        // Redirect to parent chat immediately after save
        if (frm.doc.chat) {
            frappe.set_route('Form', 'CF Chat', frm.doc.chat);
        }
    }
});