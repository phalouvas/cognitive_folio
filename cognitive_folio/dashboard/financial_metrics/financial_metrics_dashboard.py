import frappe
from frappe import _
from frappe.utils import cint, flt
import json


@frappe.whitelist()
def get_revenue_trend(security=None, period_type="Annual", years=5):
	"""Get revenue trend data for chart"""
	if not security:
		return {"labels": [], "datasets": []}

	periods = frappe.get_all(
		"CF Financial Period",
		filters={
			"security": security,
			"period_type": period_type
		},
		fields=["fiscal_year", "fiscal_quarter", "total_revenue"],
		order_by="fiscal_year DESC, fiscal_quarter DESC",
		limit=cint(years) * 4  # Allow for quarterly data
	)

	# Group and sort chronologically
	data_points = {}
	for p in periods:
		key = f"{p.fiscal_year}{' Q' + str(p.fiscal_quarter) if p.fiscal_quarter else ''}"
		data_points[key] = p.total_revenue

	labels = sorted(data_points.keys())
	values = [data_points[label] for label in labels]

	return {
		"labels": labels,
		"datasets": [{
			"name": "Revenue",
			"values": values
		}]
	}


@frappe.whitelist()
def get_margin_trends(security=None, period_type="Annual", years=5):
	"""Get margin trends data for chart"""
	if not security:
		return {"labels": [], "datasets": []}

	periods = frappe.get_all(
		"CF Financial Period",
		filters={
			"security": security,
			"period_type": period_type
		},
		fields=["fiscal_year", "fiscal_quarter", "gross_margin", "operating_margin", "net_margin"],
		order_by="fiscal_year DESC, fiscal_quarter DESC",
		limit=cint(years) * 4
	)

	data_points = {}
	for p in periods:
		key = f"{p.fiscal_year}{' Q' + str(p.fiscal_quarter) if p.fiscal_quarter else ''}"
		data_points[key] = {
			"gross": p.gross_margin or 0,
			"operating": p.operating_margin or 0,
			"net": p.net_margin or 0
		}

	labels = sorted(data_points.keys())
	gross_values = [data_points[label]["gross"] for label in labels]
	operating_values = [data_points[label]["operating"] for label in labels]
	net_values = [data_points[label]["net"] for label in labels]

	return {
		"labels": labels,
		"datasets": [
			{"name": "Gross Margin %", "values": gross_values},
			{"name": "Operating Margin %", "values": operating_values},
			{"name": "Net Margin %", "values": net_values}
		]
	}


@frappe.whitelist()
def get_cash_flow_trend(security=None, period_type="Annual", years=5):
	"""Get cash flow trend data for chart"""
	if not security:
		return {"labels": [], "datasets": []}

	periods = frappe.get_all(
		"CF Financial Period",
		filters={
			"security": security,
			"period_type": period_type
		},
		fields=["fiscal_year", "fiscal_quarter", "operating_cash_flow", "free_cash_flow"],
		order_by="fiscal_year DESC, fiscal_quarter DESC",
		limit=cint(years) * 4
	)

	data_points = {}
	for p in periods:
		key = f"{p.fiscal_year}{' Q' + str(p.fiscal_quarter) if p.fiscal_quarter else ''}"
		data_points[key] = {
			"operating": p.operating_cash_flow or 0,
			"free": p.free_cash_flow or 0
		}

	labels = sorted(data_points.keys())
	operating_values = [data_points[label]["operating"] for label in labels]
	free_values = [data_points[label]["free"] for label in labels]

	return {
		"labels": labels,
		"datasets": [
			{"name": "Operating Cash Flow", "values": operating_values},
			{"name": "Free Cash Flow", "values": free_values}
		]
	}


@frappe.whitelist()
def get_quarterly_comparison(security=None, fiscal_year=None):
	"""Get quarterly comparison data for current year"""
	if not security or not fiscal_year:
		return {"labels": [], "datasets": []}

	periods = frappe.get_all(
		"CF Financial Period",
		filters={
			"security": security,
			"period_type": "Quarterly",
			"fiscal_year": cint(fiscal_year)
		},
		fields=["fiscal_quarter", "total_revenue", "net_income"],
		order_by="fiscal_quarter"
	)

	labels = []
	revenue_values = []
	net_income_values = []

	for p in periods:
		labels.append(f"Q{p.fiscal_quarter}")
		revenue_values.append(p.total_revenue or 0)
		net_income_values.append(p.net_income or 0)

	return {
		"labels": labels,
		"datasets": [
			{"name": "Revenue", "values": revenue_values},
			{"name": "Net Income", "values": net_income_values}
		]
	}


@frappe.whitelist()
def get_yoy_growth_rates(security=None, period_type="Annual", years=5):
	"""Get YoY growth rates for chart"""
	if not security:
		return {"labels": [], "datasets": []}

	periods = frappe.get_all(
		"CF Financial Period",
		filters={
			"security": security,
			"period_type": period_type
		},
		fields=["fiscal_year", "fiscal_quarter", "revenue_growth_yoy", "net_income_growth_yoy", "eps_growth_yoy"],
		order_by="fiscal_year DESC, fiscal_quarter DESC",
		limit=cint(years) * 4
	)

	data_points = {}
	for p in periods:
		key = f"{p.fiscal_year}{' Q' + str(p.fiscal_quarter) if p.fiscal_quarter else ''}"
		data_points[key] = {
			"revenue": (p.revenue_growth_yoy or 0) * 100,
			"net_income": (p.net_income_growth_yoy or 0) * 100,
			"eps": (p.eps_growth_yoy or 0) * 100
		}

	labels = sorted(data_points.keys())
	revenue_growth = [data_points[label]["revenue"] for label in labels]
	net_income_growth = [data_points[label]["net_income"] for label in labels]
	eps_growth = [data_points[label]["eps"] for label in labels]

	return {
		"labels": labels,
		"datasets": [
			{"name": "Revenue Growth %", "values": revenue_growth},
			{"name": "Net Income Growth %", "values": net_income_growth},
			{"name": "EPS Growth %", "values": eps_growth}
		]
	}


@frappe.whitelist()
def get_financial_ratios(security=None, period_type="Annual"):
	"""Get current financial ratios for gauge charts"""
	if not security:
		return {}

	latest_period = frappe.get_all(
		"CF Financial Period",
		filters={
			"security": security,
			"period_type": period_type
		},
		fields=["roe", "roa", "current_ratio", "debt_to_equity"],
		order_by="fiscal_year DESC, fiscal_quarter DESC",
		limit=1
	)

	if not latest_period:
		return {}

	period = latest_period[0]
	return {
		"ROE": period.roe or 0,
		"ROA": period.roa or 0,
		"Current Ratio": period.current_ratio or 0,
		"Debt/Equity": period.debt_to_equity or 0
	}