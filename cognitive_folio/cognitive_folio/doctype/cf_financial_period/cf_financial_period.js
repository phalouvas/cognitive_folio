// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on("CF Financial Period", {
	refresh(frm) {
		// Add custom buttons or logic here if needed
		if (!frm.is_new()) {
			// Show period summary
			if (frm.doc.total_revenue || frm.doc.net_income) {
				frm.dashboard.add_indicator(
					__('Period: {0} {1}', [frm.doc.fiscal_year, frm.doc.fiscal_quarter || '']), 
					'blue'
				);
			}
			
			// Add "Copy from Previous Period" button
			frm.add_custom_button(__('Copy from Previous Period'), function() {
				copy_from_previous_period(frm);
			}, __('Actions'));
			
			// Add "Show Period Comparison" button
			frm.add_custom_button(__('Show Period Comparison'), function() {
				show_period_comparison_dialog(frm);
			}, __('Actions'));
			
			// Add validation warnings as alerts
			show_validation_warnings(frm);
		}
		
		// Quick entry mode hint
		if (frm.is_new()) {
			frm.set_intro(__('Quick Tip: Fill in Revenue, Net Income, and Total Assets for basic analysis. Other fields will auto-calculate.'), 'blue');
		}
	},
	
	onload(frm) {
		// Auto-calculate missing fields on load
		if (!frm.is_new()) {
			auto_calculate_missing_fields(frm);
		}
	},
	
	total_revenue(frm) {
		// Auto-calculate margins when revenue changes
		calculate_margins(frm);
	},
	
	gross_profit(frm) {
		calculate_margins(frm);
	},
	
	operating_income(frm) {
		calculate_margins(frm);
	},
	
	net_income(frm) {
		calculate_margins(frm);
		calculate_ratios(frm);
	},
	
	total_assets(frm) {
		calculate_ratios(frm);
	},
	
	total_debt(frm) {
		calculate_ratios(frm);
	},
	
	shareholders_equity(frm) {
		calculate_ratios(frm);
	},
	
	current_assets(frm) {
		calculate_ratios(frm);
	},
	
	current_liabilities(frm) {
		calculate_ratios(frm);
	}
});

function calculate_margins(frm) {
	if (frm.doc.total_revenue && frm.doc.total_revenue != 0) {
		if (frm.doc.gross_profit) {
			frm.set_value('gross_margin', (frm.doc.gross_profit / frm.doc.total_revenue) * 100);
		}
		if (frm.doc.operating_income) {
			frm.set_value('operating_margin', (frm.doc.operating_income / frm.doc.total_revenue) * 100);
		}
		if (frm.doc.net_income) {
			frm.set_value('net_margin', (frm.doc.net_income / frm.doc.total_revenue) * 100);
		}
	}
}

function calculate_ratios(frm) {
	// ROE
	if (frm.doc.shareholders_equity && frm.doc.shareholders_equity != 0 && frm.doc.net_income) {
		frm.set_value('roe', (frm.doc.net_income / frm.doc.shareholders_equity) * 100);
	}
	
	// ROA
	if (frm.doc.total_assets && frm.doc.total_assets != 0 && frm.doc.net_income) {
		frm.set_value('roa', (frm.doc.net_income / frm.doc.total_assets) * 100);
	}
	
	// Debt to Equity
	if (frm.doc.shareholders_equity && frm.doc.shareholders_equity != 0 && frm.doc.total_debt) {
		frm.set_value('debt_to_equity', frm.doc.total_debt / frm.doc.shareholders_equity);
	}
	
	// Current Ratio
	if (frm.doc.current_liabilities && frm.doc.current_liabilities != 0 && frm.doc.current_assets) {
		frm.set_value('current_ratio', frm.doc.current_assets / frm.doc.current_liabilities);
	}
	
	// Quick Ratio
	if (frm.doc.current_liabilities && frm.doc.current_liabilities != 0 && frm.doc.current_assets) {
		let inventory = frm.doc.inventory || 0;
		frm.set_value('quick_ratio', (frm.doc.current_assets - inventory) / frm.doc.current_liabilities);
	}
	
	// Asset Turnover
	if (frm.doc.total_assets && frm.doc.total_assets != 0 && frm.doc.total_revenue) {
		frm.set_value('asset_turnover', frm.doc.total_revenue / frm.doc.total_assets);
	}
}

