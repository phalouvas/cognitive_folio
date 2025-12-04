"""
SEC Edgar Financial Data Fetcher using edgartools

This module fetches financial statements from SEC Edgar using the edgartools library.
Provides higher quality data (95% accuracy) compared to Yahoo Finance (85% accuracy).

Uses edgartools to automatically parse 10-Q/10-K filings and extract standardized
financial data into CF Financial Period records.
"""

import frappe
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd

# Base GAAP tag coverage used across all sectors. These mirror the previous
# hard-coded lists but live centrally so sector overrides can extend them.
BASE_METRIC_TAGS: Dict[str, List[str]] = {
	'total_revenue': [
		'Revenue', 'Revenues', 'Total Revenue', 'Total Revenues',
		'Revenue from Contract with Customer Excluding Assessed Tax',
		'Revenue from Contract with Customer Including Assessed Tax',
		'Sales Revenue Net', 'Sales Revenue Goods Net', 'Sales Revenue Services Net',
		'Operating Revenue', 'Operating Revenues', 'Revenues Net of Interest Expense', 'Net Sales'
	],
	'cost_of_revenue': [
		'Cost of Revenue', 'Cost Of Revenue', 'Cost of Goods Sold', 'Cost of Goods And Services Sold',
		'Cost Of Sales', 'Cost Of Goods Sold Excluding Depreciation Depletion And Amortization'
	],
	'gross_profit': ['Gross Profit', 'Gross Margin'],
	'operating_expenses': [
		'Operating Expenses', 'Total Operating Expenses', 'Operating And Maintenance Expense',
		'Operating Costs and Expenses', 'Selling General and Administrative Expense',
		'Research and Development Expense'
	],
	'operating_income': [
		'Operating Income', 'Income from Operations', 'Operating Profit',
		'OperatingIncomeLoss', 'IncomeLossFromOperations'
	],
	'ebit': [
		'Earnings Before Interest and Taxes',
		'Earnings Before Interest and Tax',
		'Earnings Before Interest Income Expense and Income Taxes',
		'Earnings Before Income Taxes and Minority Interest',
		'Earnings Before Interest Taxes',
		'EBIT'
	],
	'ebitda': [
		'Earnings Before Interest Taxes Depreciation and Amortization',
		'Earnings Before Interest Taxes Depreciation Amortization and Extraordinary Items',
		'EBITDA',
		'Earnings Before Interest Taxes Depreciation Amortization',
		'Earnings Before Interest Taxes Depreciation and Amortization (EBITDA)'
	],
	'net_income': [
		'Net Income', 'Net Income Loss', 'Net Income Attributable to Common Stockholders', 'Net Earnings'
	],
	'interest_expense': ['Interest Expense', 'Interest Paid', 'Interest Expense Debt'],
	'tax_provision': [
		'Income Tax Expense', 'Provision for Income Taxes', 'Income Taxes', 'Tax Expense', 'Tax Provision'
	],
	'pretax_income': [
		'Income Before Tax', 'Pretax Income', 'Income Before Income Taxes', 'Earnings Before Tax'
	],
	'total_costs_and_expenses': [
		'Costs and Expenses', 'Total Costs and Expenses', 'Operating Costs and Expenses'
	],
	'basic_eps': [
		'Earnings Per Share Basic',
		'Earnings Per Share (Basic)',
		'Basic Earnings Per Share',
		'Basic EPS',
		'Earnings per share, basic'
	],
	'diluted_eps': [
		'Earnings Per Share Diluted',
		'Earnings Per Share (Diluted)',
		'Diluted Earnings Per Share',
		'Diluted EPS',
		'Earnings per share, diluted'
	],
	'shares_outstanding': [
		'Weighted Average Shares',
		'Weighted Average Number of Shares Outstanding Basic',
		'Weighted Average Basic Shares Outstanding',
		'Common Stock Shares Outstanding',
		'Weighted Average Number of Diluted Shares Outstanding',
		'Weighted Average Diluted Shares Outstanding'
	],
	'total_assets': ['Total Assets', 'Assets'],
	'total_liabilities': ['Total Liabilities', 'Liabilities'],
	'shareholders_equity': [
		"Total Stockholders' Equity", "Stockholders' Equity", "Shareholders' Equity", 'Total Equity'
	],
	'current_assets': ['Total Current Assets', 'Current Assets', 'Assets Current'],
	'current_liabilities': ['Total Current Liabilities', 'Current Liabilities', 'Liabilities Current'],
	'cash_and_equivalents': ['Cash and Cash Equivalents', 'Cash', 'Cash and Equivalents'],
	'accounts_receivable': ['Accounts Receivable', 'Accounts Receivable Net', 'Receivables Net'],
	'inventory': ['Inventory', 'Inventory Net'],
	'long_term_debt': ['Long-term Debt', 'Long Term Debt Noncurrent', 'Long-Term Debt', 'Debt Noncurrent'],
	'total_debt': ['Total Debt', 'Debt', 'Total Borrowings'],
	'retained_earnings': ['Retained Earnings', 'Retained Earnings Accumulated Deficit'],
	'depreciation': [
		'Depreciation and Amortization',
		'DepreciationDepletionAndAmortization',
		'Depreciation Amortization and Accretion',
		'Depreciation And Amortization',
		'Depreciation'
	],
	'operating_cash_flow': [
		'Net Cash Provided by (Used in) Operating Activities',
		'Net Cash Provided by Used in Operating Activities',
		'Net Cash Provided by (Used in) Operating Activities Continuing Operations',
		'Net Cash Provided by Used in Operating Activities Continuing Operations',
		'Net Cash from Operating Activities',
		'Operating Cash Flow'
	],
	'capital_expenditures': [
		'Capital Expenditures',
		'Payments to Acquire Property Plant and Equipment',
		'Payments for Property Plant and Equipment',
		'Purchase of Property and Equipment',
		'Capital Expenditures and Acquisitions'
	],
	'investing_cash_flow': [
		'Net Cash Provided by (Used in) Investing Activities',
		'Net Cash from Investing Activities',
		'Net Cash Provided by Used in Investing Activities'
	],
	'financing_cash_flow': [
		'Net Cash Provided by (Used in) Financing Activities',
		'Net Cash from Financing Activities',
		'Net Cash Provided by Used in Financing Activities'
	],
	'dividends_paid': [
		'Payments of Dividends',
		'Common Stock Dividends Paid',
		'Cash Dividends Paid'
	]
}

