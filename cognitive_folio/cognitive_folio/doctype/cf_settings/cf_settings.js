// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Settings", {
    refresh(frm) {
        ensure_runtime_defaults(frm);

        // Add button to check Open WebUI API connectivity
        frm.add_custom_button(__('Refresh AI Models'), function() {
            check_openwebui_connection(frm);
        });
        
        // Populate default_ai_model select field
        populate_default_ai_model_options(frm);
    },
    
    // Update default_ai_model options when AI models are updated
    after_save(frm) {
        populate_default_ai_model_options(frm);
    }
});

function ensure_runtime_defaults(frm) {
    const defaults = {
        max_context_tokens: 120000,
        chat_default_max_tokens: 4000,
        reasoner_default_max_tokens: 32000,
        chat_max_tokens_cap: 8000,
        reasoner_max_tokens_cap: 64000,
        max_api_retries: 3,
        retry_backoff_base_seconds: 1.5,
        stream_flush_interval_seconds: 1.0,
        stream_flush_min_char_delta: 120,
    };

    let changed = false;

    Object.keys(defaults).forEach((fieldname) => {
        const currentValue = Number(frm.doc[fieldname] || 0);
        if (!(currentValue > 0)) {
            frm.set_value(fieldname, defaults[fieldname]);
            changed = true;
        }
    });

    if (changed) {
        frappe.show_alert({
            message: __('Applied default AI runtime values. Please save settings.'),
            indicator: 'blue'
        });
    }
}

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
                frm.reload_doc();
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
            frappe.dom.unfreeze();
            
            frappe.msgprint({
                title: __('Error'),
                indicator: 'red',
                message: __('An error occurred while connecting to Open WebUI API: ') + 
                    (err.message || 'Unknown error')
            });
        }
    });
}

function populate_default_ai_model_options(frm) {
    // Clear existing options
    frm.set_df_property('default_ai_model', 'options', []);
    
    const options = [];
    
    // Add an empty option at the beginning
    options.push({ value: '', label: __('-- Select Model --') });
    
    // Get models from the table
    if (frm.doc.ai_models && frm.doc.ai_models.length > 0) {
        frm.doc.ai_models.forEach(model => {
            if (model.model_id) {
                options.push({
                    value: model.model_id,
                    label: `${model.model_name || model.model_id} (${model.owned_by || ''})`
                });
            }
        });
    }
    
    // Set options to the select field
    frm.set_df_property('default_ai_model', 'options', options);
    
    // Refresh the field to show updated options
    frm.refresh_field('default_ai_model');
}