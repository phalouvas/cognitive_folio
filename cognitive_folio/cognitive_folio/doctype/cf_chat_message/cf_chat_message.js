// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Chat Message", {
    
    refresh(frm) {
        // Add Send button
        if (!frm.is_new() && frm.doc.prompt) {
            frm.add_custom_button(__('Send'), function() {
                frm.call({
                    doc: frm.doc,
                    method: 'process',
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.show_alert({
                                message: __('Message sent for processing'),
                                indicator: 'blue'
                            });
                            if (frm.doc.chat) {
                                frappe.set_route('Form', 'CF Chat', frm.doc.chat);
                            }
                        }
                    }
                });
            }).addClass('btn-primary');
        }
    },
    
    template_prompt(frm) {
        // When template_prompt field is changed, fetch the content from CF Prompt
        if (frm.doc.template_prompt) {
            frappe.db.get_value('CF Prompt', frm.doc.template_prompt, 'content')
                .then(r => {
                    if (r.message && r.message.content) {
                        frm.set_value('prompt', r.message.content);
                    }
                });
        } else {
            // Clear prompt if template_prompt is cleared
            frm.set_value('prompt', '');
        }
    }
});