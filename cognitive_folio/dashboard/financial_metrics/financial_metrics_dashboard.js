// Financial Metrics Dashboard

frappe.pages['financial-metrics-dashboard'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Financial Metrics Dashboard',
		single_column: true
	});

	// Add filters
	page.add_inner_button(__('Refresh'), () => load_dashboard());

	let security_filter = page.add_field({
		label: 'Security',
		fieldtype: 'Link',
		options: 'CF Security',
		fieldname: 'security',
		reqd: 1,
		change: () => load_dashboard()
	});

	let period_filter = page.add_field({
		label: 'Period Type',
		fieldtype: 'Select',
		options: 'Annual\nQuarterly',
		fieldname: 'period_type',
		default: 'Annual',
		change: () => load_dashboard()
	});

	let years_filter = page.add_field({
		label: 'Years',
		fieldtype: 'Select',
		options: '1\n3\n5\nAll',
		fieldname: 'years',
		default: '5',
		change: () => load_dashboard()
	});

	// Dashboard container
	let dashboard_html = `
		<div class="dashboard-container">
			<div class="row">
				<div class="col-md-6">
					<div class="chart-container" id="revenue-trend-chart"></div>
				</div>
				<div class="col-md-6">
					<div class="chart-container" id="margin-trends-chart"></div>
				</div>
			</div>
			<div class="row">
				<div class="col-md-6">
					<div class="chart-container" id="cash-flow-trend-chart"></div>
				</div>
				<div class="col-md-6">
					<div class="chart-container" id="quarterly-comparison-chart"></div>
				</div>
			</div>
			<div class="row">
				<div class="col-md-6">
					<div class="chart-container" id="yoy-growth-chart"></div>
				</div>
				<div class="col-md-6">
					<div class="ratios-container" id="ratios-gauges"></div>
				</div>
			</div>
		</div>
	`;

	page.main.html(dashboard_html);

	function load_dashboard() {
		let security = security_filter.get_value();
		let period_type = period_filter.get_value();
		let years = years_filter.get_value();

		if (!security) return;

		// Load all charts
		load_revenue_trend(security, period_type, years);
		load_margin_trends(security, period_type, years);
		load_cash_flow_trend(security, period_type, years);
		load_quarterly_comparison(security, period_type);
		load_yoy_growth(security, period_type, years);
		load_ratios_gauges(security, period_type);
	}

	function load_revenue_trend(security, period_type, years) {
		frappe.call({
			method: 'cognitive_folio.cognitive_folio.dashboard.financial_metrics.financial_metrics_dashboard.get_revenue_trend',
			args: { security, period_type, years },
			callback: (r) => {
				if (r.message) {
					new frappe.Chart("#revenue-trend-chart", {
						title: "Revenue Trend",
						data: r.message,
						type: 'line',
						height: 300
					});
				}
			}
		});
	}

	function load_margin_trends(security, period_type, years) {
		frappe.call({
			method: 'cognitive_folio.cognitive_folio.dashboard.financial_metrics.financial_metrics_dashboard.get_margin_trends',
			args: { security, period_type, years },
			callback: (r) => {
				if (r.message) {
					new frappe.Chart("#margin-trends-chart", {
						title: "Margin Trends (%)",
						data: r.message,
						type: 'line',
						height: 300
					});
				}
			}
		});
	}

	function load_cash_flow_trend(security, period_type, years) {
		frappe.call({
			method: 'cognitive_folio.cognitive_folio.dashboard.financial_metrics.financial_metrics_dashboard.get_cash_flow_trend',
			args: { security, period_type, years },
			callback: (r) => {
				if (r.message) {
					new frappe.Chart("#cash-flow-trend-chart", {
						title: "Cash Flow Trend",
						data: r.message,
						type: 'line',
						height: 300
					});
				}
			}
		});
	}

	function load_quarterly_comparison(security, period_type) {
		let current_year = new Date().getFullYear();
		frappe.call({
			method: 'cognitive_folio.cognitive_folio.dashboard.financial_metrics.financial_metrics_dashboard.get_quarterly_comparison',
			args: { security, fiscal_year: current_year },
			callback: (r) => {
				if (r.message) {
					new frappe.Chart("#quarterly-comparison-chart", {
						title: `Quarterly Comparison ${current_year}`,
						data: r.message,
						type: 'bar',
						height: 300
					});
				}
			}
		});
	}

	function load_yoy_growth(security, period_type, years) {
		frappe.call({
			method: 'cognitive_folio.cognitive_folio.dashboard.financial_metrics.financial_metrics_dashboard.get_yoy_growth_rates',
			args: { security, period_type, years },
			callback: (r) => {
				if (r.message) {
					new frappe.Chart("#yoy-growth-chart", {
						title: "YoY Growth Rates (%)",
						data: r.message,
						type: 'bar',
						height: 300
					});
				}
			}
		});
	}

	function load_ratios_gauges(security, period_type) {
		frappe.call({
			method: 'cognitive_folio.cognitive_folio.dashboard.financial_metrics.financial_metrics_dashboard.get_financial_ratios',
			args: { security, period_type },
			callback: (r) => {
				if (r.message) {
					let ratios = r.message;
					let html = '<h4>Financial Ratios</h4>';
					Object.keys(ratios).forEach(ratio => {
						let value = ratios[ratio];
						let color = get_ratio_color(ratio, value);
						html += `
							<div class="ratio-gauge">
								<div class="ratio-label">${ratio}</div>
								<div class="ratio-value" style="color: ${color}">${value.toFixed(2)}</div>
							</div>
						`;
					});
					$('#ratios-gauges').html(html);
				}
			}
		});
	}

	function get_ratio_color(ratio, value) {
		// Simple color coding for ratios
		if (ratio.includes('ROE') || ratio.includes('ROA')) {
			return value > 10 ? 'green' : value > 5 ? 'orange' : 'red';
		}
		if (ratio.includes('Current Ratio')) {
			return value > 1.5 ? 'green' : value > 1 ? 'orange' : 'red';
		}
		if (ratio.includes('Debt/Equity')) {
			return value < 1 ? 'green' : value < 2 ? 'orange' : 'red';
		}
		return 'black';
	}

	// Initial load if security is set
	if (security_filter.get_value()) {
		load_dashboard();
	}
};