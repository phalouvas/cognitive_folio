frappe.ui.form.on('CF Security', {
    validate: function(frm) {
        // If security type is Cash, set symbol equal to security_name
        if ((frm.doc.security_type !== "Stock") && !frm.doc.symbol) {
            frm.set_value('symbol', frm.doc.security_name);
        }
    },
    refresh: function(frm) {
        // Set current_price field read_only based on security_type
        if(frm.doc.security_type === "Treasury Rate") {
            frm.set_df_property('current_price', 'read_only', 0);
            frm.set_df_property('country', 'read_only', 0);
        }
        
        if (!frm.is_new() && frm.doc.security_type == "Stock") {
            // Process news data and render it in the news_html field
            if(frm.doc.news) {
                try {
                    const newsData = JSON.parse(frm.doc.news);
                    const htmlResultArray = formatNewsData(newsData);
                    frm.set_df_property('news_html', 'options', htmlResultArray);
                } catch (error) {
                    console.error("Error parsing news data:", error);
                    frm.set_df_property('news_html', 'options', 
                        '<div class="text-muted">Error displaying news data.</div>');
                }
            } else {
                frm.set_df_property('news_html', 'options', 
                    '<div class="text-muted">No news available for this security.</div>');
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

            // Format and display balance sheet data if available
            if(frm.doc.balance_sheet) {
                try {
                    frm.set_df_property('profit_loss_html', 'options', formatJsonForDisplay(frm.doc.profit_loss, "Yearly",  frm.doc.currency ));
                    frm.set_df_property('quarterly_profit_loss_html', 'options', formatJsonForDisplay(frm.doc.quarterly_profit_loss, "Quarterly",  frm.doc.currency ));
                    frm.set_df_property('ttm_profit_loss_html', 'options', formatJsonForDisplay(frm.doc.ttm_profit_loss, "TTM",  frm.doc.currency ));
                    
                    frm.set_df_property('balance_sheet_html', 'options', formatJsonForDisplay(frm.doc.balance_sheet, "Yearly",  frm.doc.currency ));
                    frm.set_df_property('quarterly_balance_sheet_html', 'options', formatJsonForDisplay(frm.doc.quarterly_balance_sheet, "Quarterly",  frm.doc.currency ));

                    frm.set_df_property('cash_flow_html', 'options', formatJsonForDisplay(frm.doc.cash_flow, "Yearly",  frm.doc.currency ));
                    frm.set_df_property('quarterly_cash_flow_html', 'options', formatJsonForDisplay(frm.doc.quarterly_cash_flow, "Quarterly",  frm.doc.currency ));
                    frm.set_df_property('ttm_cash_flow_html', 'options', formatJsonForDisplay(frm.doc.ttm_cash_flow, "TTM",  frm.doc.currency ));
                } catch (error) {
                    console.error("Error parsing financial data:", error);
                }
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
                
                frm.add_custom_button(__('Fetch CIK'), function() {
                    frappe.dom.freeze(__('Fetching CIK...'));
                    frm.call({
                        doc: frm.doc,
                        method: 'fetch_cik',
                        callback: function(r) {
                            frappe.dom.unfreeze();
                            if (r.message && r.message.success) {
                                frappe.show_alert({
                                    message: __('CIK set to {0}', [r.message.cik || '']),
                                    indicator: 'green'
                                });
                                frm.reload_doc();
                            } else {
                                frappe.msgprint({
                                    title: __('CIK Lookup'),
                                    indicator: 'orange',
                                    message: (r.message && r.message.message) || __('CIK not found')
                                });
                            }
                        },
                        error: function() {
                            frappe.dom.unfreeze();
                            frappe.msgprint({
                                title: __('CIK Lookup Error'),
                                indicator: 'red',
                                message: __('Unable to fetch CIK. Please try again later.')
                            });
                        }
                    });
                }, __('Actions'));

            frm.add_custom_button(__('Fetch Fundamentals'), function() {
                frappe.dom.freeze(__('Fetching fundamentals and latest data...'));
                
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
            
            // Add button for viewing financial data coverage
            frm.add_custom_button(__('View Data Coverage'), function() {
                frappe.dom.freeze(__('Analyzing available financial data...'));
                
                frm.call({
                    doc: frm.doc,
                    method: 'get_financial_data_coverage',
                    callback: function(r) {
                        frappe.dom.unfreeze();
                        
                        if (r.message && r.message.success) {
                            // Display the formatted data coverage in a dialog
                            formatDataCoverageDialog(r.message.data, frm.doc.security_name);
                        } else {
                            frappe.msgprint({
                                title: __('Data Coverage'),
                                indicator: 'red',
                                message: r.message && r.message.error ? 
                                    r.message.error : __('Failed to retrieve data coverage information')
                            });
                        }
                    },
                    error: function() {
                        frappe.dom.unfreeze();
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('An error occurred while retrieving data coverage')
                        });
                    }
                });
            }, __('Actions'));
            
            // Add copy buttons for multiple fields
            const fieldsWithCopyButtons = [
                'balance_sheet', 'quarterly_balance_sheet',
                'ticker_info', 
                'profit_loss', 'ttm_profit_loss', 'quarterly_profit_loss',
                'cash_flow', 'ttm_cash_flow', 'quarterly_cash_flow',
                'ai_prompt', 'news_urls', 'dividends'];
            fieldsWithCopyButtons.forEach(fieldName => {
                addCopyButtonToField(frm, fieldName);
            });

            // Add "Ask AI" button — opens ph_agent chat with security context
            frm.page.add_inner_button(__('Ask AI'), function() {
                // First find the Financial Advisor persona and its default LLM provider
                frappe.db.get_value('Persona', {persona_name: 'Financial Advisor'}, ['name', 'default_llm_provider'])
                    .then(pr => {
                        let persona = pr.message && pr.message.name;
                        let llm_provider = pr.message && pr.message.default_llm_provider;
                        if (!persona) {
                            frappe.msgprint(__('Financial Advisor persona not found. Please ensure ph_agent is installed.'));
                            return;
                        }
                        // If persona has no default provider, find the first enabled one
                        if (!llm_provider) {
                            frappe.db.get_value('LLM Provider', {is_enabled: 1}, 'name')
                                .then(lr => {
                                    llm_provider = lr.message && lr.message.name;
                                    _create_or_reopen_chat_session(frm, 'CF Security', persona, llm_provider);
                                });
                        } else {
                            _create_or_reopen_chat_session(frm, 'CF Security', persona, llm_provider);
                        }
                    });
            });

            // Render chat sessions section
            _render_chat_sessions_section(frm, 'CF Security', frm.doc.name);
            
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
        
        // Make current_price editable for Treasury Rate securities
        if(frm.doc.security_type === "Treasury Rate") {
            frm.set_df_property('current_price', 'read_only', 0);
            frappe.show_alert({
                message: __('Current price is now editable for Treasury Rate securities'),
                indicator: 'blue'
            });
        } else {
            frm.set_df_property('current_price', 'read_only', 1);
        }
    },

    template_prompt(frm) {
        // When template_prompt field is changed, fetch the content from CF Prompt
        if (frm.doc.template_prompt) {
            frappe.db.get_value('CF Prompt', frm.doc.template_prompt, 'content')
                .then(r => {
                    if (r.message && r.message.content) {
                        frm.set_value('ai_prompt', r.message.content);
                    }
                });
        } else {
            // Clear prompt if template_prompt is cleared
            frm.set_value('ai_prompt', '');
        }
    }
});

// Function to search for stocks based on search term
function search_stocks(frm, search_term) {

    if (frm.doc.security_type != 'Stock') {
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
    
    let urls = [];
    let htmlContent = ['<div class="cf-news-container">'];
    
    for (const item of newsData) {
        if (!item.content) continue;
        
        const content = item.content;
        const canonicalUrl = content.canonicalUrl && content.canonicalUrl.url;
        const title = content.title?.replace(/['"]/g, "") || "No title";
        const summary = content.summary?.replace(/['"]/g, "") || "No summary available";
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
        urls.push("#" + canonicalUrl);
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
        
        // Create container with Frappe styling
        let html = `
            <div class="ticker-info-container">
        `;
        
        // Company overview section
        html += `<h3>Company Overview</h3>`;
        
        // Add Yahoo Finance link
        html += `
            <div class="mb-3">
                <a href="https://finance.yahoo.com/quote/${frm.doc.symbol}/" 
                   target="_blank" 
                   rel="noopener noreferrer"
                   class="btn btn-sm btn-default text-decoration-none">
                    <svg class="mr-1" style="width: 16px; height: 16px; vertical-align: middle;" viewBox="0 0 24 24">
                        <path fill="currentColor" d="M14,3V5H17.59L7.76,14.83L9.17,16.24L19,6.41V10H21V3M19,19H5V5H12V3H5C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V12H19V19Z" />
                    </svg>
                    View on Yahoo Finance
                </a>
            </div>
        `;
        
        html += `<div class="card card-body mb-3">`;
        
        // Company summary if available
        if (data.longBusinessSummary) {
            html += `
                <div class="mb-3 overflow-auto" style="max-height: 150px;">
                    ${data.longBusinessSummary}
                </div>
            `;
        }
        
        // Basic company info - use Frappe grid system
        html += `<div class="row">`;
        
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
                    <div class="col-sm-6 col-md-4 mb-3">
                        <div class="small text-muted">${item.label}</div>
                        <div class="font-weight-medium">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div></div>`;
        
        // Market data section
        html += `<h3>Market Data</h3>`;
        html += `<div class="row">`;
        
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
                    <div class="col-sm-6 col-md-4 mb-3">
                        <div class="small text-muted">${item.label}</div>
                        <div class="font-weight-medium">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Annual Performance section
        html += `<h3>Annual Performance</h3>`;
        html += `<div class="row">`;
        
        // Calculate distance from 52-week high and low
        let distanceFromHigh = null;
        let distanceFromLow = null;
        if (data.fiftyTwoWeekHigh && data.currentPrice) {
            distanceFromHigh = formatPercentWithColor((data.currentPrice / data.fiftyTwoWeekHigh) - 1);
        }
        if (data.fiftyTwoWeekLow && data.currentPrice) {
            distanceFromLow = formatPercentWithColor((data.currentPrice / data.fiftyTwoWeekLow) - 1);
        }
        
        // Calculate 52-week total return (price change + dividend yield)
        // Fallback to trailingAnnualDividendYield if dividendYield is missing
        const dividendYield = data.dividendYield !== null && data.dividendYield !== undefined ? data.dividendYield : data.trailingAnnualDividendYield;
        let totalReturn = null;
        if (data["52WeekChange"] !== null && dividendYield !== null && dividendYield !== undefined) {
            const totalReturnValue = data["52WeekChange"] + (dividendYield / 100);
            totalReturn = formatPercentWithColor(totalReturnValue);
        }
        
        // Calculate outperformance vs S&P 500
        let outperformance = null;
        if (data["52WeekChange"] !== null && data.SandP52WeekChange) {
            const outperformanceValue = data["52WeekChange"] - data.SandP52WeekChange;
            outperformance = formatPercentWithColor(outperformanceValue);
        }
        
        // Add annual performance metrics (52-Week Total Return moved to end with arrow indicator)
        const annualPerformanceMetrics = [
            {label: "52-Week Price Change", value: formatPercentWithColor(data["52WeekChange"])},
            {label: "52-Week High", value: data.fiftyTwoWeekHigh ? formatCurrency(data.fiftyTwoWeekHigh, data.currency) : null},
            {label: "52-Week Low", value: data.fiftyTwoWeekLow ? formatCurrency(data.fiftyTwoWeekLow, data.currency) : null},
            {label: "Distance from 52W High", value: distanceFromHigh},
            {label: "Distance from 52W Low", value: distanceFromLow},
            {label: "Annual Dividend Rate", value: data.dividendRate ? formatCurrency(data.dividendRate, data.currency) : null},
            {label: "Dividend Yield", value: dividendYield ? (dividendYield).toFixed(2) + '%' : null},
            {label: "S&P 500 52-Week Change", value: formatPercentWithColor(data.SandP52WeekChange)},
            {label: "Outperformance vs S&P 500", value: outperformance},
            {
                label: "52-Week Total Return",
                value: totalReturn ? totalReturn + getPerformanceArrows(data["52WeekChange"] + (dividendYield ? dividendYield / 100 : 0)) : null
            }
        ];
        
        annualPerformanceMetrics.forEach(item => {
            if (item.value) {
                html += `
                    <div class="col-sm-6 col-md-4 mb-3">
                        <div class="small text-muted">${item.label}</div>
                        <div class="font-weight-medium">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Financial metrics section
        html += `<h3>Financial Metrics</h3>`;
        html += `<div class="row">`;
        
        // Add financial metrics grid items
        const financialMetrics = [
            {label: "P/E Ratio", value: data.trailingPE ? data.trailingPE.toFixed(2) : null},
            {label: "Forward P/E", value: data.forwardPE ? data.forwardPE.toFixed(2) : null},
            {label: "EPS (TTM)", value: data.trailingEps ? formatCurrency(data.trailingEps, data.currency) : null},
            {label: "Dividend Yield", value: dividendYield ? formatPercentWithColor(dividendYield/100) : null},
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
                    <div class="col-sm-6 col-md-4 mb-3">
                        <div class="small text-muted">${item.label}</div>
                        <div class="font-weight-medium">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Financials and Analysis section
        html += `<h3>Financials and Analysis</h3>`;
        
        // Analyst Recommendations subsection
        if (data.averageAnalystRating || data.recommendationKey || data.targetMeanPrice) {
            html += `<h4 class="mt-3 mb-2 h6">Analyst Recommendations</h4>`;
            html += `<div class="row">`;
            
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
                        <div class="col-sm-6 col-md-4 mb-3">
                            <div class="small text-muted">${item.label}</div>
                            <div class="font-weight-medium">${item.value}</div>
                        </div>
                    `;
                }
            });
            
            html += `</div>`;
        }
        
        // Financial Highlights subsection
        html += `<h4 class="mt-3 mb-2 h6">Financial Highlights</h4>`;
        html += `<div class="row">`;
        
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
                    <div class="col-sm-6 col-md-4 mb-3">
                        <div class="small text-muted">${item.label}</div>
                        <div class="font-weight-medium">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Financial Health Ratios subsection
        html += `<h4 class="mt-3 mb-2 h6">Financial Health Ratios</h4>`;
        html += `<div class="row">`;
        
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
                    <div class="col-sm-6 col-md-4 mb-3">
                        <div class="small text-muted">${item.label}</div>
                        <div class="font-weight-medium">${item.value}</div>
                    </div>
                `;
            }
        });
        
        html += `</div>`;
        
        // Key executive team (if data available)
        if (data.companyOfficers && data.companyOfficers.length > 0) {
            html += `<h3>Key Executives</h3>`;
            html += `<div class="card card-body mb-3">`;
            html += `<div class="table-responsive">`;
            html += `<table class="table table-bordered">`;
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
        return `<span class="text-success">+${percent}</span>`;
    } else if (value < 0) {
        return `<span class="text-danger">${percent}</span>`;
    } else {
        return percent;
    }
}

/**
 * Generate performance arrows based on percentage thresholds (5%, 10%, 20%)
 * @param {number} value - The percentage value (as decimal, e.g., 0.15 for 15%)
 * @returns {string} - HTML with colored arrows indicating performance level
 */
function getPerformanceArrows(value) {
    if (value === null || value === undefined) return '';
    
    const absValue = Math.abs(value);
    const isPositive = value > 0;
    const colorClass = isPositive ? 'text-success' : value < 0 ? 'text-danger' : 'text-muted';
    let arrowCount = 0;
    
    if (Math.abs(value) < 0.005) { // ~0% - neutral
        return `<span class="text-muted ml-2">—</span>`;
    }
    
    // Thresholds: 5%, 10%, 20%
    if (absValue >= 0.05) arrowCount = 1;
    if (absValue >= 0.10) arrowCount = 2;
    if (absValue >= 0.20) arrowCount = 3;
    if (absValue >= 0.30) arrowCount = 4; // 30%+ gets 4 arrows
    
    const arrow = isPositive ? '↑' : '↓';
    const arrows = arrow.repeat(arrowCount);
    
    return `<span class="${colorClass} ml-2 font-weight-bold">${arrows}</span>`;
}

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

// Helper function to get user-friendly field names for messages
function getFieldDisplayName(fieldName) {
    const displayNames = {
        'balance_sheet': 'Balance Sheet',
        'ticker_info': 'Ticker Info',
        'profit_loss': 'Profit & Loss',
        'cash_flow': 'Cash Flow'
    };
    return displayNames[fieldName] || fieldName;
}

// Helper function to format a json string for display
function formatJsonForDisplay(jsonString, title = "Financial Data", currency = "USD") {
    try {
        const jsonObj = JSON.parse(jsonString);
        
        // Check if the JSON structure matches the financial data pattern
        // (keys are dates and values are objects with financial metrics)
        const isFinancialTable = Object.keys(jsonObj).every(key => 
            key.includes('T00:00:00.000') && typeof jsonObj[key] === 'object'
        );
        
        if (isFinancialTable) {
            return formatFinancialTable(jsonObj, title, currency);
        }
        
        // If not a financial table, use the standard JSON formatter
        return "";
    } catch (e) {
        return `<div class="text-danger">Invalid JSON: ${e.message}</div>`;
    }
}

// Function to format financial data as a table
function formatFinancialTable(data, title = "Financial Data", currency = "USD") {
    // Get all dates and sort them (newest first)
    const dates = Object.keys(data).sort().reverse();
    
    if (dates.length === 0) return '<div class="text-muted">No data available</div>';
    
    // Get all possible metrics from all date entries while preserving order
    const allMetrics = [];
    // First, get metrics from the first date entry to establish initial order
    if (dates.length > 0) {
        const firstDate = dates[0];
        Object.keys(data[firstDate]).forEach(metric => {
            if (!allMetrics.includes(metric)) {
                allMetrics.push(metric);
            }
        });
    }
    
    // Then add any additional metrics from other dates that weren't in the first date
    dates.slice(1).forEach(date => {
        Object.keys(data[date]).forEach(metric => {
            if (!allMetrics.includes(metric)) {
                allMetrics.push(metric);
            }
        });
    });
    
    // Get currency symbol for formatting
    const currencySymbol = getCurrencySymbol(currency);
    
    // Generate table HTML
    let html = `
        <style>
            .financial-table {
                width: 100%;
                border-collapse: collapse;
                font-family: var(--font-stack);
                font-size: 13px;
                margin-bottom: 20px;
                overflow-x: auto;
            }
            .financial-table th, .financial-table td {
                border: 1px solid #e0e0e0;
                padding: 8px;
                text-align: right;
            }
            .financial-table th {
                background-color: #f8f8f8;
                font-weight: 600;
                position: sticky;
                top: 0;
                z-index: 10;
            }
            .financial-table tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .financial-table tr:hover {
                background-color: #f0f7ff;
            }
            .financial-table td.metric-name {
                text-align: left;
                font-weight: 500;
                position: sticky;
                left: 0;
                background-color: #fff;
                z-index: 5;
            }
            .financial-table tr:nth-child(even) td.metric-name {
                background-color: #f9f9f9;
            }
            .financial-table tr:hover td.metric-name {
                background-color: #f0f7ff;
            }
            .financial-table-container {
                max-height: 600px;
                overflow-y: auto;
                margin-bottom: 20px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            .financial-table-search {
                margin-bottom: 10px;
                padding: 8px;
                width: 250px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            .financial-table-toolbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .financial-table-title {
                margin: 0;
                font-size: 16px;
                font-weight: 600;
            }
            .financial-info {
                font-size: 12px;
                color: #666;
                margin-top: 5px;
            }
        </style>

        <script>
            $(document).ready(function() {
                // Filter table rows based on search input
                $("#financial-table-search").on("keyup", function() {
                    const value = $(this).val().toLowerCase();
                    $(".financial-table tbody tr").filter(function() {
                        $(this).toggle($(this).find("td:first").text().toLowerCase().indexOf(value) > -1);
                    });
                });
                
                // Format numbers
                $(".financial-number").each(function() {
                    const value = parseFloat($(this).attr("data-value"));
                    if (!isNaN(value)) {
                        const isLargeValue = Math.abs(value) >= 1000000;
                        let formattedValue;
                        
                        if (isLargeValue) {
                            // Format in millions with 2 decimal places
                            formattedValue = (value / 1000000).toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2
                            }) + 'M';
                        } else {
                            // Regular formatting with appropriate decimal places
                            formattedValue = value.toLocaleString(undefined, {
                                minimumFractionDigits: value % 1 === 0 ? 0 : 2,
                                maximumFractionDigits: 2
                            });
                        }
                        
                        // Add currency symbol if this is a monetary value
                        $(this).text('${currencySymbol}' + formattedValue);
                    }
                });
            });
        </script>

        <div class="financial-table-toolbar">
            <div>
                <h3 class="financial-table-title">${title}</h3>
                <div class="financial-info">All monetary values in ${currency}</div>
            </div>
        </div>
        
        <div class="financial-table-container">
            <table class="financial-table">
                <thead>
                    <tr>
                        <th></th>
    `;
    
    // Add date headers
    dates.forEach(date => {
        // Format the date for display (remove time part)
        const displayDate = date.split('T')[0];
        html += `<th>${displayDate}</th>`;
    });
    
    html += `
                    </tr>
                </thead>
                <tbody>
    `;
    
    // Add rows for each metric in the preserved order
    allMetrics.forEach(metric => {
        html += `<tr><td class="metric-name">${metric}</td>`;
        
        dates.forEach(date => {
            const value = data[date][metric];
            if (value === null || value === undefined) {
                html += `<td>-</td>`;
            } else if (typeof value === 'number') {
                // Add data-value attribute for JavaScript formatting
                html += `<td class="financial-number" data-value="${value}">${value}</td>`;
            } else {
                html += `<td>${value}</td>`;
            }
        });
        
        html += `</tr>`;
    });
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    return html;
}

// Helper function to get currency symbol
function getCurrencySymbol(currency) {
    const currencySymbols = {
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'JPY': '¥',
        'CNY': '¥',
        'HKD': 'HK$',
        'AUD': 'A$',
        'CAD': 'C$',
        'CHF': 'CHF',
        'INR': '₹',
        'SGD': 'S$',
        'ZAR': 'R'
    };
    
    return currencySymbols[currency] || currency + ' ';
}

/**
 * Format and display data coverage in a dialog
 * @param {Object} data - Data coverage information
 * @param {string} securityName - Name of the security
 */
function formatDataCoverageDialog(data, securityName) {
    if (!data) {
        frappe.msgprint(__('No data coverage information available'));
        return;
    }
    
    let html = `
        <style>
            .data-coverage-container {
                font-family: var(--font-stack);
                font-size: 14px;
            }
            .coverage-table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }
            .coverage-table th {
                background-color: #f8f8f8;
                padding: 10px;
                text-align: left;
                border: 1px solid #e0e0e0;
                font-weight: 600;
            }
            .coverage-table td {
                padding: 10px;
                border: 1px solid #e0e0e0;
                vertical-align: top;
            }
            .coverage-table tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .coverage-table tr:hover {
                background-color: #f0f7ff;
            }
            .period-list {
                margin: 0;
                padding-left: 20px;
            }
            .period-list li {
                margin: 3px 0;
            }
            .source-badge {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: 600;
                margin-right: 5px;
            }
            .source-yfinance {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            .source-edgar {
                background-color: #f3e5f5;
                color: #7b1fa2;
            }
            .count-badge {
                display: inline-block;
                background-color: #4caf50;
                color: white;
                padding: 2px 8px;
                border-radius: 10px;
                font-size: 12px;
                font-weight: 600;
            }
            .no-data {
                color: #999;
                font-style: italic;
            }
            .statement-header {
                font-size: 16px;
                font-weight: 600;
                margin: 20px 0 10px 0;
                color: #333;
                border-bottom: 2px solid #2196f3;
                padding-bottom: 5px;
            }
        </style>
        <div class="data-coverage-container">
    `;
    
    // Helper function to format periods list
    const formatPeriodsList = (periods) => {
        if (!periods || periods.length === 0) {
            return '<span class="no-data">No data available</span>';
        }
        let list = '<ul class="period-list">';
        periods.forEach(period => {
            list += `<li>${period}</li>`;
        });
        list += '</ul>';
        return list;
    };
    
    // Process each statement type
    const statementTypes = ['Income Statement', 'Balance Sheet', 'Cash Flow'];
    
    statementTypes.forEach(statementType => {
        const stmtData = data[statementType];
        if (!stmtData) return;
        
        html += `<div class="statement-header">${statementType}</div>`;
        html += '<table class="coverage-table">';
        html += `
            <thead>
                <tr>
                    <th>Period Type</th>
                    <th>Data Source</th>
                    <th>Count</th>
                    <th>Available Periods</th>
                </tr>
            </thead>
            <tbody>
        `;
        
        // Display data for each period type and source
        ['Annual', 'Quarterly', 'TTM'].forEach(periodType => {
            if (stmtData[periodType]) {
                Object.keys(stmtData[periodType]).forEach(source => {
                    const sourceData = stmtData[periodType][source];
                    const sourceBadgeClass = source === 'YFinance' ? 'source-yfinance' : 'source-edgar';
                    
                    html += `
                        <tr>
                            <td><strong>${periodType}</strong></td>
                            <td><span class="source-badge ${sourceBadgeClass}">${source}</span></td>
                            <td><span class="count-badge">${sourceData.count}</span></td>
                            <td>${formatPeriodsList(sourceData.periods)}</td>
                        </tr>
                    `;
                });
            }
        });
        
        html += `
            </tbody>
        </table>
        `;
    });
    
    html += '</div>';
    
    // Display in a dialog
    frappe.msgprint({
        title: __('Financial Data Coverage - {0}', [securityName]),
        message: html,
        wide: true
    });
}

/**
 * Create or reopen a ph_agent Chat Session linked to a document.
 * Navigates to the chat page in the same tab.
 */
function _create_or_reopen_chat_session(frm, ref_doctype, persona, llm_provider) {
    if (!llm_provider) {
        frappe.msgprint(__('No LLM Provider found. Please configure one in PH Agent > LLM Provider.'));
        return;
    }
    
    // Use a generic title — ph_agent's _reference_enrich_title will prepend
    // the document name automatically (e.g. "BOC — Chat")
    var session_title = 'Chat';
    
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Chat Session',
            filters: {
                reference_doctype: ref_doctype,
                reference_name: frm.doc.name,
                user: frappe.session.user,
                status: 'Open'
            },
            fieldname: ['name']
        },
        callback: function(r) {
            if (r.message && r.message.name) {
                // Reopen existing session — navigate to chat page in same tab
                frappe.set_route('chat');
            } else {
                // Create new session
                frappe.call({
                    method: 'frappe.client.insert',
                    args: {
                        doc: {
                            doctype: 'Chat Session',
                            title: session_title,
                            persona: persona,
                            llm_provider: llm_provider,
                            reference_doctype: ref_doctype,
                            reference_name: frm.doc.name,
                            user: frappe.session.user,
                            status: 'Open',
                            is_temporary: 0
                        }
                    },
                    callback: function(create_r) {
                        if (create_r.message && create_r.message.name) {
                            frappe.set_route('chat');
                        }
                    }
                });
            }
        }
    });
}

/**
 * Render a "Chat Sessions" section on the form showing past ph_agent sessions
 * linked to this document.
 */
function _render_chat_sessions_section(frm, ref_doctype, ref_name) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Chat Session',
            filters: {
                reference_doctype: ref_doctype,
                reference_name: ref_name,
                user: frappe.session.user
            },
            fields: ['name', 'title', 'modified', 'persona', 'status'],
            order_by: 'modified desc',
            limit_page_length: 10
        },
        callback: function(r) {
            if (!r.message || r.message.length === 0) return;
            
            let rows = r.message.map(s => {
                let status_badge = s.status === 'Open' 
                    ? '<span class="indicator green">Open</span>'
                    : '<span class="indicator grey">' + s.status + '</span>';
                let modified = frappe.datetime.comment_when(s.modified);
                return `<tr>
                    <td><a href="/app/chat?session=${s.name}" target="_blank">${s.title || s.name}</a></td>
                    <td>${s.persona || '-'}</td>
                    <td>${status_badge}</td>
                    <td>${modified}</td>
                </tr>`;
            }).join('');
            
            let html = `<div class="frappe-control" style="margin-top: 15px;">
                <label class="control-label" style="margin-bottom: 5px;">${__('Chat Sessions')}</label>
                <div class="control-value">
                    <table class="table table-bordered table-hover" style="margin-bottom: 0;">
                        <thead><tr>
                            <th>${__('Session')}</th>
                            <th>${__('Persona')}</th>
                            <th>${__('Status')}</th>
                            <th>${__('Last Activity')}</th>
                        </tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>`;
            
            // Add the HTML after the main form actions
            if (frm.fields_dict.chat_sessions_html) {
                frm.set_df_property('chat_sessions_html', 'options', html);
            }
        }
    });
}

