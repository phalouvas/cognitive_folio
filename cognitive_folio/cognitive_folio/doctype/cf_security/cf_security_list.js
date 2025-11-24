frappe.listview_settings['CF Security'] = {
	onload(listview) {
		// Add bulk import action
		listview.page.add_action_item(__('Bulk Import Periods'), () => {
			const selected = listview.get_checked_items().map(d => d.name);
			if (!selected.length) {
				frappe.msgprint(__('Select at least one security to import.'));
				return;
			}
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

		function start_bulk_import(securities, opts) {
			const progress_id = Math.random().toString(36).substring(2, 12);
			let progress_dialog = new frappe.ui.Dialog({
				title: __('Import Progress'),
				fields: [
					{ fieldname: 'html', fieldtype: 'HTML' }
				],
				primary_action_label: __('Close'),
				primary_action() {
					progress_dialog.hide();
				}
			});
			progress_dialog.show();
			const html = `
				<div id="bulk-import-status" style="max-height:300px;overflow:auto;font-size:12px"></div>
				<div style="margin-top:1rem">
					<div class="progress" style="height:20px">
						<div class="progress-bar" role="progressbar" style="width:0%">0%</div>
					</div>
				</div>
			`;
			progress_dialog.set_value('html', html);

			const channel = 'bulk_import_progress_' + progress_id;
			let finished = false;
			frappe.realtime.on(channel, data => {
				const pct = data.total ? Math.round(((data.current_index + 1) / data.total) * 100) : 0;
				const bar = progress_dialog.$wrapper.find('.progress-bar');
				if (!data.finished) {
					bar.css('width', pct + '%').text(pct + '%');
				}
				const log = progress_dialog.$wrapper.find('#bulk-import-status');
				if (data.security) {
					log.append(`<div><strong>${data.security}</strong> imported:${data.imported} updated:${data.updated} skipped:${data.skipped} errors:${data.errors_count}</div>`);
				}
				if (data.finished && !finished) {
					finished = true;
					bar.css('width', '100%').text('100%');
				}
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
						if (summary.aborted) {
							log.append('<div style="color:red">Import aborted due to error.</div>');
						}
						const details = JSON.stringify(summary.results, null, 2);
						const blob = new Blob([details], { type: 'application/json' });
						const url = URL.createObjectURL(blob);
						log.append(`<div style="margin-top:8px"><a class="btn btn-sm btn-secondary" href="${url}" download="bulk_import_results.json">${__('Download Details JSON')}</a></div>`);
					}
				}
			});
		}
	},

	get_indicator(doc) {
		if (doc.needs_update) {
			return [__("Needs Update"), "red", "needs_update,=,1"];
		}
		if (doc.days_since_last_period <= 30) {
			return [__("Fresh"), "green", "days_since_last_period,<=,30"];
		} else if (doc.days_since_last_period <= 90) {
			return [__("Stale"), "orange", "days_since_last_period,>,30|days_since_last_period,<=,90"];
		} else {
			return [__("Very Stale"), "red", "days_since_last_period,>,90"];
		}
	},

	add_filter: function(listview) {
		listview.page.add_menu_item(__("Needs Financial Update"), function() {
			listview.filter_area.add([
				["CF Security", "needs_update", "=", 1]
			]);
		});
	}
};
