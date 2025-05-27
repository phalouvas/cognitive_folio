// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Chat Message", {
	refresh(frm) {
		// Start polling if status is Processing
		if (frm.doc.status === "Processing") {
			frm.trigger("start_status_polling");
		}
		
		// Set status indicator
		frm.trigger("set_status_indicator");
	},

	start_status_polling(frm) {
		// Clear any existing interval
		if (frm.status_polling_interval) {
			clearInterval(frm.status_polling_interval);
		}

		// Start polling every 5 seconds
		frm.status_polling_interval = setInterval(() => {
			// Check if we're still on the same document
			if (!frm.doc || frm.doc.name !== frm.docname || !frm.$wrapper.is(":visible")) {
				clearInterval(frm.status_polling_interval);
				frm.status_polling_interval = null;
				return;
			}

			// Check current status
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "CF Chat Message",
					filters: { name: frm.doc.name },
					fieldname: ["status", "response", "response_html"]
				},
				callback: function(r) {
					if (r.message) {
						let current_status = r.message.status;
						
						// Update the form if status changed
						if (current_status !== frm.doc.status) {
							frm.set_value("status", current_status);
							
							// Update response fields if they changed
							if (r.message.response !== frm.doc.response) {
								frm.set_value("response", r.message.response);
							}
							if (r.message.response_html !== frm.doc.response_html) {
								frm.set_value("response_html", r.message.response_html);
							}
							
							frm.trigger("set_status_indicator");
						}
						
						// Stop polling if status is final
						if (current_status === "Success" || current_status === "Failed") {
							clearInterval(frm.status_polling_interval);
							frm.status_polling_interval = null;
							
							// Show completion message
							if (current_status === "Success") {
								frappe.show_alert({
									message: __("Chat message processed successfully"),
									indicator: "green"
								});
							} else {
								frappe.show_alert({
									message: __("Chat message processing failed"),
									indicator: "red"
								});
							}
						}
					}
				}
			});
		}, 5000);
	},

	set_status_indicator(frm) {
		// Set page indicator based on status
		if (frm.doc.status === "Processing") {
			frm.page.set_indicator(__("Processing"), "blue");
		} else if (frm.doc.status === "Success") {
			frm.page.set_indicator(__("Success"), "green");
		} else if (frm.doc.status === "Failed") {
			frm.page.set_indicator(__("Failed"), "red");
		} else {
			frm.page.set_indicator(__("Draft"), "gray");
		}
	},

	// Clean up interval when form is hidden/destroyed
	onload(frm) {
		// Listen for realtime updates
		frappe.realtime.on('chat_message_completed', (data) => {
			if (data.message_id === frm.doc.name) {
				// Stop polling since we got realtime update
				if (frm.status_polling_interval) {
					clearInterval(frm.status_polling_interval);
					frm.status_polling_interval = null;
				}
				
				// Reload the document to get latest data
				frm.reload_doc();
			}
		});
	},

	before_unload(frm) {
		if (frm.status_polling_interval) {
			clearInterval(frm.status_polling_interval);
			frm.status_polling_interval = null;
		}
	}
});