// Copy data from previous period
function copy_from_previous_period(frm) {
	frappe.call({
		method: 'cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period.get_previous_period',
		args: {
			security: frm.doc.security,
			period_type: frm.doc.period_type,
			fiscal_year: frm.doc.fiscal_year,
			fiscal_quarter: frm.doc.fiscal_quarter
		},
		callback: function(r) {
			if (r.message) {
				let prev = r.message;
				let d = new frappe.ui.Dialog({
					title: __('Copy from Previous Period'),
					fields: [
						{
							fieldtype: 'HTML',
							options: `<div style="padding: 10px; background: #f8f9fa; border-radius: 4px; margin-bottom: 15px;">
								<strong>Previous Period:</strong> ${prev.period}<br>
								<strong>Data Source:</strong> ${prev.data_source || 'N/A'}<br>
								<strong>Quality Score:</strong> ${prev.data_quality_score || 'N/A'}
							</div>`
						},
						{
							fieldtype: 'Section Break',
							label: 'Select Fields to Copy'
						},
						{
							fieldtype: 'Check',
							fieldname: 'copy_all',
							label: 'Copy All Fields',
							default: 1,
							onchange: function() {
								let copy_all = this.get_value();
								// Toggle all other checkboxes
								['income', 'balance', 'cashflow'].forEach(group => {
									d.set_value('copy_' + group, copy_all);
								});
							}
						},
						{
							fieldtype: 'Column Break'
						},
						{
							fieldtype: 'Check',
							fieldname: 'copy_income',
							label: 'Income Statement',
							default: 1
						},
						{
							fieldtype: 'Check',
							fieldname: 'copy_balance',
							label: 'Balance Sheet',
							default: 1
						},
						{
							fieldtype: 'Check',
							fieldname: 'copy_cashflow',
							label: 'Cash Flow',
							default: 1
						}
					],
					primary_action_label: __('Copy Data'),
					primary_action(values) {
						let fields_to_copy = [];
						
						if (values.copy_income || values.copy_all) {
							fields_to_copy.push(
								'total_revenue', 'cost_of_revenue', 'gross_profit',
								'operating_expenses', 'operating_income', 'net_income',
								'ebitda', 'diluted_eps'
							);
						}
						
						if (values.copy_balance || values.copy_all) {
							fields_to_copy.push(
								'total_assets', 'current_assets', 'total_liabilities',
								'current_liabilities', 'shareholders_equity', 'total_debt',
								'cash_and_equivalents', 'inventory'
							);
						}
						
						if (values.copy_cashflow || values.copy_all) {
							fields_to_copy.push(
								'operating_cash_flow', 'investing_cash_flow',
								'financing_cash_flow', 'capital_expenditures', 'free_cash_flow'
							);
						}
						
						// Copy the fields
						fields_to_copy.forEach(field => {
							if (prev[field] !== null && prev[field] !== undefined) {
								frm.set_value(field, prev[field]);
							}
						});
						
						frappe.show_alert({
							message: __('Data copied from previous period. Please review and update as needed.'),
							indicator: 'green'
						});
						
						d.hide();
					}
				});
				d.show();
			} else {
				frappe.msgprint(__('No previous period found for this security.'));
			}
		}
	});
}

