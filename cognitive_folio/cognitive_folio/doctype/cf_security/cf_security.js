frappe.ui.form.on('CF Security', {
    validate: function(frm) {
        // If security type is Cash, set symbol equal to security_name
        if(frm.doc.security_type === "Cash") {
            frm.set_value('symbol', frm.doc.security_name);
        }
    },
    refresh: function(frm) {
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
                if (!frm.doc.ticker_info) {
                    frappe.msgprint({
                        title: __('Missing Data'),
                        indicator: 'yellow',
                        message: __('Please fetch ticker info first to generate AI suggestions')
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

    // Add an event handler for security_name field
    security_name: function(frm) {
        // Only search if security_name has at least 3 characters
        if(frm.doc.security_name && frm.doc.security_name.length >= 3) {
            // Don't search if we already have a symbol
            if(frm.doc.stock_exchange) return;
            
            // Debounce the search to avoid too many API calls
            if(frm.security_name_timeout) clearTimeout(frm.security_name_timeout);
            
            frm.security_name_timeout = setTimeout(() => {
                search_stocks(frm, frm.doc.security_name);
            }, 800); // Wait 800ms after user stops typing
        }
    },
    
    // Add an event handler for isin field
    isin: function(frm) {
        // Only search if isin has at least 3 characters
        if(frm.doc.isin && frm.doc.isin.length >= 3) {
            // Don't search if we already have a symbol
            if(frm.doc.stock_exchange) return;
            
            // Debounce the search to avoid too many API calls
            if(frm.isin_timeout) clearTimeout(frm.isin_timeout);
            
            frm.isin_timeout = setTimeout(() => {
                search_stocks(frm, frm.doc.isin);
            }, 800); // Wait 800ms after user stops typing
        }
    },
    
    // Add event handler for security_type field
    security_type: function(frm) {
        // If security type is changed to Cash, update symbol
        if(frm.doc.security_type === "Cash" && frm.doc.security_name) {
            frm.set_value('symbol', frm.doc.security_name);
        }
    }
});

// Function to search for stocks based on search term
function search_stocks(frm, search_term) {

    if (frm.doc.security_type == 'Cash') {
        return;
    }

    // Show loading indicator
    frappe.dom.freeze(__('Searching for securities...'));
    
    frappe.call({
        method: 'cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.search_stock_symbols',
        args: {
            search_term: search_term
        },
        callback: function(r) {
            // Hide loading indicator
            frappe.dom.unfreeze();
            
            if (r.message.error) {
                frappe.msgprint({
                    title: __('Search Error'),
                    indicator: 'red',
                    message: r.message.error
                });
                return;
            }
            
            if (!r.message.results || r.message.results.length === 0) {
                frappe.msgprint({
                    title: __('No Results'),
                    indicator: 'yellow',
                    message: __(`No securities found matching "${search_term}"`)
                });
                return;
            }
            
            // Show results in a dialog
            let result_dialog = new frappe.ui.Dialog({
                title: __('Stock Matches Found'),
                fields: [
                    {
                        fieldname: 'search_message',
                        fieldtype: 'HTML',
                        options: `<div class="alert alert-info">
                            We found ${r.message.results.length} potential matches for <strong>${search_term}</strong>.
                            Select one to populate your security details.
                        </div>`
                    },
                    {
                        fieldname: 'results_html',
                        fieldtype: 'HTML'
                    }
                ]
            });
            
            let results_html = '<div class="stock-search-results">';
            results_html += '<table class="table table-bordered"><thead><tr>';
            results_html += '<th>Symbol</th><th>Name</th><th>Exchange</th><th>Sector</th><th>Industry</th><th>Action</th>';
            results_html += '</tr></thead><tbody>';
            
            r.message.results.forEach(stock => {
                results_html += `<tr>
                    <td>${stock.symbol || ''}</td>
                    <td>${stock.name || ''}</td>
                    <td>${stock.exchange || ''}</td>
                    <td>${stock.sector || ''}</td>
                    <td>${stock.industry || ''}</td>
                    <td><button class="btn btn-xs btn-primary select-stock" 
                        data-symbol="${stock.symbol || ''}" 
                        data-name="${stock.name || ''}"
                        data-exchange="${stock.exchange || ''}"
                        data-sector="${stock.sector || ''}"
                        data-industry="${stock.industry || ''}">Select</button></td>
                </tr>`;
            });
            
            results_html += '</tbody></table></div>';
            
            result_dialog.fields_dict.results_html.$wrapper.html(results_html);
            
            // Handle stock selection
            result_dialog.$wrapper.on('click', '.select-stock', function() {
                // Show loading indicator while fetching data
                frappe.dom.freeze(__('Fetching security data...'));
                
                let symbol = $(this).attr('data-symbol');
                let company = $(this).attr('data-name');
                let exchange = $(this).attr('data-exchange');
                let sector = $(this).attr('data-sector');
                let industry = $(this).attr('data-industry');
                
                // Set all available fields immediately
                frm.set_value('symbol', symbol);
                if (company) frm.set_value('security_name', company);
                if (exchange) frm.set_value('stock_exchange', exchange);
                if (sector) frm.set_value('sector', sector);
                if (industry) frm.set_value('industry', industry);
                
                result_dialog.hide();
                frappe.dom.unfreeze();
                
            });
            
            result_dialog.show();
        }
    });
}

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