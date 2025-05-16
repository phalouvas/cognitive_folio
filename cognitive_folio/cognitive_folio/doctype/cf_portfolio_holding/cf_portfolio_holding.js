// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Portfolio Holding", {
	refresh(frm) {
        if (!frm.is_new()) {

            if(frm.doc.ai_suggestion) {
                let md_html = frappe.markdown(frm.doc.ai_suggestion);
                frm.set_df_property('ai_suggestion_html', 'options', 
                    `<div class="markdown-preview">${md_html}</div>`);
            }

            frm.add_custom_button(__('Fetch Ticker Info'), function() {
                frappe.dom.freeze(__('Fetching security data...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'fetch_current_price',
                    callback: function(r) {
                        // Unfreeze the GUI when operation completes
                        frappe.dom.unfreeze();
                        
                        frappe.show_alert({
                            message: __('Security data refreshed'),
                            indicator: 'green'
                        });
                        frm.refresh();
                    },
                    error: function(r) {
                        // Make sure to unfreeze even if there's an error
                        frappe.dom.unfreeze();
                    }
                });
            }, __('Actions'));
            
            // Add a new button for generating AI suggestion
            frm.add_custom_button(__('Generate AI Suggestion'), function() {
                // Only proceed if ticker info is available
                if (!frm.doc.security) {
                    frappe.msgprint({
                        title: __('Missing Data'),
                        indicator: 'yellow',
                        message: __('Please select a security first to generate AI suggestions')
                    });
                    return;
                }
                
                frappe.dom.freeze(__('Generating AI suggestion...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'generate_ai_suggestion',
                    callback: function(r) {
                        frappe.dom.unfreeze();
                        
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('AI suggestion generated successfully'),
                                indicator: 'green'
                            });
                            frm.refresh();
                        } else {
                            frappe.msgprint({
                                title: __('Error'),
                                indicator: 'red',
                                message: r.message && r.message.error ? 
                                    r.message.error : __('Failed to generate AI suggestion')
                            });
                        }
                    },
                    error: function() {
                        frappe.dom.unfreeze();
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('An error occurred while generating AI suggestion')
                        });
                    }
                });
            }, __('Actions'));
        }
	},
});