# Sector-specific aliases that extend the base tags without replacing them. These
# reflect the mapping plan documented in the contributor instructions.
SECTOR_TAG_OVERRIDES: Dict[str, Dict[str, List[str]]] = {
	'banks': {
		'total_revenue': [
			'Net Interest Income',
			'Interest Income',
			'Total Interest Income',
			'Net Interest Income After Provision for Credit Losses',
			'Noninterest Income',
			'Total Noninterest Income',
			'Net Revenues'
		],
		'cost_of_revenue': ['Provision for Credit Losses', 'Provision for Loan Losses'],
		'operating_expenses': [
			'Noninterest Expense',
			'Noninterest Expenses',
			'Provision for Credit Losses',
			'Provision for Loan Losses'
		],
		'operating_income': [
			'Income Before Income Taxes and Noncontrolling Interests',
			'Income Before Provision for Income Taxes'
		],
		'pretax_income': [
			'Income Before Provision for Income Taxes',
			'Income Before Income Taxes and Minority Interest'
		],
		'interest_expense': [
			'Interest Expense Deposits',
			'Interest Expense Borrowings',
			'Interest Expense Short-term Borrowings'
		]
	},
	'insurance': {
		'total_revenue': [
			'Premiums Earned',
			'Net Premiums Earned',
			'Policy Premiums Earned'
		],
		'operating_expenses': [
			'Benefits Losses and Loss Adjustment Expenses',
			'Policyholder Benefits And Claims Incurred',
			'Insurance Underwriting Expense'
		],
		'cost_of_revenue': ['Policyholder Benefits And Claims'],
		'operating_income': ['Underwriting Income', 'Income from Insurance Operations']
	},
	'energy': {
		'total_revenue': [
			'Sales and Other Operating Revenues',
			'Net Sales and Operating Revenues',
			'Oil and Gas Sales'
		],
		'cost_of_revenue': [
			'Production and Manufacturing Expenses',
			'Upstream Operating Expenses',
			'Exploration Expense'
		],
		'capital_expenditures': ['Capital Expenditures for Exploration and Production', 'Development Costs']
	},
	'utilities': {
		'total_revenue': [
			'Utility Operating Revenues',
			'Electric Operating Revenues',
			'Gas Operating Revenues'
		],
		'operating_expenses': ['Operation and Maintenance Expense', 'Transmission and Distribution Expense']
	},
	'reit': {
		'operating_income': ['Net Operating Income', 'Funds From Operations'],
		'operating_cash_flow': ['Funds From Operations', 'Adjusted Funds From Operations'],
		'total_revenue': ['Rental Revenue', 'Property Revenue']
	}
}