// Show period comparison dialog
function show_period_comparison_dialog(frm) {
	frappe.call({
		method: 'cognitive_folio.cognitive_folio.doctype.cf_financial_period.cf_financial_period.get_previous_period',
		args: {
			security: frm.doc.security,
			period_type: frm.doc.period_type,
			fiscal_year: frm.doc.fiscal_year,
			fiscal_quarter: frm.doc.fiscal_quarter
		},
		callback: function(r) {
			if (r.message) {
				let prev = r.message;
				let current = frm.doc;
				
				// Build comparison HTML
				let comparison_html = `
					<style>
						.comparison-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
						.comparison-table th, .comparison-table td { 
							padding: 8px; 
							border: 1px solid #ddd; 
							text-align: right; 
						}
						.comparison-table th { background: #f8f9fa; font-weight: 600; }
						.comparison-table td:first-child { text-align: left; font-weight: 500; }
						.positive { color: #28a745; }
						.negative { color: #dc3545; }
						.section-header { background: #e9ecef !important; font-weight: bold; }
					</style>
					<table class="comparison-table">
						<thead>
							<tr>
								<th>Metric</th>
								<th>${prev.period}</th>
								<th>${current.period}</th>
								<th>Change</th>
							</tr>
						</thead>
						<tbody>
							<tr class="section-header">
								<td colspan="4">Income Statement</td>
							</tr>
							${format_comparison_row('Revenue', prev.total_revenue, current.total_revenue)}
							${format_comparison_row('Gross Profit', prev.gross_profit, current.gross_profit)}
							${format_comparison_row('Operating Income', prev.operating_income, current.operating_income)}
							${format_comparison_row('Net Income', prev.net_income, current.net_income)}
							${format_comparison_row('Diluted EPS', prev.diluted_eps, current.diluted_eps, true)}
							<tr class="section-header">
								<td colspan="4">Margins</td>
							</tr>
							${format_comparison_row('Gross Margin %', prev.gross_margin * 100, current.gross_margin * 100, true)}
							${format_comparison_row('Operating Margin %', prev.operating_margin * 100, current.operating_margin * 100, true)}
							${format_comparison_row('Net Margin %', prev.net_margin * 100, current.net_margin * 100, true)}
							<tr class="section-header">
								<td colspan="4">Balance Sheet</td>
							</tr>
							${format_comparison_row('Total Assets', prev.total_assets, current.total_assets)}
							${format_comparison_row('Total Liabilities', prev.total_liabilities, current.total_liabilities)}
							${format_comparison_row('Shareholders Equity', prev.shareholders_equity, current.shareholders_equity)}
							${format_comparison_row('Total Debt', prev.total_debt, current.total_debt)}
							<tr class="section-header">
								<td colspan="4">Cash Flow</td>
							</tr>
							${format_comparison_row('Operating Cash Flow', prev.operating_cash_flow, current.operating_cash_flow)}
							${format_comparison_row('Free Cash Flow', prev.free_cash_flow, current.free_cash_flow)}
							<tr class="section-header">
								<td colspan="4">Ratios</td>
							</tr>
							${format_comparison_row('ROE %', prev.roe * 100, current.roe * 100, true)}
							${format_comparison_row('Debt/Equity', prev.debt_to_equity, current.debt_to_equity, true)}
							${format_comparison_row('Current Ratio', prev.current_ratio, current.current_ratio, true)}
						</tbody>
					</table>
				`;
				
				let d = new frappe.ui.Dialog({
					title: __('Period Comparison'),
					size: 'large',
					fields: [
						{
							fieldtype: 'HTML',
							options: comparison_html
						}
					]
				});
				d.show();
			} else {
				frappe.msgprint(__('No previous period found for comparison.'));
			}
		}
	});
}

