// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Prompt", {
    refresh(frm) {
        // Add copy buttons for multiple fields only for existing documents
        if (!frm.doc.__islocal) {
            const fieldsWithCopyButtons = ['content'];
            fieldsWithCopyButtons.forEach(fieldName => {
                addCopyButtonToField(frm, fieldName);
            });
            
            // Add custom button to copy prompt to securities
            frm.add_custom_button(__('Copy to CF Securities'), function() {
                // Show confirmation dialog
                frappe.confirm(
                    __('This will copy the Content field to the AI Prompt field of ALL CF Security records. This will overwrite existing ai_prompt values. Are you sure you want to continue?'),
                    function() {
                        // Call server-side method on the document
                        frm.call({
                            doc: frm.doc,
                            method: 'copy_prompt_to_securities',
                            callback: function(r) {
                                if (!r.exc) {
                                    frappe.show_alert({
                                        message: __('Successfully copied to CF Security records'),
                                        indicator: 'green'
                                    });
                                }
                            }
                        });
                    }
                );
            }, __('Actions'));
        }
    },
});

// Add this helper function after the frappe.ui.form.on block
function addCopyButtonToField(frm, fieldName) {
    if (frm.doc[fieldName]) {
        // Get the field wrapper
        const field = frm.get_field(fieldName);
        if (field && field.$wrapper) {
            // Remove any existing copy button first
            field.$wrapper.find('.copy-btn').remove();
            
            // Create a small copy button
            const copyBtn = $(`
                <button type="button" class="btn btn-xs btn-default copy-btn" 
                        style="margin-left: 5px; padding: 2px 8px; font-size: 11px;">
                    <i class="fa fa-copy"></i> Copy
                </button>
            `);
            
            // Add click handler
            copyBtn.on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                // Use the modern Clipboard API
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(frm.doc[fieldName]).then(function() {
                        frappe.show_alert({
                            message: __(`${getFieldDisplayName(fieldName)} data copied to clipboard`),
                            indicator: 'green'
                        });
                    }).catch(function(err) {
                        console.error('Failed to copy: ', err);
                        frappe.msgprint({
                            title: __('Copy Error'),
                            indicator: 'red',
                            message: __(`Failed to copy ${getFieldDisplayName(fieldName)} data to clipboard`)
                        });
                    });
                } else {
                    // Fallback for older browsers or non-secure contexts
                    try {
                        const textArea = document.createElement('textarea');
                        textArea.value = frm.doc[fieldName];
                        textArea.style.position = 'fixed';
                        textArea.style.opacity = '0';
                        document.body.appendChild(textArea);
                        textArea.focus();
                        textArea.select();
                        
                        const successful = document.execCommand('copy');
                        document.body.removeChild(textArea);
                        
                        if (successful) {
                            frappe.show_alert({
                                message: __(`${getFieldDisplayName(fieldName)} data copied to clipboard`),
                                indicator: 'green'
                            });
                        } else {
                            throw new Error('Copy command failed');
                        }
                    } catch (err) {
                        console.error('Fallback copy failed: ', err);
                        frappe.msgprint({
                            title: __('Copy Error'),
                            indicator: 'red',
                            message: __(`Failed to copy ${getFieldDisplayName(fieldName)} data to clipboard`)
                        });
                    }
                }
            });
            
            // Append the button to the field's label area
            field.$wrapper.find('.control-label').append(copyBtn);
        }
    }
}

function getFieldDisplayName(fieldName) {
    const fieldDisplayNames = {
        'content': 'Content',
        'title': 'Title'
    };
    return fieldDisplayNames[fieldName] || fieldName;
}