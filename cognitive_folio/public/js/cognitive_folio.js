// Initialize chat realtime listener when document is ready
$(document).ready(function() {
    // Wait for frappe to be available
    function initializeChatListener() {
        if (typeof frappe !== 'undefined' && frappe.realtime) {
            // Track if listener is already initialized to prevent duplicates
            if (!frappe._cf_chat_listener_initialized) {
                
                frappe.realtime.on('cf_job_completed', function(data) {
                    // Only process if we're currently on a CF Chat form that matches the chat_id
                    if (cur_frm && 
                        cur_frm.doctype === 'CF Chat' && 
                        cur_frm.doc.name === data.chat_id) {
                        
                        // Refresh the timeline
                        if (typeof render_chat_timeline === 'function') {
                            render_chat_timeline(cur_frm);
                        }
                        
                    }

                    // Refresh frame to ensure latest data
                    cur_frm.reload_doc();
                    
                    // Play notification sound
                    const audio = new Audio('/assets/cognitive_folio/sounds/notification.mp3');
                    audio.volume = 0.5;
                    audio.play().catch(e => console.log('Audio play failed:', e));
                    
                    // Show notification based on status
                    if (data.status === 'success') {
                        frappe.show_alert({
                            message: __(data.message || "Chat message processed successfully."),
                            indicator: "green"
                        });
                    } else if (data.status === 'error') {
                        frappe.show_alert({
                            message: __(data.message || "An error occurred while processing the chat message."),
                            indicator: "red"
                        });
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