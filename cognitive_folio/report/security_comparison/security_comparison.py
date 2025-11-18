import frappe
from frappe import _
from frappe.utils import flt, cstr, cint
import json


def execute(filters=None):
	"""Return columns and data for Security Comparison Report"""
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
			"fieldname": "sector",
			"label": _("Sector"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "latest_period",
			"label": _("Latest Period"),
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
			"width": 100
		},
		{
			"fieldname": "roa",
			"label": _("ROA %"),
			"fieldtype": "Percent",
			"width": 100
		},
		{
			"fieldname": "debt_to_equity",
			"label": _("Debt/Equity"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "current_ratio",
			"label": _("Current Ratio"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "free_cash_flow",
			"label": _("Free Cash Flow"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "market_cap",
			"label": _("Market Cap"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "pe_ratio",
			"label": _("P/E Ratio"),
			"fieldtype": "Float",
			"width": 100
		}
	]


def get_data(filters):
	"""Fetch and process data for the report"""
	sector = filters.get("sector")
	region = filters.get("region")
	min_market_cap = flt(filters.get("min_market_cap"))
	max_market_cap = flt(filters.get("max_market_cap"))
	period_type = filters.get("period_type", "Annual")

	# Get securities with filters
	security_filters = {}
	if sector:
		security_filters["sector"] = sector
	if region:
		security_filters["region"] = region

	securities = frappe.get_all(
		"CF Security",
		filters=security_filters,
		fields=["name", "sector", "region", "currency", "market_cap"]
	)

	data = []
	for security in securities:
		# Skip if market cap filter doesn't match
		if min_market_cap and (security.market_cap or 0) < min_market_cap:
			continue
		if max_market_cap and (security.market_cap or 0) > max_market_cap:
			continue

		# Get latest period data
		latest_period = frappe.get_all(
			"CF Financial Period",
			filters={
				"security": security.name,
				"period_type": period_type
			},
			fields=[
				"name", "fiscal_year", "fiscal_quarter", "total_revenue", "net_income",
				"gross_margin", "operating_margin", "roe", "roa", "debt_to_equity",
				"current_ratio", "free_cash_flow", "revenue_growth_yoy"
			],
			order_by="fiscal_year DESC, fiscal_quarter DESC",
			limit=1
		)

		if latest_period:
			period = latest_period[0]
			period_label = f"{period.fiscal_year}{' Q' + str(period.fiscal_quarter) if period.fiscal_quarter else ''}"

			# Calculate P/E ratio (simplified: market_cap / net_income)
			pe_ratio = None
			if period.net_income and period.net_income > 0 and security.market_cap:
				pe_ratio = security.market_cap / period.net_income

			row = {
				"security": security.name,
				"sector": security.sector,
				"latest_period": period_label,
				"revenue": period.total_revenue,
				"revenue_growth": period.revenue_growth_yoy,
				"net_income": period.net_income,
				"gross_margin": period.gross_margin,
				"operating_margin": period.operating_margin,
				"roe": period.roe,
				"roa": period.roa,
				"debt_to_equity": period.debt_to_equity,
				"current_ratio": period.current_ratio,
				"free_cash_flow": period.free_cash_flow,
				"market_cap": security.market_cap,
				"pe_ratio": pe_ratio
			}
			data.append(row)

	# Add sector averages row if multiple securities
	if len(data) > 1:
		sector_avg = calculate_sector_averages(data)
		if sector_avg:
			data.append(sector_avg)

	return data


def calculate_sector_averages(data):
	"""Calculate sector averages for comparison"""
	if not data:
		return None

	# Group by sector
	sector_groups = {}
	for row in data:
		sector = row.get("sector") or "Unknown"
		if sector not in sector_groups:
			sector_groups[sector] = []
		sector_groups[sector].append(row)

	# Calculate averages for each sector
	avg_rows = []
	for sector, rows in sector_groups.items():
		if len(rows) < 2:  # Skip sectors with only one security
			continue

		avg_row = {
			"security": f"<b>{sector} Average</b>",
			"sector": sector,
			"latest_period": "N/A"
		}

		# Calculate averages for numeric fields
		numeric_fields = [
			"revenue", "revenue_growth", "net_income", "gross_margin", "operating_margin",
			"roe", "roa", "debt_to_equity", "current_ratio", "free_cash_flow", "market_cap", "pe_ratio"
		]

		for field in numeric_fields:
			values = [r[field] for r in rows if r.get(field) is not None]
			if values:
				avg_row[field] = sum(values) / len(values)

		avg_rows.append(avg_row)

	return avg_rows[0] if avg_rows else None


def get_filters():
	"""Define report filters"""
	return [
		{
			"fieldname": "sector",
			"label": _("Sector"),
			"fieldtype": "Link",
			"options": "Sector",  # Assuming Sector doctype exists
			"reqd": 0
		},
		{
			"fieldname": "region",
			"label": _("Region"),
			"fieldtype": "Select",
			"options": "North America\nEurope\nAsia\nOther",
			"reqd": 0
		},
		{
			"fieldname": "min_market_cap",
			"label": _("Min Market Cap"),
			"fieldtype": "Currency",
			"reqd": 0
		},
		{
			"fieldname": "max_market_cap",
			"label": _("Max Market Cap"),
			"fieldtype": "Currency",
			"reqd": 0
		},
		{
			"fieldname": "period_type",
			"label": _("Period Type"),
			"fieldtype": "Select",
			"options": "Annual\nQuarterly",
			"default": "Annual",
			"reqd": 1
		}
	]