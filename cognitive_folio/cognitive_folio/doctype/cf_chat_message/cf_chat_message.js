// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Chat Message", {
    
    refresh(frm) {
        set_model_options_from_settings(frm);

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
                            window.location.href = `/app/cf-chat/${frm.doc.chat}`;
                        }
                    }
                }
            });
        }).addClass('btn-primary');
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

function set_model_options_from_settings(frm) {
    frappe.call({
        method: 'cognitive_folio.cognitive_folio.doctype.cf_chat.cf_chat.get_available_ai_models'
    }).then((r) => {
        const models = (r.message || []).filter((model) => !!model);

        if (!models.length) {
            return;
        }

        if (frm.doc.model && !models.includes(frm.doc.model)) {
            models.unshift(frm.doc.model);
        }

        const modelOptions = [''].concat(models).join('\n');
        frm.set_df_property('model', 'options', modelOptions);
        frm.refresh_field('model');
    }).catch(() => {
        // Keep existing static options if model fetch fails
    });
}