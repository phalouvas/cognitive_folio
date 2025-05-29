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
            }).addClass('btn-primary');
        }

        // Show Amend button if not new and not already amended
        if (!frm.is_new() && !frm.doc.amended_from) {
            frm.add_custom_button(__('Amend'), function() {
                frappe.call({
                    method: "cognitive_folio.cognitive_folio.doctype.cf_chat.cf_chat.amend_cf_chat",
                    args: { name: frm.doc.name },
                    callback: function(r) {
                        if (r.message) {
                            frappe.set_route("Form", "CF Chat", r.message);
                        }
                    }
                });
            });
        }

        // Load and display chat messages as timeline
        if (!frm.is_new()) {
            render_chat_timeline(frm);
            frappe.realtime.on('chat_message_completed', (data) => {
                render_chat_timeline(frm);
            });
        }
    }
});

function render_chat_timeline(frm) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'CF Chat Message',
            filters: {
                chat: frm.doc.name
            },
            fields: ['name', 'prompt', 'model', 'response_html', 'status', 'creation', 'modified', 'owner'],
            order_by: 'creation desc',
            limit_page_length: 0
        },
        callback: function(r) {
            if (r.message) {
                display_timeline(frm, r.message);
            }
        }
    });
}

function display_timeline(frm, messages) {
    let timeline_html = `
        <div class="chat-timeline">
            <div class="timeline-items">
    `;

    messages.forEach(function(message) {
        let creation_time = frappe.datetime.comment_when(message.creation);
        let status_indicator = "";
        let status_class = "";
        let dot_class = "timeline-dot";
        
        if (message.status === "Processing") {
            status_indicator = `<span class="indicator blue">Processing...</span>`;
            status_class = "processing";
            dot_class = "timeline-dot processing-dot";
        } else if (message.status === "Success") {
            status_indicator = `<span class="indicator green">Completed</span>`;
            status_class = "success";
            dot_class = "timeline-dot success-dot";
        } else if (message.status === "Failed") {
            status_indicator = `<span class="indicator red">Failed</span>`;
            status_class = "failed";
            dot_class = "timeline-dot failed-dot";
        } else {
            status_indicator = `<span class="indicator gray">Draft</span>`;
            status_class = "draft";
        }
        
        timeline_html += `
            <div class="timeline-item ${status_class}">
                <div class="${dot_class}"></div>
                <div class="timeline-content frappe-card">
                    <div class="timeline-message-box">
                        <span class="flex justify-between m-1 mb-3">
                            <span class="text-color flex">
                                <span class="margin-right">
                                    ${frappe.utils.icon('es-line-chat-alt', 'md')}
                                </span>
                                <div>
                                    <span class="text-muted">${creation_time}</span>
                                    ${status_indicator}
                                </div>
                            </span>
                            <span class="actions">
                                <a class="action-btn" href="/app/cf-chat-message/${message.name}" title="Open Message">
                                    ${frappe.utils.icon('link-url', 'sm')}
                                </a>
                            </span>
                        </span>
                        <div class="content">
                            ${message.prompt ? `<div class="chat-prompt"><strong>${message.owner}:<br></strong>${message.prompt}</div>` : ''}
                            ${message.response_html ? `<div class="chat-response mt-2"><strong>${message.model}:</strong><br>${message.response_html}</div>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    });

    timeline_html += `
            </div>
        </div>
    `;

    // Add some custom CSS for better styling
    let custom_css = `
        <style>
            .chat-timeline {
                position: relative;
                padding-top: var(--padding-lg);
            }
            .chat-timeline:before {
                content: " ";
                top: 90px;
                left: calc(var(--timeline-item-icon-size) / 2);
                position: absolute;
                border-left: 1px solid var(--dark-border-color);
                bottom: 25px;
            }
            .chat-timeline .timeline-item {
                position: relative;
                margin-left: var(--timeline-item-left-margin);
                margin-bottom: var(--timeline-item-bottom-margin);
            }
            .chat-timeline .timeline-dot {
                width: 16px;
                height: 16px;
                border-radius: 50%;
                position: absolute;
                left: calc(-1.25 * var(--timeline-item-left-margin) / 2);
                background: var(--bg-color);
                border: 2px solid var(--primary-color);
            }
            .chat-timeline .processing-dot {
                background: var(--blue-100);
                border: 2px solid var(--blue-500);
                animation: pulse 2s infinite;
            }
            .chat-timeline .success-dot {
                background: var(--green-100);
                border: 2px solid var(--green-500);
            }
            .chat-timeline .failed-dot {
                background: var(--red-100);
                border: 2px solid var(--red-500);
            }
            @keyframes pulse {
                0% {
                    transform: scale(1);
                    opacity: 1;
                }
                50% {
                    transform: scale(1.1);
                    opacity: 0.7;
                }
                100% {
                    transform: scale(1);
                    opacity: 1;
                }
            }
            .chat-timeline .add-message-dot {
                background: var(--primary-color);
                border: 2px solid var(--primary-color);
            }
            .chat-timeline .timeline-content {
                #max-width: var(--timeline-content-max-width);
                padding: var(--padding-sm);
                margin-left: var(--margin-md);
                color: var(--text-neutral);
                background-color: var(--bg-color);
                box-shadow: none;
                border: 1px solid var(--border-color);
                margin: calc(var(--timeline-item-bottom-margin) + var(--padding-md)) 0;
                margin-left: var(--margin-lg);
            }
            .chat-prompt {
                background-color: var(--control-bg);
                padding: 8px;
                border-radius: 4px;
                border-left: 3px solid var(--primary-color);
                max-height: 200px;
                overflow-y: auto;
            }
            .chat-response {
                padding: 8px;
                border-radius: 4px;
                border-left: 3px solid var(--green);
                max-height: 500px;
                overflow-y: auto;
            }
        </style>
    `;

    frm.fields_dict.messages.$wrapper.html(custom_css + timeline_html);
}