def _determine_sector_profile(security) -> List[str]:
	"""Return ordered sector profile tokens for tag selection."""
	profiles = ['general']
	try:
		if getattr(security, 'security_type', 'Stock') != 'Stock':
			return profiles
		sector = (security.sector or '').lower()
		industry = (security.industry or '').lower()
		name = (security.security_name or '').lower()
		if _matches_any([sector, industry], ['bank', 'banks', 'diversified financial', 'capital markets']):
			return ['banks', 'general']
		if _matches_any([sector, industry], ['insurance', 'insurers', 'reinsurance']):
			return ['insurance', 'general']
		if _matches_any([sector, industry, name], ['reit', 'real estate investment trust']):
			return ['reit', 'general']
		if _matches_any([sector, industry], ['utility', 'utilities', 'infrastructure']):
			return ['utilities', 'general']
		if _matches_any([sector, industry], ['energy', 'oil', 'gas', 'materials', 'mining']):
			return ['energy', 'general']
		return profiles
	except Exception:
		return profiles


def _matches_any(text_list: List[str], keywords: List[str]) -> bool:
	"""Helper to see if any keyword appears in the provided text snippets."""
	for text in text_list:
		if not text:
			continue
		for keyword in keywords:
			if keyword in text:
				return True
	return False


def _build_tag_config(profiles: List[str]) -> Dict[str, List[str]]:
	"""Merge base tags with sector overrides for the selected profiles."""
	if not profiles:
		profiles = ['general']
	config = {metric: list(tags) for metric, tags in BASE_METRIC_TAGS.items()}
	for profile in profiles:
		overrides = SECTOR_TAG_OVERRIDES.get(profile)
		if not overrides:
			continue
		for metric, additions in overrides.items():
			config.setdefault(metric, [])
			for tag in additions:
				if tag not in config[metric]:
					config[metric].append(tag)
	return config


