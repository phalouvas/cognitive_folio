// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Chat Message", {
	
	// Listen for realtime updates
	onload(frm) {
		frappe.realtime.on('chat_message_completed', (data) => {
			if (data.message_id === frm.doc.name) {
				// Reload the document to get latest data
				frm.reload_doc();
			}
		});
	}
});
