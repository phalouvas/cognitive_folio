// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Portfolio Holding", {
	refresh(frm) {
        if (!frm.is_new()) {
            // Process news data and render it in the news_html field
            if(frm.doc.news) {
                try {
                    const newsData = JSON.parse(frm.doc.news);
                    const newsHtml = formatNewsData(newsData);
                    frm.set_df_property('news_html', 'options', newsHtml);
                } catch (error) {
                    console.error("Error parsing news data:", error);
                    frm.set_df_property('news_html', 'options', 
                        '<div class="text-muted">Error displaying news data.</div>');
                }
            } else {
                frm.set_df_property('news_html', 'options', 
                    '<div class="text-muted">No news available for this security.</div>');
            }

            if(frm.doc.ai_suggestion) {
                let md_html = frappe.markdown(frm.doc.ai_suggestion);
                frm.set_df_property('ai_suggestion_html', 'options', 
                    `<div class="markdown-preview">${md_html}</div>`);
            } else {
                frm.set_df_property('ai_suggestion_html', 'options',
                    `<div class="markdown-preview">No AI suggestion available.</div>`);
            }

            frm.add_custom_button(__('Fetch Latest Data'), function() {
                frappe.dom.freeze(__('Fetching latest data...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'fetch_data',
                    args: {
                        with_fundamentals: false
                    },
                    callback: function(r) {
                        // Unfreeze the GUI when operation completes
                        frappe.dom.unfreeze();
                        
                        frappe.show_alert({
                            message: __('Security data refreshed'),
                            indicator: 'green'
                        });
                        frm.reload_doc();
                    },
                    error: function(r) {
                        // Make sure to unfreeze even if there's an error
                        frappe.dom.unfreeze();
                    }
                });
            }, __('Actions'));

            frm.add_custom_button(__('Fetch Fundamentals'), function() {
                frappe.dom.freeze(__('Fetching security data...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'fetch_data',
                    args: {
                        with_fundamentals: true
                    },
                    callback: function(r) {
                        // Unfreeze the GUI when operation completes
                        frappe.dom.unfreeze();
                        
                        frappe.show_alert({
                            message: __('Security data refreshed'),
                            indicator: 'green'
                        });
                        frm.reload_doc();
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
                            frm.reload_doc();
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

/**
 * Format news data into HTML for display
 * @param {Array} newsData - Array of news items
 * @returns {string} - Formatted HTML string
 */
function formatNewsData(newsData) {
    if (!newsData || !newsData.length) {
        return '<div class="text-muted">No news available for this security.</div>';
    }
    
    let htmlContent = ['<div class="cf-news-container">'];
    
    for (const item of newsData) {
        if (!item.content) continue;
        
        const content = item.content;
        const canonicalUrl = content.canonicalUrl && content.canonicalUrl.url;
        const title = content.title || 'No title';
        const summary = content.summary || 'No summary available';
        const pubDate = content.pubDate || '';
        
        if (!canonicalUrl) continue;
        
        // Format the publication date if it exists
        let formattedDate = '';
        if (pubDate) {
            try {
                const date = new Date(pubDate);
                formattedDate = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
            } catch (e) {
                formattedDate = pubDate; // Use the original string if parsing fails
            }
        }
        
        // Format each news item as a card with publication date
        htmlContent.push(`
            <div class="cf-news-item">
                <p class="text-muted"><small><a href="${canonicalUrl}" target="_blank" rel="noopener noreferrer">${canonicalUrl}</a></small></p>
                <h5>${title}</h5>
                <p>${summary}</p>
                <p class="text-muted"><small>${formattedDate}</small></p>
                <hr>
            </div>
        `);
    }
    
    htmlContent.push('</div>');
    
    return htmlContent.join('');
}
