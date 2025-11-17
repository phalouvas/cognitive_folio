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
			
			// Add comparison button
			frm.add_custom_button(__('Compare Periods'), function() {
				frappe.set_route('query-report', 'Financial Period Comparison', {
					security: frm.doc.security
				});
			});
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
