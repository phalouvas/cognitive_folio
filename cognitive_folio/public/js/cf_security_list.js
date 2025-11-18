frappe.listview_settings['CF Security'] = frappe.listview_settings['CF Security'] || {};

frappe.listview_settings['CF Security'].onload = function(listview) {
    // Add "Fetch Latest Data" button under Actions
    if (frappe.model.can_create("CF Security")) {
        listview.page.add_action_item(__("Fetch Latest Data"), function() {
            const selected_docs = listview.get_checked_items();
            const docnames = listview.get_checked_items(true);

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Security"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.fetch_data_selected",
                args: {
                    docnames: docnames,
                    with_fundamentals: false
                },
                freeze: true,
                freeze_message: __("Processing..."),
                callback: function(r) {
                    if (!r.exc) {
                        listview.refresh();
                    }
                }
            });
        });

        listview.page.add_action_item(__("Fetch Fundamentals"), function() {
            const selected_docs = listview.get_checked_items();
            const docnames = listview.get_checked_items(true);

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Security"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.fetch_data_selected",
                args: {
                    docnames: docnames,
                    with_fundamentals: true
                },
                freeze: true,
                freeze_message: __("Processing..."),
                callback: function(r) {
                    if (!r.exc) {
                        listview.refresh();
                    }
                }
            });
        });

        listview.page.add_action_item(__("Generate AI Suggestion"), function() {
            const selected_docs = listview.get_checked_items();
            const docnames = listview.get_checked_items(true);

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Security"));
                return;
            }

            frappe.call({
                method: "cognitive_folio.cognitive_folio.doctype.cf_security.cf_security.generate_ai_suggestion_selected",
                args: {
                    docnames: docnames
                },
                freeze: true,
                freeze_message: __("Processing..."),
                callback: function(r) {
                    if (!r.exc) {
                        listview.refresh();
                    }
                }
            });
        });

        listview.page.add_action_item(__("Copy to Portfolio"), function() {
            const selected_docs = listview.get_checked_items();

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one CF Portfolio Holding"));
                return;
            }

            // Check if quantity or average_purchase_price are missing
            const missing_data = selected_docs.filter(doc => 
                !doc.current_price
            );

            if (missing_data.length > 0) {
                frappe.throw(__("Please add current price in the list view before copying holdings."));
                return;
            }

            // Show dialog to select target portfolio
            let dialog = new frappe.ui.Dialog({
                title: __('Copy Holdings to Portfolio'),
                fields: [
                    {
                        label: __('Target Portfolio'),
                        fieldname: 'target_portfolio',
                        fieldtype: 'Link',
                        options: 'CF Portfolio',
                        reqd: 1,
                        description: __('Select the portfolio where you want to copy the selected holdings')
                    }
                ],
                primary_action_label: __('Copy Holdings'),
                primary_action(values) {
                    if (!values.target_portfolio) {
                        frappe.throw(__("Please select a target portfolio"));
                        return;
                    }

                    // Prepare holdings data for copying
                    const holdings_data = selected_docs.map(doc => ({
                        portfolio: values.target_portfolio,
                        security: doc.name,
                        quantity: 1,
                        average_purchase_price: doc.current_price
                    }));

                    frappe.call({
                        method: "cognitive_folio.cognitive_folio.doctype.cf_portfolio_holding.cf_portfolio_holding.copy_holdings_to_portfolio",
                        args: {
                            holdings_data: holdings_data
                        },
                        freeze: true,
                        freeze_message: __("Copying holdings..."),
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.show_alert({
                                    message: __('Holdings copied successfully to {0}', [values.target_portfolio]),
                                    indicator: 'green'
                                });
                                dialog.hide();
                                listview.refresh();
                            }
                        }
                    });
                }
            });

            dialog.show();
        });
    }
};

