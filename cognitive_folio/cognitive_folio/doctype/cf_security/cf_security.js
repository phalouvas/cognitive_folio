frappe.ui.form.on('CF Security', {
    refresh: function(frm) {
        // Add "Fetch Market Data" button
        frm.add_custom_button(__('Fetch Market Data'), function() {
            frm.call('fetch_market_data')
                .then(r => {
                    frm.refresh();
                });
        }, __('Actions'));
        
        // Add "Search Stocks" button that opens a dialog
        frm.add_custom_button(__('Search Stocks'), function() {
            let d = new frappe.ui.Dialog({
                title: __('Search for Stocks'),
                fields: [
                    {
                        label: __('Search Term'),
                        fieldname: 'search_term',
                        fieldtype: 'Data',
                        reqd: 1,
                        description: __('Enter company name or symbol')
                    }
                ],
                primary_action_label: __('Search'),
                primary_action: function() {
                    let values = d.get_values();
                    
                    frappe.call({
                        method: 'cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.search_stock_symbols',
                        args: {
                            search_term: values.search_term
                        },
                        callback: function(r) {
                            d.hide();
                            if (r.message.error) {
                                frappe.msgprint(r.message.error);
                                return;
                            }
                            
                            if (!r.message.results || r.message.results.length === 0) {
                                frappe.msgprint(__('No stocks found matching your search.'));
                                return;
                            }
                            
                            // Show results in a dialog
                            let result_dialog = new frappe.ui.Dialog({
                                title: __('Search Results'),
                                fields: [
                                    {
                                        fieldname: 'results_html',
                                        fieldtype: 'HTML'
                                    }
                                ]
                            });
                            
                            let results_html = '<div class="stock-search-results">';
                            results_html += '<table class="table table-bordered"><thead><tr>';
                            results_html += '<th>Symbol</th><th>Name</th><th>Exchange</th><th>Type</th><th>Action</th>';
                            results_html += '</tr></thead><tbody>';
                            
                            r.message.results.forEach(stock => {
                                results_html += `<tr>
                                    <td>${stock.symbol}</td>
                                    <td>${stock.name || ''}</td>
                                    <td>${stock.exchange || ''}</td>
                                    <td>${stock.type || ''}</td>
                                    <td><button class="btn btn-xs btn-primary select-stock" 
                                        data-symbol="${stock.symbol}" 
                                        data-name="${stock.name || ''}">Select</button></td>
                                </tr>`;
                            });
                            
                            results_html += '</tbody></table></div>';
                            
                            result_dialog.fields_dict.results_html.$wrapper.html(results_html);
                            
                            // Handle stock selection
                            result_dialog.$wrapper.on('click', '.select-stock', function() {
                                let symbol = $(this).attr('data-symbol');
                                let company = $(this).attr('data-name');
                                
                                frm.set_value('symbol', symbol);
                                if (!frm.doc.security_name) {
                                    frm.set_value('security_name', company);
                                }
                                
                                result_dialog.hide();
                                frappe.show_alert(__(`Selected ${symbol}`));
                            });
                            
                            result_dialog.show();
                        }
                    });
                }
            });
            
            d.show();
        }, __('Actions'));
    }
});