def fetch_sec_edgar_financials(security_name: str, ticker: str, show_progress: bool = True) -> Dict:
	"""
	Fetch financial data from SEC Edgar using edgartools.
	
	Args:
		security_name: Name of the CF Security document
		ticker: Stock ticker symbol (e.g., "MSFT", "AAPL")
		show_progress: Whether to publish progress updates
		
	Returns:
		Dict with structure:
		{
			'success': bool,
			'total_periods': int,
			'imported_count': int,
			'updated_count': int,
			'skipped_count': int,
			'data_source_used': str,
			'error': Optional[str],
			'currency_mismatches': List[str]
		}
	"""
	try:
		from edgar import Company, set_identity
		
		# Set SEC API identity (required by SEC)
		set_identity("phalouvas@gmail.com")
		
		# Get security document to check currency and determine sector profile
		security = frappe.get_doc("CF Security", security_name)
		expected_currency = security.currency
		sector_profiles = _determine_sector_profile(security)
		tag_config = _build_tag_config(sector_profiles)
		
		# Initialize result tracking
		result = {
			'success': True,
			'total_periods': 0,
			'imported_count': 0,
			'updated_count': 0,
			'skipped_count': 0,
			'data_source_used': 'SEC Edgar',
			'error': None,
			'currency_mismatches': [],
			'sector_profile': sector_profiles[0] if sector_profiles else 'general'
		}
		
		# Get company and filings
		if show_progress:
			frappe.publish_progress(10, 100, description=f"Connecting to SEC Edgar for {ticker}...")
		
		company = Company(ticker)
		
		# Fetch quarterly and annual filings
		if show_progress:
			frappe.publish_progress(20, 100, description="Fetching 10-Q quarterly filings...")
		quarterly_filings = company.get_filings(form="10-Q").latest(16)
		
		if show_progress:
			frappe.publish_progress(30, 100, description="Fetching 10-K annual filings...")
		annual_filings = company.get_filings(form="10-K").latest(10)
		
		# Process all filings
		all_filings = []
		if quarterly_filings:
			all_filings.extend([(f, "Quarterly", "10-Q") for f in quarterly_filings])
		if annual_filings:
			all_filings.extend([(f, "Annual", "10-K") for f in annual_filings])
		
		if not all_filings:
			return {
				'success': False,
				'error': f"No 10-Q or 10-K filings found for {ticker}",
				'total_periods': 0,
				'imported_count': 0,
				'updated_count': 0,
				'skipped_count': 0,
				'data_source_used': 'SEC Edgar',
				'currency_mismatches': []
			}
		
		result['total_periods'] = len(all_filings)
		
		# Process each filing
		for idx, (filing, period_type, filing_form) in enumerate(all_filings):
			try:
				progress_pct = 30 + int((idx / len(all_filings)) * 65)
				period_label = f"{period_type} {filing.filing_date}"
				
				if show_progress:
					frappe.publish_progress(
						progress_pct, 
						100, 
						description=f"Processing {period_label} ({idx + 1}/{len(all_filings)})..."
					)
				
				# Extract financial data
				filing_obj = filing.obj()
				financials = filing_obj.financials
				
				if not financials:
					frappe.log_error(f"No financials available for {ticker} filing {filing.accession_no}", "SEC Edgar Fetch")
					result['skipped_count'] += 1
					continue
				
				# Determine period end date from filing
				period_end_date = str(filing.period_of_report) if filing.period_of_report else None
				
				if not period_end_date:
					frappe.log_error(f"No period_of_report for {ticker} filing {filing.accession_no}", "SEC Edgar Fetch")
					result['skipped_count'] += 1
					continue
				
				# Extract financial data using financials helper methods
				period_data = _extract_financial_data(
					financials=financials,
					period_end_date=period_end_date,
					period_type=period_type,
					document_fiscal_period=getattr(filing_obj, 'fiscal_period', None),
					tag_config=tag_config
				)
				
				if not period_data:
					frappe.log_error(f"Could not extract data for {ticker} period {period_end_date}", "SEC Edgar Fetch")
					result['skipped_count'] += 1
					continue
				
				# Add metadata
				period_data['filing_date'] = filing.filing_date.strftime('%Y-%m-%d') if filing.filing_date else None
				period_data['filing_form'] = filing_form
				period_data['accession_number'] = filing.accession_no
				period_data['document_fiscal_period'] = getattr(filing_obj, 'fiscal_period', None)
				period_data['data_source'] = 'SEC Edgar'
				period_data['data_quality_score'] = 95
				
				# Validate currency if available
				filing_currency = getattr(filing_obj, 'currency', None) or 'USD'
				if expected_currency and filing_currency != expected_currency:
					result['currency_mismatches'].append(
						f"{period_end_date}: {filing_currency} vs {expected_currency}"
					)
					frappe.log_error(
						f"Currency mismatch for {ticker} period {period_end_date}: "
						f"Filing has {filing_currency}, security expects {expected_currency}",
						"SEC Edgar Currency Mismatch"
					)
					result['skipped_count'] += 1
					continue
				period_data['currency'] = filing_currency or expected_currency
				
				# Upsert the period
				was_new = _upsert_period(
					security_name=security_name,
					period_type=period_type,
					period_data=period_data,
					commit=True
				)
				
				if was_new:
					result['imported_count'] += 1
				else:
					result['updated_count'] += 1
					
			except Exception as e:
				frappe.log_error(
					title=f"Error processing filing for {ticker}",
					message=f"Filing: {filing.accession_no}\nError: {str(e)}\n{frappe.get_traceback()}"
				)
				result['skipped_count'] += 1
				continue
		
		if show_progress:
			frappe.publish_progress(100, 100, description="Completed SEC Edgar data fetch")
		
		return result
		
	except Exception as e:
		error_msg = f"Failed to fetch SEC Edgar data for {ticker}: {str(e)}"
		frappe.log_error(
			title="SEC Edgar Fetch Error",
			message=f"{error_msg}\n{frappe.get_traceback()}"
		)
		return {
			'success': False,
			'error': error_msg,
			'total_periods': 0,
			'imported_count': 0,
			'updated_count': 0,
			'skipped_count': 0,
			'data_source_used': 'SEC Edgar',
			'currency_mismatches': []
		}


