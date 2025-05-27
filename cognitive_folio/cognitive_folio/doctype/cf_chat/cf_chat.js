// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Chat", {
	refresh(frm) {
		// Add custom button to quickly add new message
		if (!frm.is_new()) {
			frm.add_custom_button(__('Add Message'), function() {
				frappe.new_doc('CF Chat Message', {
					chat: frm.doc.name
				});
			});
		}
	}
});