// Helper function to format comparison rows
function format_comparison_row(label, prev_val, curr_val, is_decimal = false) {
	if (prev_val === null || prev_val === undefined || curr_val === null || curr_val === undefined) {
		return `<tr><td>${label}</td><td>-</td><td>-</td><td>-</td></tr>`;
	}
	
	let change_val = curr_val - prev_val;
	let change_pct = prev_val !== 0 ? (change_val / Math.abs(prev_val)) * 100 : 0;
	let change_class = change_val >= 0 ? 'positive' : 'negative';
	let change_sign = change_val >= 0 ? '+' : '';
	
	let format_val = (val) => {
		if (is_decimal) {
			return val.toFixed(2);
		}
		return val >= 1000000 ? (val / 1000000).toFixed(1) + 'M' : val.toLocaleString();
	};
	
	return `
		<tr>
			<td>${label}</td>
			<td>${format_val(prev_val)}</td>
			<td>${format_val(curr_val)}</td>
			<td class="${change_class}">${change_sign}${change_pct.toFixed(1)}%</td>
		</tr>
	`;
}

// Show validation warnings
function show_validation_warnings(frm) {
	let warnings = [];
	
	// Check for negative equity
	if (frm.doc.shareholders_equity && frm.doc.shareholders_equity < 0) {
		warnings.push('⚠️ Negative shareholders equity detected');
	}
	
	// Check for margins > 100%
	if (frm.doc.gross_margin && frm.doc.gross_margin > 1.0) {
		warnings.push('⚠️ Gross margin exceeds 100%');
	}
	if (frm.doc.operating_margin && frm.doc.operating_margin > 1.0) {
		warnings.push('⚠️ Operating margin exceeds 100%');
	}
	if (frm.doc.net_margin && frm.doc.net_margin > 1.0) {
		warnings.push('⚠️ Net margin exceeds 100%');
	}
	
	// Check for negative revenue
	if (frm.doc.total_revenue && frm.doc.total_revenue < 0) {
		warnings.push('⚠️ Negative revenue detected');
	}
	
	// Check for very high debt/equity
	if (frm.doc.debt_to_equity && frm.doc.debt_to_equity > 10) {
		warnings.push('⚠️ Debt-to-Equity ratio exceeds 10x');
	}
	
	// Check for impossible current ratio
	if (frm.doc.current_ratio && frm.doc.current_ratio < 0) {
		warnings.push('⚠️ Negative current ratio detected');
	}
	
	// Display warnings
	if (warnings.length > 0) {
		frm.dashboard.add_comment(warnings.join('<br>'), 'yellow', true);
	}
}

// Auto-calculate missing fields
function auto_calculate_missing_fields(frm) {
	let calculated = [];
	
	// Calculate gross profit if missing
	if (!frm.doc.gross_profit && frm.doc.total_revenue && frm.doc.cost_of_revenue) {
		frm.set_value('gross_profit', frm.doc.total_revenue - frm.doc.cost_of_revenue);
		calculated.push('Gross Profit');
	}
	
	// Calculate operating income if missing
	if (!frm.doc.operating_income && frm.doc.gross_profit && frm.doc.operating_expenses) {
		frm.set_value('operating_income', frm.doc.gross_profit - frm.doc.operating_expenses);
		calculated.push('Operating Income');
	}
	
	// Calculate free cash flow if missing
	if (!frm.doc.free_cash_flow && frm.doc.operating_cash_flow && frm.doc.capital_expenditures) {
		frm.set_value('free_cash_flow', frm.doc.operating_cash_flow - frm.doc.capital_expenditures);
		calculated.push('Free Cash Flow');
	}
	
	// Calculate cost of revenue if missing
	if (!frm.doc.cost_of_revenue && frm.doc.total_revenue && frm.doc.gross_profit) {
		frm.set_value('cost_of_revenue', frm.doc.total_revenue - frm.doc.gross_profit);
		calculated.push('Cost of Revenue');
	}
	
	// Show notification if fields were calculated
	if (calculated.length > 0 && !frm.is_new()) {
		frappe.show_alert({
			message: __('Auto-calculated: {0}', [calculated.join(', ')]),
			indicator: 'blue'
		}, 3);
	}
}