def _extract_financial_data(
	financials,
	period_end_date: str,
	period_type: str,
	document_fiscal_period: Optional[str] = None,
	tag_config: Optional[Dict[str, List[str]]] = None
) -> Optional[Dict]:
	"""
	Extract financial data for a filing period using standardized SEC statements.

	Args:
		financials: edgartools Financials object
		period_end_date: Period end date string (YYYY-MM-DD)
		period_type: 'Annual' or 'Quarterly'

	Returns:
		Dict with extracted financial data or None if extraction fails
	"""
	data = {'period_end_date': period_end_date}
	tag_config = tag_config or BASE_METRIC_TAGS

	def tags(metric: str) -> List[str]:
		return tag_config.get(metric) or BASE_METRIC_TAGS.get(metric, [])

	try:
		fiscal_year, fiscal_quarter = _determine_fiscal_context(
			financials=financials,
			period_end_date=period_end_date,
			document_fiscal_period=document_fiscal_period,
			period_type=period_type
		)
		data['fiscal_year'] = fiscal_year
		if period_type != 'Annual' and fiscal_quarter:
			data['fiscal_quarter'] = fiscal_quarter
		elif period_type == 'Annual':
			data['fiscal_quarter'] = None

		income_df = _get_statement_dataframe(financials.income_statement())

		if not data.get('shares_outstanding') and data.get('net_income') and data.get('net_income') not in (0, 0.0):
			eps = data.get('diluted_eps') or data.get('basic_eps')
			if eps not in (None, 0, 0.0):
				data['shares_outstanding'] = data['net_income'] / eps
		balance_df = _get_statement_dataframe(financials.balance_sheet())
		cashflow_df = _get_statement_dataframe(financials.cashflow_statement())

		income_col = _resolve_period_column(
			df=income_df,
			period_end_date=period_end_date,
			period_type=period_type,
			fiscal_quarter=fiscal_quarter
		)
		balance_col = _resolve_period_column(
			df=balance_df,
			period_end_date=period_end_date,
			period_type=period_type,
			fiscal_quarter=fiscal_quarter
		)
		cashflow_col = _resolve_period_column(
			df=cashflow_df,
			period_end_date=period_end_date,
			period_type=period_type,
			fiscal_quarter=fiscal_quarter
		)

		# Income statement metrics
		data['total_revenue'] = _safe_extract_value(income_df, tags('total_revenue'), income_col)
		if data['total_revenue'] is None:
			data['total_revenue'] = _coerce_number(financials.get_revenue())

		data['cost_of_revenue'] = _safe_extract_value(income_df, tags('cost_of_revenue'), income_col)
		data['gross_profit'] = _safe_extract_value(income_df, tags('gross_profit'), income_col)
		data['operating_expenses'] = _safe_extract_value(income_df, tags('operating_expenses'), income_col)
		data['operating_income'] = _safe_extract_value(income_df, tags('operating_income'), income_col)
		data['ebit'] = _safe_extract_value(income_df, tags('ebit'), income_col)
		if data['ebit'] is None:
			data['ebit'] = data.get('operating_income')
		data['ebitda'] = _safe_extract_value(income_df, tags('ebitda'), income_col)
		data['net_income'] = _safe_extract_value(income_df, tags('net_income'), income_col)
		if data['net_income'] is None:
			data['net_income'] = _coerce_number(financials.get_net_income())

		data['interest_expense'] = _safe_extract_value(income_df, tags('interest_expense'), income_col)
		data['tax_provision'] = _safe_extract_value(income_df, tags('tax_provision'), income_col)
		data['pretax_income'] = _safe_extract_value(income_df, tags('pretax_income'), income_col)
		data['total_costs_and_expenses'] = _safe_extract_value(
			income_df,
			tags('total_costs_and_expenses'),
			income_col
		)
		data['basic_eps'] = _safe_extract_value(income_df, tags('basic_eps'), income_col)
		data['diluted_eps'] = _safe_extract_value(income_df, tags('diluted_eps'), income_col)
		data['shares_outstanding'] = _safe_extract_value(income_df, tags('shares_outstanding'), income_col)

		if not data.get('shares_outstanding') and data.get('net_income') and data.get('net_income') not in (0, 0.0):
			eps = data.get('diluted_eps') or data.get('basic_eps')
			if eps not in (None, 0, 0.0):
				data['shares_outstanding'] = data['net_income'] / eps

		# Balance sheet metrics
		data['total_assets'] = _safe_extract_value(balance_df, tags('total_assets'), balance_col)
		if data['total_assets'] is None:
			data['total_assets'] = _coerce_number(financials.get_total_assets())

		data['total_liabilities'] = _safe_extract_value(balance_df, tags('total_liabilities'), balance_col)
		if data['total_liabilities'] is None:
			data['total_liabilities'] = _coerce_number(financials.get_total_liabilities())

		data['shareholders_equity'] = _safe_extract_value(balance_df, tags('shareholders_equity'), balance_col)
		if data['shareholders_equity'] is None:
			data['shareholders_equity'] = _coerce_number(financials.get_stockholders_equity())

		data['current_assets'] = _safe_extract_value(balance_df, tags('current_assets'), balance_col)
		if data['current_assets'] is None:
			data['current_assets'] = _coerce_number(financials.get_current_assets())

		data['current_liabilities'] = _safe_extract_value(balance_df, tags('current_liabilities'), balance_col)
		if data['current_liabilities'] is None:
			data['current_liabilities'] = _coerce_number(financials.get_current_liabilities())

		data['cash_and_equivalents'] = _safe_extract_value(balance_df, tags('cash_and_equivalents'), balance_col)
		data['accounts_receivable'] = _safe_extract_value(balance_df, tags('accounts_receivable'), balance_col)
		data['inventory'] = _safe_extract_value(balance_df, tags('inventory'), balance_col)
		data['long_term_debt'] = _safe_extract_value(balance_df, tags('long_term_debt'), balance_col)
		data['total_debt'] = _safe_extract_value(balance_df, tags('total_debt'), balance_col)
		if not data.get('total_debt') and data.get('long_term_debt'):
			data['total_debt'] = data['long_term_debt']
		data['retained_earnings'] = _safe_extract_value(balance_df, tags('retained_earnings'), balance_col)

		# Cash flow metrics
		dep_amort = _safe_extract_value(cashflow_df, tags('depreciation'), cashflow_col)

		ocf = _safe_extract_value(cashflow_df, tags('operating_cash_flow'), cashflow_col)
		if ocf is None:
			ocf = _coerce_number(financials.get_operating_cash_flow())
		data['operating_cash_flow'] = ocf

		capex = _safe_extract_value(cashflow_df, tags('capital_expenditures'), cashflow_col)
		if capex is None:
			capex = _coerce_number(financials.get_capital_expenditures())
		if capex is not None:
			capex = -abs(capex)
		data['capital_expenditures'] = capex

		if ocf is not None and capex is not None:
			data['free_cash_flow'] = ocf + capex
		else:
			data['free_cash_flow'] = _coerce_number(financials.get_free_cash_flow())

		if data.get('ebitda') is None and data.get('ebit') not in (None, 0, 0.0) and dep_amort not in (None, 0, 0.0):
			data['ebitda'] = data['ebit'] + dep_amort

		data['investing_cash_flow'] = _safe_extract_value(cashflow_df, tags('investing_cash_flow'), cashflow_col)
		data['financing_cash_flow'] = _safe_extract_value(cashflow_df, tags('financing_cash_flow'), cashflow_col)
		data['dividends_paid'] = _safe_extract_value(cashflow_df, tags('dividends_paid'), cashflow_col)

		# Final sanity checks derived from components
		if (data.get('total_revenue') in (None, 0, 0.0)) and (
			data.get('gross_profit') not in (None, 0, 0.0) and data.get('cost_of_revenue') not in (None, 0, 0.0)
		):
			data['total_revenue'] = data['gross_profit'] + data['cost_of_revenue']

		if (data.get('operating_income') in (None, 0, 0.0)) and (
			data.get('gross_profit') not in (None, 0, 0.0) and data.get('operating_expenses') not in (None, 0, 0.0)
		):
			data['operating_income'] = data['gross_profit'] - data['operating_expenses']

		return data

	except Exception as e:
		frappe.log_error(
			title="Financial Data Extraction Error",
			message=f"Error extracting data: {str(e)}\n{frappe.get_traceback()}"
		)
		return None


