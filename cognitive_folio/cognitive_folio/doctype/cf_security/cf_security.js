frappe.ui.form.on('CF Security', {
    refresh: function(frm) {
        // Add "Fetch Market Data" button
        frm.add_custom_button(__('Fetch Market Data'), function() {
            frm.call('fetch_market_data')
                .then(r => {
                    frm.refresh();
                });
        }, __('Actions'));
    },

    // Add an event handler for security_name field
    security_name: function(frm) {
        // Only search if security_name has at least 3 characters
        if(frm.doc.security_name && frm.doc.security_name.length >= 3) {
            // Don't search if we already have a symbol
            if(frm.doc.symbol) return;
            
            // Debounce the search to avoid too many API calls
            if(frm.security_name_timeout) clearTimeout(frm.security_name_timeout);
            
            frm.security_name_timeout = setTimeout(() => {
                search_stocks(frm, frm.doc.security_name);
            }, 800); // Wait 800ms after user stops typing
        }
    }
});

// Function to search for stocks based on search term
function search_stocks(frm, search_term) {
    frappe.call({
        method: 'cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.search_stock_symbols',
        args: {
            search_term: search_term
        },
        callback: function(r) {
            if (r.message.error) {
                console.log("Stock search error:", r.message.error);
                return;
            }
            
            if (!r.message.results || r.message.results.length === 0) {
                console.log("No stocks found for:", search_term);
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
                            We found potential matches for <strong>${search_term}</strong>.
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
                    <td>${stock.symbol}</td>
                    <td>${stock.name || ''}</td>
                    <td>${stock.exchange || ''}</td>
                    <td>${stock.sector || ''}</td>
                    <td>${stock.industry || ''}</td>
                    <td><button class="btn btn-xs btn-primary select-stock" 
                        data-symbol="${stock.symbol}" 
                        data-name="${stock.name || ''}"
                        data-sector="${stock.sector || ''}"
                        data-industry="${stock.industry || ''}"
                        data-price="${stock.current_price || ''}"
                        data-currency="${stock.currency || ''}"
                        data-exchange="${stock.exchange || ''}">Select</button></td>
                </tr>`;
            });
            
            results_html += '</tbody></table></div>';
            
            result_dialog.fields_dict.results_html.$wrapper.html(results_html);
            
            // Handle stock selection - Now with more data!
            result_dialog.$wrapper.on('click', '.select-stock', function() {
                let symbol = $(this).attr('data-symbol');
                let company = $(this).attr('data-name');
                let sector = $(this).attr('data-sector');
                let industry = $(this).attr('data-industry');
                let price = $(this).attr('data-price');
                let currency = $(this).attr('data-currency');
                let exchange = $(this).attr('data-exchange');
                
                // Set values directly from search results
                frm.set_value('symbol', symbol);
                if (company) frm.set_value('security_name', company);
                if (sector) frm.set_value('sector', sector);
                if (industry) frm.set_value('industry', industry);
                if (price) frm.set_value('current_price', parseFloat(price));
                if (exchange) frm.set_value('stock_exchange', exchange);
                
                // Set currency if it exists
                if (currency && frappe.meta.has_field(frm.doctype, 'currency')) {
                    frm.set_value('currency', currency);
                }
                
                result_dialog.hide();
                
                // Save the form with the updated values
                if (!frm.doc.__islocal) {
                    frm.save();
                }
                
                frappe.show_alert(__(`Selected ${symbol} with all available data`));
            });
            
            result_dialog.show();
        }
    });
}