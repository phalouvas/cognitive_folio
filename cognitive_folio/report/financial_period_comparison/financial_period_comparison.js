// Client-side enhancements for Financial Period Comparison Report

frappe.query_reports["Financial Period Comparison"] = {
	"filters": [
		{
			"fieldname": "security",
			"label": __("Security"),
			"fieldtype": "Link",
			"options": "CF Security",
			"reqd": 0
		},
		{
			"fieldname": "period_type",
			"label": __("Period Type"),
			"fieldtype": "Select",
			"options": "Annual\nQuarterly",
			"default": "Annual",
			"reqd": 1
		},
		{
			"fieldname": "num_periods",
			"label": __("Number of Periods"),
			"fieldtype": "Int",
			"default": 5,
			"reqd": 1
		}
	],

	"formatter": function(value, field, data) {
		// Format currency fields
		if (["revenue", "net_income", "free_cash_flow"].includes(field.fieldname) && value) {
			return format_currency(value, data.currency || "USD");
		}

		// Format percentage fields
		if (["revenue_growth", "net_income_growth", "gross_margin", "operating_margin", "roe", "fcf_growth"].includes(field.fieldname) && value !== null) {
			let color = value > 0 ? "green" : value < 0 ? "red" : "black";
			return `<span style="color: ${color};">${(value * 100).toFixed(1)}%</span>`;
		}

		return value;
	},

	"onload": function(report) {
		// Add export button for Excel with charts
		report.page.add_inner_button(__("Export with Charts"), function() {
			export_with_charts(report);
		});

		// Add drill-down to period form
		report.page.add_inner_button(__("View Period Details"), function() {
			let selected_row = report.datatable.get_selected_rows();
			if (selected_row.length === 0) {
				frappe.msgprint(__("Please select a row to view period details"));
				return;
			}

			let row_data = report.data[selected_row[0]];
			if (row_data && row_data.name) {
				frappe.set_route("Form", "CF Financial Period", row_data.name);
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

function export_with_charts(report) {
	// Placeholder for Excel export with embedded charts
	// Would require additional libraries like xlsx or similar
	frappe.msgprint(__("Excel export with charts feature coming soon"));
}