def _get_statement_dataframe(statement, use_standard: bool = True) -> pd.DataFrame:
	"""Return a pandas DataFrame for a statement, preferring standardized rendering."""
	if statement is None:
		return pd.DataFrame()

	if use_standard:
		try:
			rendered = statement.render(standard=True)
			df = rendered.to_dataframe()
			if isinstance(df, pd.DataFrame):
				return df
		except Exception:
			pass

	try:
		df = statement.to_dataframe()
		if isinstance(df, pd.DataFrame):
			return df
	except Exception:
		return pd.DataFrame()

	return pd.DataFrame()


def _resolve_period_column(
	df: pd.DataFrame,
	period_end_date: str,
	period_type: str,
	fiscal_quarter: Optional[str]
) -> Optional[str]:
	"""Determine which column corresponds to the filing period."""
	if df is None or df.empty:
		return None

	metadata_cols = {
		'concept', 'label', 'level', 'abstract', 'dimension',
		'balance', 'weight', 'preferred_sign', 'unit', 'point_in_time'
	}
	value_columns = [
		col for col in df.columns
		if isinstance(col, str) and col not in metadata_cols
	]
	if not value_columns:
		return None

	candidates: List[str] = []
	normalized_quarter = _normalize_fiscal_period_label(fiscal_quarter)
	if period_type == 'Quarterly':
		if normalized_quarter and normalized_quarter.startswith('Q'):
			candidates.append(f"{period_end_date} ({normalized_quarter})")
		candidates.append(period_end_date)
	else:
		candidates.append(f"{period_end_date} (FY)")
		candidates.append(period_end_date)

	for candidate in candidates:
		if candidate in value_columns:
			return candidate

	for col in value_columns:
		if period_end_date in col:
			return col

	date_like = sorted([col for col in value_columns if '-' in col])
	if date_like:
		return date_like[-1]

	return value_columns[-1]


