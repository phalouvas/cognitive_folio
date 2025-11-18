import frappe
from frappe import _
from frappe.utils import flt, cstr, cint
import json


def execute(filters=None):
	"""Return columns and data for Financial Period Comparison Report"""
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns():
	"""Define report columns"""
	return [
		{
			"fieldname": "security",
			"label": _("Security"),
			"fieldtype": "Link",
			"options": "CF Security",
			"width": 120
		},
		{
			"fieldname": "period",
			"label": _("Period"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "revenue",
			"label": _("Revenue"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "revenue_growth",
			"label": _("Revenue Growth %"),
			"fieldtype": "Percent",
			"width": 120
		},
		{
			"fieldname": "net_income",
			"label": _("Net Income"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "net_income_growth",
			"label": _("Net Income Growth %"),
			"fieldtype": "Percent",
			"width": 120
		},
		{
			"fieldname": "eps",
			"label": _("EPS"),
			"fieldtype": "Float",
			"width": 80
		},
		{
			"fieldname": "gross_margin",
			"label": _("Gross Margin %"),
			"fieldtype": "Percent",
			"width": 120
		},
		{
			"fieldname": "operating_margin",
			"label": _("Operating Margin %"),
			"fieldtype": "Percent",
			"width": 120
		},
		{
			"fieldname": "roe",
			"label": _("ROE %"),
			"fieldtype": "Percent",
			"width": 80
		},
		{
			"fieldname": "free_cash_flow",
			"label": _("Free Cash Flow"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "fcf_growth",
			"label": _("FCF Growth %"),
			"fieldtype": "Percent",
			"width": 120
		},
		{
			"fieldname": "sparkline",
			"label": _("Trend"),
			"fieldtype": "HTML",
			"width": 200
		}
	]


def get_data(filters):
	"""Fetch and process data for the report"""
	security = filters.get("security")
	period_type = filters.get("period_type", "Annual")
	num_periods = cint(filters.get("num_periods", 5))

	# Build query
	query_filters = {"period_type": period_type}
	if security:
		query_filters["security"] = security

	# Get periods ordered by fiscal_year desc, fiscal_quarter desc
	periods = frappe.get_all(
		"CF Financial Period",
		filters=query_filters,
		fields=[
			"name", "security", "fiscal_year", "fiscal_quarter", "period_type",
			"total_revenue", "net_income", "diluted_eps", "gross_margin",
			"operating_margin", "roe", "free_cash_flow",
			"revenue_growth_yoy", "net_income_growth_yoy", "eps_growth_yoy", "fcf_growth_yoy"
		],
		order_by="security, fiscal_year DESC, fiscal_quarter DESC",
		limit=num_periods * 100  # Get enough for grouping
	)

	# Group by security and limit to num_periods per security
	security_periods = {}
	for period in periods:
		sec = period.security
		if sec not in security_periods:
			security_periods[sec] = []
		if len(security_periods[sec]) < num_periods:
			security_periods[sec].append(period)

	# Process data
	data = []
	for sec, periods_list in security_periods.items():
		# Sort periods chronologically for sparkline
		sorted_periods = sorted(periods_list, key=lambda x: (x.fiscal_year, x.fiscal_quarter or 0))

		# Generate sparkline data
		revenue_values = [p.total_revenue or 0 for p in sorted_periods]
		net_income_values = [p.net_income or 0 for p in sorted_periods]
		sparkline_html = generate_sparkline(revenue_values, net_income_values)

		# Add rows for each period
		for period in periods_list:
			row = {
				"security": sec,
				"period": f"{period.fiscal_year}{' Q' + str(period.fiscal_quarter) if period.fiscal_quarter else ''}",
				"revenue": period.total_revenue,
				"revenue_growth": period.revenue_growth_yoy,
				"net_income": period.net_income,
				"net_income_growth": period.net_income_growth_yoy,
				"eps": period.diluted_eps,
				"gross_margin": period.gross_margin,
				"operating_margin": period.operating_margin,
				"roe": period.roe,
				"free_cash_flow": period.free_cash_flow,
				"fcf_growth": period.fcf_growth_yoy,
				"sparkline": sparkline_html if periods_list.index(period) == 0 else ""  # Only show sparkline on first row per security
			}
			data.append(row)

	return data


def generate_sparkline(revenue_values, net_income_values):
	"""Generate HTML sparkline chart"""
	if not revenue_values or len(revenue_values) < 2:
		return ""

	# Normalize values to 0-100 range for sparkline
	def normalize(values):
		if not values:
			return []
		min_val = min(values)
		max_val = max(values)
		if max_val == min_val:
			return [50] * len(values)
		return [((v - min_val) / (max_val - min_val)) * 100 for v in values]

	revenue_norm = normalize(revenue_values)
	net_income_norm = normalize(net_income_values)

	# Create SVG sparkline
	points_revenue = " ".join([f"{i*20},{100-v}" for i, v in enumerate(revenue_norm)])
	points_net = " ".join([f"{i*20},{100-v}" for i, v in enumerate(net_income_norm)])

	html = f"""
	<div style="display: flex; align-items: center; gap: 10px;">
		<svg width="100" height="30" style="border: 1px solid #ddd;">
			<polyline points="{points_revenue}" fill="none" stroke="#007bff" stroke-width="2"/>
			<polyline points="{points_net}" fill="none" stroke="#28a745" stroke-width="2"/>
		</svg>
		<div style="font-size: 10px; color: #666;">
			<div style="color: #007bff;">Revenue</div>
			<div style="color: #28a745;">Net Income</div>
		</div>
	</div>
	"""

	return html


def get_filters():
	"""Define report filters"""
	return [
		{
			"fieldname": "security",
			"label": _("Security"),
			"fieldtype": "Link",
			"options": "CF Security",
			"reqd": 0
		},
		{
			"fieldname": "period_type",
			"label": _("Period Type"),
			"fieldtype": "Select",
			"options": "Annual\nQuarterly",
			"default": "Annual",
			"reqd": 1
		},
		{
			"fieldname": "num_periods",
			"label": _("Number of Periods"),
			"fieldtype": "Int",
			"default": 5,
			"reqd": 1
		}
	]