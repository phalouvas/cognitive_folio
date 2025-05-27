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

        // Load and display chat messages as timeline
        if (!frm.is_new()) {
            render_chat_timeline(frm);
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
            fields: ['name', 'prompt', 'response', 'creation', 'modified'],
            order_by: 'creation asc',
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
        let prompt_content = message.prompt ? frappe.utils.escape_html(message.prompt.substring(0, 200)) : '';
        let response_content = message.response ? frappe.utils.escape_html(message.response.substring(0, 300)) : '';
        
        timeline_html += `
            <div class="timeline-item">
                <div class="timeline-dot"></div>
                <div class="timeline-content frappe-card">
                    <div class="timeline-message-box">
                        <span class="flex justify-between m-1 mb-3">
                            <span class="text-color flex">
                                <span class="margin-right">
                                    ${frappe.utils.icon('es-line-chat-alt', 'md')}
                                </span>
                                <div>
                                    <strong>Chat Message</strong>
                                    <span> · </span>
                                    <span class="text-muted">${creation_time}</span>
                                </div>
                            </span>
                            <span class="actions">
                                <a class="action-btn" href="/app/cf-chat-message/${message.name}" title="Open Message">
                                    ${frappe.utils.icon('link-url', 'sm')}
                                </a>
                            </span>
                        </span>
                        <div class="content">
                            ${prompt_content ? `<div class="chat-prompt"><strong>Prompt:</strong><br>${prompt_content}${message.prompt.length > 200 ? '...' : ''}</div>` : ''}
                            ${response_content ? `<div class="chat-response mt-2"><strong>Response:</strong><br>${response_content}${message.response.length > 300 ? '...' : ''}</div>` : ''}
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
            .chat-timeline .timeline-content {
                max-width: var(--timeline-content-max-width);
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
            }
            .chat-response {
                background-color: var(--bg-light-gray);
                padding: 8px;
                border-radius: 4px;
                border-left: 3px solid var(--green);
            }
        </style>
    `;

    frm.fields_dict.messages.$wrapper.html(custom_css + timeline_html);
}