def _determine_fiscal_context(
	financials,
	period_end_date: str,
	document_fiscal_period: Optional[str],
	period_type: str
) -> Tuple[int, Optional[str]]:
	"""Infer fiscal year and quarter using cover data with calendar fallbacks."""
	fiscal_year = None
	fiscal_period_focus = None

	try:
		cover_stmt = financials.cover()
		cover_df = cover_stmt.to_dataframe() if cover_stmt else None
		if cover_df is not None and not cover_df.empty and period_end_date in cover_df.columns:
			fy_row = cover_df[cover_df['label'].str.contains('Document Fiscal Year Focus', case=False, na=False)]
			if not fy_row.empty:
				val = fy_row.iloc[0][period_end_date]
				if pd.notna(val):
					try:
						fiscal_year = int(float(val))
					except Exception:
						pass

			fp_row = cover_df[cover_df['label'].str.contains('Document Fiscal Period Focus', case=False, na=False)]
			if not fp_row.empty:
				val = fp_row.iloc[0][period_end_date]
				if isinstance(val, str) and val:
					fiscal_period_focus = val.strip().upper()
	except Exception:
		pass

	if not fiscal_period_focus:
		normalized = _normalize_fiscal_period_label(document_fiscal_period)
		if normalized:
			fiscal_period_focus = normalized

	period_date = datetime.strptime(period_end_date, '%Y-%m-%d')
	if fiscal_year is None:
		fiscal_year = period_date.year

	if period_type == 'Annual':
		return fiscal_year, None

	if fiscal_period_focus in {'Q1', 'Q2', 'Q3', 'Q4'}:
		return fiscal_year, fiscal_period_focus

	month = period_date.month
	if month in [1, 2, 3]:
		return fiscal_year, 'Q1'
	if month in [4, 5, 6]:
		return fiscal_year, 'Q2'
	if month in [7, 8, 9]:
		return fiscal_year, 'Q3'
	return fiscal_year, 'Q4'


