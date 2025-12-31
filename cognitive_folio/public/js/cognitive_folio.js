// Initialize chat realtime listener when document is ready
$(document).ready(function() {
    // Debounce timer to limit reload frequency during streaming
    let streamingReloadTimer = null;

    // Wait for frappe to be available
    function initializeChatListener() {
        if (typeof frappe !== 'undefined' && frappe.realtime) {
            // Track if listener is already initialized to prevent duplicates
            if (!frappe._cf_chat_listener_initialized) {

                // Existing job completion listener
                frappe.realtime.on('cf_job_completed', function(data) {
                    // Clear any pending streaming reload and refresh once on completion
                    if (streamingReloadTimer) {
                        clearTimeout(streamingReloadTimer);
                        streamingReloadTimer = null;
                    }

                    if (cur_frm) {
                        cur_frm.reload_doc();
                    }
                    
                    // Show notification based on status
                    if (data.status === 'success') {
                        // Play notification sound
                        const audio = new Audio('/assets/cognitive_folio/sounds/notification.mp3');
                        audio.volume = 0.5;
                        audio.play().catch(e => console.log('Audio play failed:', e));
                        frappe.show_alert({
                            message: __(data.message || "Chat message processed successfully."),
                            indicator: "green"
                        });
                    } else if (data.status === 'error') {
                        // Play notification sound
                        const audio = new Audio('/assets/cognitive_folio/sounds/error.mp3');
                        audio.volume = 0.5;
                        audio.play().catch(e => console.log('Audio play failed:', e));
                        frappe.show_alert({
                            message: __(data.message || "An error occurred while processing the chat message."),
                            indicator: "red"
                        });
                    }
                });
                
                // Streaming update listener with 500ms debounce and visibility guard
                frappe.realtime.on('cf_streaming_update', function(data) {
                    // Only reload if we're currently viewing the relevant chat message or chat
                    if (!(cur_frm && (
                        (cur_frm.doctype === 'CF Chat Message' && cur_frm.doc.name === data.message_id) ||
                        (cur_frm.doctype === 'CF Chat' && cur_frm.doc.name === data.chat_id)
                    ))) {
                        return;
                    }

                    // Avoid spamming reloads while tab is hidden
                    if (document.hidden) {
                        return;
                    }

                    // Debounce reload to at most once per 1000ms
                    if (!streamingReloadTimer) {
                        streamingReloadTimer = setTimeout(() => {
                            streamingReloadTimer = null;
                            if (cur_frm) {
                                cur_frm.reload_doc();
                            }
                        }, 1000);
                    }
                });
                
                // Mark as initialized
                frappe._cf_chat_listener_initialized = true;
            }
        } else {
            // Retry after a short delay if frappe is not ready
            setTimeout(initializeChatListener, 100);
        }
    }
    
    initializeChatListener();
});