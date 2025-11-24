// Client-side enhancements for Security Comparison Report

frappe.query_reports["Security Comparison"] = {
	"filters": [
		{
			"fieldname": "sector",
			"label": __("Sector"),
			"fieldtype": "Link",
			"options": "Sector",
			"reqd": 0
		},
		{
			"fieldname": "region",
			"label": __("Region"),
			"fieldtype": "Select",
			"options": "North America\nEurope\nAsia\nOther",
			"reqd": 0
		},
		{
			"fieldname": "min_market_cap",
			"label": __("Min Market Cap"),
			"fieldtype": "Currency",
			"reqd": 0
		},
		{
			"fieldname": "max_market_cap",
			"label": __("Max Market Cap"),
			"fieldtype": "Currency",
			"reqd": 0
		},
		{
			"fieldname": "period_type",
			"label": __("Period Type"),
			"fieldtype": "Select",
			"options": "Annual\nQuarterly",
			"default": "Annual",
			"reqd": 1
		}
	],

	"formatter": function(value, field, data) {
		// Format currency fields
		if (["revenue", "net_income", "free_cash_flow", "market_cap"].includes(field.fieldname) && value) {
			return format_currency(value, data.currency || "USD");
		}

		// Format percentage fields
		if (["revenue_growth", "gross_margin", "operating_margin", "roe", "roa"].includes(field.fieldname) && value !== null) {
			let color = value > 0 ? "green" : value < 0 ? "red" : "black";
			return `<span style="color: ${color};">${(value * 100).toFixed(1)}%</span>`;
		}

		// Highlight sector averages
		if (data.security && data.security.includes("Average")) {
			return `<b>${value}</b>`;
		}

		return value;
	},

	"onload": function(report) {
		// Add "Add to Portfolio" button
		report.page.add_inner_button(__("Add to Portfolio"), function() {
			let selected_rows = report.datatable.get_selected_rows();
			if (selected_rows.length === 0) {
				frappe.msgprint(__("Please select securities to add to portfolio"));
				return;
			}

			// Show portfolio selection dialog
			let dialog = new frappe.ui.Dialog({
				title: __('Add Securities to Portfolio'),
				fields: [
					{
						label: __('Target Portfolio'),
						fieldname: 'target_portfolio',
						fieldtype: 'Link',
						options: 'CF Portfolio',
						reqd: 1
					},
					{
						label: __('Default Quantity'),
						fieldname: 'quantity',
						fieldtype: 'Int',
						default: 1,
						reqd: 1
					}
				],
				primary_action_label: __('Add to Portfolio'),
				primary_action(values) {
					let securities = selected_rows.map(idx => report.data[idx].security);
					add_to_portfolio(securities, values.target_portfolio, values.quantity);
					dialog.hide();
				}
			});
			dialog.show();
		});

		// Add drill-down to security form
		report.page.add_inner_button(__("View Security Details"), function() {
			let selected_row = report.datatable.get_selected_rows();
			if (selected_row.length === 0) {
				frappe.msgprint(__("Please select a security to view details"));
				return;
			}

			let row_data = report.data[selected_row[0]];
			if (row_data && row_data.security && !row_data.security.includes("Average")) {
				frappe.set_route("Form", "CF Security", row_data.security);
			}
		});
	}
};

function format_currency(value, currency) {
	if (!value) return "";
	let currency_symbols = { 'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥' };
	let symbol = currency_symbols[currency] || currency;
	return `${symbol}${Number(value).toLocaleString()}`;
}

function add_to_portfolio(securities, portfolio, quantity) {
	frappe.call({
		method: "cognitive_folio.cognitive_folio.doctype.cf_portfolio_holding.cf_portfolio_holding.add_securities_to_portfolio",
		args: {
			securities: securities,
			portfolio: portfolio,
			quantity: quantity
		},
		callback: function(r) {
			if (!r.exc) {
				frappe.show_alert({
					message: __('Securities added to portfolio successfully'),
					indicator: 'green'
				});
			}
		}
	});
}