def _normalize_fiscal_period_label(value: Optional[str]) -> Optional[str]:
	"""Normalize quarter labels like 'Quarter 1' or 'q3' to canonical tokens."""
	if not value:
		return None

	text = str(value).strip().upper()
	text = text.replace('QUARTER', 'Q').replace('QTR', 'Q')
	if text.startswith('Q') and len(text) >= 2 and text[1].isdigit():
		return f"Q{text[1]}"
	if text.startswith('FY'):
		return 'FY'
	if text in {'Q1', 'Q2', 'Q3', 'Q4'}:
		return text
	return None


def _coerce_number(value: Optional[object]) -> Optional[float]:
	"""Convert assorted numeric types/strings to float, returning None on failure."""
	if value in (None, ''):
		return None
	try:
		if isinstance(value, str):
			cleaned = value.replace(',', '').strip()
			if not cleaned:
				return None
			value = cleaned
		if pd.isna(value):
			return None
		return float(value)
	except Exception:
		return None


def _safe_extract_value(df: pd.DataFrame, label_variations: List[str], date_col: str) -> Optional[float]:
	"""
	Safely extract a value from DataFrame by trying multiple label variations.
	Tries exact matches first, then falls back to substring matching.
	
	Args:
		df: DataFrame with 'label' column and date columns
		label_variations: List of possible label names to try (in priority order)
		date_col: Date column name to extract value from
		
	Returns:
		Float value or None if not found
	"""
	try:
		if df is None or df.empty or 'label' not in df.columns or date_col not in df.columns:
			return None
		
		# First pass: try exact matches (case-insensitive)
		for label in label_variations:
			mask = df['label'].str.lower() == label.lower()
			matches = df[mask]
			
			if not matches.empty:
				value = matches.iloc[0][date_col]
				if pd.notna(value):
					try:
						return float(value)
					except (ValueError, TypeError):
						continue
		
		# Second pass: try substring matching (case-insensitive)
		for label in label_variations:
			mask = df['label'].str.contains(label, case=False, na=False, regex=False)
			matches = df[mask]
			
			if not matches.empty:
				# Get the first match
				value = matches.iloc[0][date_col]
				
				# Convert to float if possible
				if pd.notna(value):
					try:
						return float(value)
					except (ValueError, TypeError):
						continue
		
		return None
		
	except Exception as e:
		frappe.log_error(
			title="Value Extraction Error",
			message=f"Error extracting value for labels {label_variations}: {str(e)}"
		)
		return None


def _upsert_period(
	security_name: str,
	period_type: str,
	period_data: Dict,
	commit: bool = True
) -> bool:
	"""
	Create or update a CF Financial Period record.
	
	Args:
		security_name: Name of the CF Security
		period_type: 'Annual' or 'Quarterly'
		period_data: Dict with all period data including metadata
		commit: Whether to commit the transaction
		
	Returns:
		True if new record created, False if existing record updated
	"""
	try:
		# Extract key fields for finding/creating period
		fiscal_year = period_data.get('fiscal_year')
		fiscal_quarter = period_data.get('fiscal_quarter') if period_type == 'Quarterly' else None
		period_end_date = period_data.get('period_end_date')
		
		# Try to find existing period
		filters = {
			'security': security_name,
			'period_type': period_type,
			'fiscal_year': fiscal_year
		}
		
		if period_type == 'Quarterly' and fiscal_quarter:
			filters['fiscal_quarter'] = fiscal_quarter
		
		existing = frappe.db.exists('CF Financial Period', filters)
		
		if existing:
			# Update existing period
			period = frappe.get_doc('CF Financial Period', existing)
			was_new = False
		else:
			# Create new period
			period = frappe.new_doc('CF Financial Period')
			period.security = security_name
			period.period_type = period_type
			period.fiscal_year = fiscal_year
			if period_type == 'Quarterly':
				period.fiscal_quarter = fiscal_quarter
			was_new = True
		
		# Set all fields from period_data
		for field, value in period_data.items():
			if field not in ['fiscal_year', 'fiscal_quarter'] and hasattr(period, field):
				setattr(period, field, value)
		
		# Save the period
		period.save(ignore_permissions=True)
		
		# Commit if requested
		if commit:
			frappe.db.commit()
		
		return was_new
		
	except Exception as e:
		frappe.log_error(
			title="Period Upsert Error",
			message=f"Error upserting period for {security_name}: {str(e)}\n{frappe.get_traceback()}"
		)
		# Re-raise to allow caller to handle
		raise