// Extend with Bulk Import (foreground and background) actions
frappe.listview_settings['CF Security'].onload = (function(original) {
    return function(listview) {
        if (original) original(listview);
        const add_action = () => {
            listview.page.add_action_item(__('Bulk Import Periods'), () => {
                const selected = listview.get_checked_items().map(d => d.name);
                if (!selected.length) { frappe.msgprint(__('Select at least one security to import.')); return; }
                const d = new frappe.ui.Dialog({
                    title: __('Bulk Import Financial Periods'),
                    fields: [
                        { fieldname: 'replace_existing', fieldtype: 'Check', label: __('Replace Existing Periods'), default: 0 },
                        { fieldname: 'respect_override', fieldtype: 'Check', label: __('Respect Override Yahoo'), default: 1 },
                        { fieldname: 'stop_on_error', fieldtype: 'Check', label: __('Stop on First Error'), default: 0 },
                    ],
                    primary_action_label: __('Start Import'),
                    primary_action(values) {
                        d.hide();
                        start_bulk_import(selected, values);
                    }
                });
                d.show();
            });

            listview.page.add_action_item(__('Enqueue Bulk Import (Background)'), () => {
                const selected = listview.get_checked_items().map(d => d.name);
                const d = new frappe.ui.Dialog({
                    title: __('Enqueue Bulk Import'),
                    fields: [
                        { fieldname: 'use_all', fieldtype: 'Check', label: __('Ignore Selection (Import All Securities)'), default: 0 },
                        { fieldname: 'replace_existing', fieldtype: 'Check', label: __('Replace Existing Periods'), default: 0 },
                        { fieldname: 'respect_override', fieldtype: 'Check', label: __('Respect Override Yahoo'), default: 1 },
                        { fieldname: 'stop_on_error', fieldtype: 'Check', label: __('Stop on First Error'), default: 0 }
                    ],
                    primary_action_label: __('Enqueue'),
                    primary_action(values) {
                        if (!values.use_all && !selected.length) { frappe.msgprint(__('Select securities or check Import All.')); return; }
                        d.hide();
                        enqueue_bulk_import(values.use_all ? null : selected, values);
                    }
                });
                d.show();
            });
        };

        function start_bulk_import(securities, opts) {
            const progress_id = Math.random().toString(36).substring(2, 12);
            let progress_dialog = new frappe.ui.Dialog({
                title: __('Import Progress'),
                fields: [{ fieldname: 'html', fieldtype: 'HTML' }],
                primary_action_label: __('Close'),
                primary_action() { progress_dialog.hide(); }
            });
            progress_dialog.show();
            const html = `
                <div id="bulk-import-status" style="max-height:300px;overflow:auto;font-size:12px"></div>
                <div style="margin-top:1rem">
                    <div class="progress" style="height:20px">
                        <div class="progress-bar" role="progressbar" style="width:0%">0%</div>
                    </div>
                </div>`;
            progress_dialog.set_value('html', html);
            const channel = 'bulk_import_progress_' + progress_id;
            let finished = false;
            frappe.realtime.on(channel, data => {
                const pct = data.total ? Math.round(((data.current_index + 1) / data.total) * 100) : 0;
                const bar = progress_dialog.$wrapper.find('.progress-bar');
                if (!data.finished) { bar.css('width', pct + '%').text(pct + '%'); }
                const log = progress_dialog.$wrapper.find('#bulk-import-status');
                if (data.security) {
                    log.append(`<div><strong>${data.security}</strong> imported:${data.imported} updated:${data.updated} skipped:${data.skipped} errors:${data.errors_count}</div>`);
                }
                if (data.finished && !finished) { finished = true; bar.css('width', '100%').text('100%'); }
            });

            frappe.call({
                method: 'cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period.bulk_import_financial_periods',
                args: {
                    security_names: securities,
                    replace_existing: opts.replace_existing ? 1 : 0,
                    respect_override: opts.respect_override ? 1 : 0,
                    stop_on_error: opts.stop_on_error ? 1 : 0,
                    progress_id: progress_id
                },
                freeze: true,
                freeze_message: __('Starting bulk import...'),
                callback(r) {
                    if (r.message) {
                        const summary = r.message;
                        const log = progress_dialog.$wrapper.find('#bulk-import-status');
                        log.append('<hr>');
                        log.append(`<div><strong>Summary:</strong> Imported ${summary.total_imported}, Updated ${summary.total_updated}, Skipped ${summary.total_skipped}, Errors ${summary.total_errors}</div>`);
                        if (summary.aborted) { log.append('<div style="color:red">Import aborted due to error.</div>'); }
                        const details = JSON.stringify(summary.results, null, 2);
                        const blob = new Blob([details], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        log.append(`<div style="margin-top:8px"><a class="btn btn-sm btn-secondary" href="${url}" download="bulk_import_results.json">${__('Download Details JSON')}</a></div>`);
                    }
                }
            });
        }

        function enqueue_bulk_import(securities, opts) {
            frappe.call({
                method: 'cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period.enqueue_bulk_import_financial_periods',
                args: {
                    security_names: securities,
                    replace_existing: opts.replace_existing ? 1 : 0,
                    respect_override: opts.respect_override ? 1 : 0,
                    stop_on_error: opts.stop_on_error ? 1 : 0
                },
                freeze: true,
                freeze_message: __('Enqueuing bulk import...'),
                callback(r) {
                    if (!r.message) return;
                    const { job_id, cache_key } = r.message;
                    frappe.msgprint(__('Bulk import enqueued (Job ID: {0}). Polling for result...', [job_id]));
                    poll_job_result(cache_key, job_id, 0);
                }
            });
        }

        function poll_job_result(cache_key, job_id, attempts) {
            if (attempts > 120) { frappe.msgprint(__('Bulk import result polling timed out.')); return; }
            setTimeout(() => {
                frappe.call({
                    method: 'cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period.get_bulk_import_job_result',
                    args: { cache_key },
                    callback(r) {
                        if (r.message && r.message.ready) {
                            const res = r.message.result;
                            frappe.msgprint(__('Bulk Import Completed: Imported {0}, Updated {1}, Skipped {2}, Errors {3}', [res.total_imported, res.total_updated, res.total_skipped, res.total_errors]));
                            const details = JSON.stringify(res.results, null, 2);
                            const blob = new Blob([details], { type: 'application/json' });
                            const url = URL.createObjectURL(blob);
                            frappe.msgprint(`<a class="btn btn-sm btn-secondary" href="${url}" download="bulk_import_results_${job_id}.json">${__('Download Results JSON')}</a>`);
                        } else {
                            poll_job_result(cache_key, job_id, attempts + 1);
                        }
                    }
                });
            }, 1000);
        }

        add_action();
    };
})(frappe.listview_settings['CF Security'].onload);
