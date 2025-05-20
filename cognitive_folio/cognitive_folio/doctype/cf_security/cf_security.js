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

            // Format and display ticker info if available
            if(frm.doc.ticker_info) {
                try {
                    formatTickerInfo(frm);
                } catch (error) {
                    console.error("Error formatting ticker info:", error);
                    frm.set_df_property('ticker_info_html', 'options', 
                        '<div class="text-muted">Error displaying ticker information.</div>');
                }
            } else {
                frm.set_df_property('ticker_info_html', 'options', 
                    '<div class="text-muted">No ticker information available.</div>');
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

/**
 * Format ticker_info into a human-readable structured display
 * @param {Object} frm - The form object
 */
function formatTickerInfo(frm) {
    try {
        const data = JSON.parse(frm.doc.ticker_info);
        
        // Create container with styling
        let html = `
            <style>
                .ticker-info-container { font-family: var(--font-stack); }
                .ticker-info-container h3 { margin-top: 20px; margin-bottom: 10px; color: #1a1a1a; }
                .ticker-info-container .info-card { 
                    background: #f8f8f8; border-radius: 5px; padding: 15px; 
                    margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                .ticker-info-container .info-grid {
                    display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                    grid-gap: 15px; margin-bottom: 15px;
                }
                .ticker-info-container .metric-item {
                    padding: 10px; border-radius: 4px; background: #fff;
                    border-left: 4px solid #4d99e7;
                }
                .ticker-info-container .metric-label {
                    font-size: 0.85rem; color: #6c7680; margin-bottom: 5px;
                }
                .ticker-info-container .metric-value {
                    font-size: 1.1rem; font-weight: 500; color: #1a1a1a;
                }
                .ticker-info-container .positive { color: #28a745; }
                .ticker-info-container .negative { color: #dc3545; }
                .ticker-info-container .table-condensed { margin-bottom: 0; }
                .ticker-info-container .table-condensed td, 
                .ticker-info-container .table-condensed th { padding: 5px 8px; }
                .ticker-info-container .company-summary {
                    line-height: 1.5; margin-bottom: 15px; 
                    max-height: 150px; overflow-y: auto;
                }
            </style>
            <div class="ticker-info-container">
        `;
        
        // Company overview section
        html += `<h3>Company Overview</h3>`;
        html += `<div class="info-card">`;
        
        // Company summary if available
        if (data.longBusinessSummary) {
            html += `
                <div class="company-summary">
                    ${data.longBusinessSummary}
                </div>
            `;
        }
        
        // Basic company info
        html += `<div class="info-grid">`;
        
        // Add company details grid items
        const companyDetails = [
            {label: "Sector", value: data.sector},
            {label: "Industry", value: data.industryDisp || data.industry},
            {label: "Country", value: data.country},
            {label: "Exchange", value: data.fullExchangeName},
            {label: "Employees", value: data.fullTimeEmployees ? formatNumber(data.fullTimeEmployees) : null},
            {label: "Website", value: data.website ? `<a href="${data.website}" target="_blank">${data.website}</a>` : null}
        ];
        
        companyDetails.forEach(item => {
            if (item.value) {
                html += `
                    <div class="metric-item">
                        <div class="metric-label">${item.label}</div>
                        <div class="metric-value">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div></div>`;
        
        // Market data section
        html += `<h3>Market Data</h3>`;
        html += `<div class="info-grid">`;
        
        // Add market metrics grid items
        const marketMetrics = [
            {label: "Current Price", value: formatCurrency(data.currentPrice, data.currency)},
            {label: "Market Cap", value: formatLargeNumber(data.marketCap, data.currency)},
            {label: "52-Week Range", value: data.fiftyTwoWeekLow && data.fiftyTwoWeekHigh ? 
                `${formatCurrency(data.fiftyTwoWeekLow, data.currency)} - ${formatCurrency(data.fiftyTwoWeekHigh, data.currency)}` : null},
            {label: "52-Week Change", value: formatPercentWithColor(data["52WeekChange"])},
            {label: "Day Range", value: data.dayLow && data.dayHigh ? 
                `${formatCurrency(data.dayLow, data.currency)} - ${formatCurrency(data.dayHigh, data.currency)}` : null},
            {label: "Average Volume", value: data.averageVolume ? formatNumber(data.averageVolume) : null}
        ];
        
        marketMetrics.forEach(item => {
            if (item.value) {
                html += `
                    <div class="metric-item">
                        <div class="metric-label">${item.label}</div>
                        <div class="metric-value">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Financial metrics section
        html += `<h3>Financial Metrics</h3>`;
        html += `<div class="info-grid">`;
        
        // Add financial metrics grid items
        const financialMetrics = [
            {label: "P/E Ratio", value: data.trailingPE ? data.trailingPE.toFixed(2) : null},
            {label: "Forward P/E", value: data.forwardPE ? data.forwardPE.toFixed(2) : null},
            {label: "EPS (TTM)", value: data.trailingEps ? formatCurrency(data.trailingEps, data.currency) : null},
            {label: "Dividend Yield", value: formatPercentWithColor(data.dividendYield/100)},
            {label: "Profit Margins", value: formatPercentWithColor(data.profitMargins)},
            {label: "Operating Margins", value: formatPercentWithColor(data.operatingMargins)},
            {label: "Return on Equity", value: formatPercentWithColor(data.returnOnEquity)},
            {label: "Revenue Growth", value: formatPercentWithColor(data.revenueGrowth)},
            {label: "Earnings Growth", value: formatPercentWithColor(data.earningsGrowth)},
            {label: "Book Value", value: data.bookValue ? formatCurrency(data.bookValue, data.currency) : null},
            {label: "Price to Book", value: data.priceToBook ? data.priceToBook.toFixed(2) : null},
            {label: "Beta", value: data.beta ? data.beta.toFixed(2) : null}
        ];
        
        financialMetrics.forEach(item => {
            if (item.value) {
                html += `
                    <div class="metric-item">
                        <div class="metric-label">${item.label}</div>
                        <div class="metric-value">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Financials and Analysis section
        html += `<h3>Financials and Analysis</h3>`;
        
        // Analyst Recommendations subsection
        if (data.averageAnalystRating || data.recommendationKey || data.targetMeanPrice) {
            html += `<h4 style="margin-top: 15px; margin-bottom: 10px; font-size: 1rem;">Analyst Recommendations</h4>`;
            html += `<div class="info-grid">`;
            
            // Analyst ratings and price targets
            const analysisMetrics = [
                {label: "Analyst Rating", value: data.averageAnalystRating},
                {label: "Recommendation", value: data.recommendationKey ? 
                    data.recommendationKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : null},
                {label: "Target Price (Mean)", value: data.targetMeanPrice ? 
                    formatCurrency(data.targetMeanPrice, data.currency) : null},
                {label: "Target Price Range", value: data.targetLowPrice && data.targetHighPrice ? 
                    `${formatCurrency(data.targetLowPrice, data.currency)} - ${formatCurrency(data.targetHighPrice, data.currency)}` : null},
                {label: "Potential Return", value: data.targetMeanPrice && data.currentPrice ? 
                    formatPercentWithColor((data.targetMeanPrice / data.currentPrice) - 1) : null}
            ];
            
            analysisMetrics.forEach(item => {
                if (item.value) {
                    html += `
                        <div class="metric-item">
                            <div class="metric-label">${item.label}</div>
                            <div class="metric-value">${item.value}</div>
                        </div>
                    `;
                }
            });
            
            html += `</div>`;
        }
        
        // Financial Highlights subsection
        html += `<h4 style="margin-top: 15px; margin-bottom: 10px; font-size: 1rem;">Financial Highlights</h4>`;
        html += `<div class="info-grid">`;
        
        // Add balance sheet and cash flow metrics
        const financialHighlights = [
            {label: "Total Revenue", value: data.totalRevenue ? 
                formatLargeNumber(data.totalRevenue, data.financialCurrency) : null},
            {label: "EBITDA", value: data.ebitda ? 
                formatLargeNumber(data.ebitda, data.financialCurrency) : null},
            {label: "EBITDA Margin", value: formatPercentWithColor(data.ebitdaMargins)},
            {label: "Total Cash", value: data.totalCash ? 
                formatLargeNumber(data.totalCash, data.financialCurrency) : null},
            {label: "Total Debt", value: data.totalDebt ? 
                formatLargeNumber(data.totalDebt, data.financialCurrency) : null},
            {label: "Debt to Equity", value: data.debtToEquity ? (data.debtToEquity / 100).toFixed(2) : null},
            {label: "Operating Cash Flow", value: data.operatingCashflow ? 
                formatLargeNumber(data.operatingCashflow, data.financialCurrency) : null},
            {label: "Free Cash Flow", value: data.freeCashflow ? 
                formatLargeNumber(data.freeCashflow, data.financialCurrency) : null}
        ];
        
        financialHighlights.forEach(item => {
            if (item.value) {
                html += `
                    <div class="metric-item">
                        <div class="metric-label">${item.label}</div>
                        <div class="metric-value">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Financial Health Ratios subsection
        html += `<h4 style="margin-top: 15px; margin-bottom: 10px; font-size: 1rem;">Financial Health Ratios</h4>`;
        html += `<div class="info-grid">`;
        
        // Add health ratios
        const healthRatios = [
            {label: "Current Ratio", value: data.currentRatio ? data.currentRatio.toFixed(2) : null},
            {label: "Quick Ratio", value: data.quickRatio ? data.quickRatio.toFixed(2) : null},
            {label: "Return on Assets", value: formatPercentWithColor(data.returnOnAssets)},
            {label: "Enterprise Value", value: data.enterpriseValue ? 
                formatLargeNumber(data.enterpriseValue, data.financialCurrency) : null},
            {label: "EV/Revenue", value: data.enterpriseToRevenue ? data.enterpriseToRevenue.toFixed(2) : null},
            {label: "EV/EBITDA", value: data.enterpriseToEbitda ? data.enterpriseToEbitda.toFixed(2) : null},
            {label: "Payout Ratio", value: data.payoutRatio ? formatPercentWithColor(data.payoutRatio) : null},
            {label: "PEG Ratio", value: data.trailingPegRatio ? data.trailingPegRatio.toFixed(2) : null}
        ];
        
        healthRatios.forEach(item => {
            if (item.value) {
                html += `
                    <div class="metric-item">
                        <div class="metric-label">${item.label}</div>
                        <div class="metric-value">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Key executive team (if data available)
        if (data.companyOfficers && data.companyOfficers.length > 0) {
            html += `<h3>Key Executives</h3>`;
            html += `<div class="info-card">`;
            html += `<div class="table-responsive">`;
            html += `<table class="table table-bordered table-condensed">`;
            html += `<thead><tr>
                <th>Name</th>
                <th>Title</th>
                <th>Age</th>
            </tr></thead><tbody>`;
            
            // Show up to 5 key executives
            const executives = data.companyOfficers.slice(0, 5);
            executives.forEach(exec => {
                html += `<tr>
                    <td>${exec.name || '-'}</td>
                    <td>${exec.title || '-'}</td>
                    <td>${exec.age || '-'}</td>
                </tr>`;
            });
            
            html += `</tbody></table></div></div>`;
        }
        
        html += `</div>`;
        
        // Set the HTML content
        frm.set_df_property('ticker_info_html', 'options', html);
        
    } catch (error) {
        console.error("Error formatting ticker info:", error);
        frm.set_df_property('ticker_info_html', 'options', 
            `<div class="text-danger">Error displaying ticker information: ${error.message}</div>`);
    }
}

/**
 * Format a number with commas for thousands
 * @param {number} num - The number to format
 * @returns {string} - The formatted number
 */
function formatNumber(num) {
    if (num === null || num === undefined) return null;
    return new Intl.NumberFormat().format(num);
}

/**
 * Format a currency value
 * @param {number} value - The value to format
 * @param {string} currency - The currency code
 * @returns {string} - The formatted currency value
 */
function formatCurrency(value, currency) {
    if (value === null || value === undefined) return null;
    
    // Use default currency if not provided
    const currencyCode = currency || 'USD';
    
    // Round to 2 decimal places if not a whole number
    const formatOptions = {
        style: 'currency',
        currency: currencyCode,
        minimumFractionDigits: Math.round(value) === value ? 0 : 2,
        maximumFractionDigits: 2
    };
    
    return new Intl.NumberFormat(undefined, formatOptions).format(value);
}

/**
 * Format a large number (like market cap) with abbreviations
 * @param {number} num - The number to format
 * @param {string} currency - The currency code
 * @returns {string} - The formatted large number
 */
function formatLargeNumber(num, currency) {
    if (num === null || num === undefined) return null;
    
    const currencySymbol = currency === 'USD' ? '$' : 
                         currency === 'EUR' ? '€' : 
                         currency === 'GBP' ? '£' : 
                         currency === 'JPY' ? '¥' : 
                         currency === 'HKD' ? 'HK$' : 
                         currency ? currency + ' ' : '';
    
    if (num >= 1e12) {
        return currencySymbol + (num / 1e12).toFixed(2) + 'T';
    } else if (num >= 1e9) {
        return currencySymbol + (num / 1e9).toFixed(2) + 'B';
    } else if (num >= 1e6) {
        return currencySymbol + (num / 1e6).toFixed(2) + 'M';
    } else if (num >= 1e3) {
        return currencySymbol + (num / 1e3).toFixed(2) + 'K';
    } else {
        return currencySymbol + num;
    }
}

/**
 * Format a percentage value with color coding
 * @param {number} value - The value to format as a percentage
 * @returns {string} - HTML with the formatted percentage
 */
function formatPercentWithColor(value) {
    if (value === null || value === undefined) return null;
    
    const percent = (value * 100).toFixed(2) + '%';
    if (value > 0) {
        return `<span class="positive">+${percent}</span>`;
    } else if (value < 0) {
        return `<span class="negative">${percent}</span>`;
    } else {
        return percent;
    }
}