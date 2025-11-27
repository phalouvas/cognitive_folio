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
		set_identity("Cognitive Folio info@kainotomo.com")
		
		# Get security document to check currency
		security = frappe.get_doc("CF Security", security_name)
		expected_currency = security.currency
		
		# Initialize result tracking
		result = {
			'success': True,
			'total_periods': 0,
			'imported_count': 0,
			'updated_count': 0,
			'skipped_count': 0,
			'data_source_used': 'SEC Edgar',
			'error': None,
			'currency_mismatches': []
		}
		
		# Get company and filings
		if show_progress:
			frappe.publish_progress(10, 100, description=f"Connecting to SEC Edgar for {ticker}...")
		
		company = Company(ticker)
		
		# Fetch quarterly and annual filings
		if show_progress:
			frappe.publish_progress(20, 100, description="Fetching 10-Q quarterly filings...")
		quarterly_filings = company.get_filings(form="10-Q").latest(12)
		
		if show_progress:
			frappe.publish_progress(30, 100, description="Fetching 10-K annual filings...")
		annual_filings = company.get_filings(form="10-K").latest(3)
		
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
					period_end_date=period_end_date
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
	period_end_date: str
) -> Optional[Dict]:
	"""
	Extract financial data using edgartools Financials helper methods.
	
	This uses edgartools' built-in methods like get_revenue(), get_net_income(), etc.
	which automatically extract quarterly values (not YTD/cumulative) from 10-Q filings.
	
	Args:
		financials: edgartools Financials object
		period_end_date: Period end date string (YYYY-MM-DD)
		
	Returns:
		Dict with extracted financial data or None if extraction fails
	"""
	data = {'period_end_date': period_end_date}
	
	try:
		# Use edgartools helper methods for reliable quarterly data extraction
		# These methods automatically handle quarterly vs YTD distinction
		
		# Income statement items
		try:
			data['total_revenue'] = financials.get_revenue()
		except:
			data['total_revenue'] = None
			
		try:
			data['net_income'] = financials.get_net_income()
		except:
			data['net_income'] = None
		
		# Balance sheet items (point-in-time, so DataFrame is safe)
		try:
			data['total_assets'] = financials.get_total_assets()
		except:
			data['total_assets'] = None
			
		try:
			data['total_liabilities'] = financials.get_total_liabilities()
		except:
			data['total_liabilities'] = None
			
		try:
			data['shareholders_equity'] = financials.get_stockholders_equity()
		except:
			data['shareholders_equity'] = None
			
		try:
			data['current_assets'] = financials.get_current_assets()
		except:
			data['current_assets'] = None
			
		try:
			data['current_liabilities'] = financials.get_current_liabilities()
		except:
			data['current_liabilities'] = None
		
		# Cash flow items
		try:
			# get_operating_cash_flow returns string sometimes, need to handle
			ocf = financials.get_operating_cash_flow()
			data['operating_cash_flow'] = float(ocf) if ocf else None
		except:
			data['operating_cash_flow'] = None
			
		try:
			data['capital_expenditures'] = financials.get_capital_expenditures()
		except:
			data['capital_expenditures'] = None
		
		# Calculate free cash flow
		try:
			data['free_cash_flow'] = financials.get_free_cash_flow()
		except:
			# Fallback calculation if method fails
			if data.get('operating_cash_flow') and data.get('capital_expenditures'):
				data['free_cash_flow'] = data['operating_cash_flow'] + data['capital_expenditures']
			else:
				data['free_cash_flow'] = None
		
		# For fields not available via helper methods, use DataFrame with point-in-time data only
		# (Balance sheet items are safe since they're snapshots, not cumulative)
		try:
			balance_df = financials.balance_sheet().to_dataframe()
			date_cols = [c for c in balance_df.columns if isinstance(c, str) and '-' in c]
			if date_cols:
				latest_col = max(date_cols)
				
				# Extract additional balance sheet items
				data['cash_and_equivalents'] = _safe_extract_value(
					balance_df,
					['Cash and Cash Equivalents', 'Cash', 'Cash and Equivalents'],
					latest_col
				)
				data['accounts_receivable'] = _safe_extract_value(
					balance_df,
					['Accounts Receivable', 'Accounts Receivable Net', 'Receivables Net'],
					latest_col
				)
				data['inventory'] = _safe_extract_value(
					balance_df,
					['Inventory', 'Inventory Net'],
					latest_col
				)
				data['long_term_debt'] = _safe_extract_value(
					balance_df,
					['Long-term Debt', 'Long Term Debt Noncurrent', 'Long-Term Debt', 'Debt Noncurrent'],
					latest_col
				)
				data['retained_earnings'] = _safe_extract_value(
					balance_df,
					['Retained Earnings', 'Retained Earnings Accumulated Deficit'],
					latest_col
				)
		except Exception as e:
			frappe.log_error(
				title="Balance Sheet Extraction Error",
				message=f"Error extracting balance sheet details: {str(e)}"
			)
		
		# Note: For income statement items like COGS, gross profit, operating expenses, etc.,
		# we rely on CF Financial Period's validate() method to calculate them from available data.
		# This avoids the YTD vs quarterly confusion in 10-Q filings.
		
		# Determine fiscal year and quarter from the filing cover page first
		# Fallback to calendar-based derivation only if cover data is unavailable
		fiscal_year = None
		fiscal_period = None
		try:
			cover_stmt = financials.cover()
			cover_df = cover_stmt.to_dataframe()
			# Columns in cover_df include date columns like 'YYYY-MM-DD'
			date_col = period_end_date
			if cover_df is not None and not cover_df.empty and date_col in cover_df.columns:
				# Extract Document Fiscal Year Focus
				fy_row = cover_df[cover_df['label'].str.contains('Document Fiscal Year Focus', case=False, na=False)]
				if not fy_row.empty:
					val = fy_row.iloc[0][date_col]
					if pd.notna(val):
						try:
							fiscal_year = int(float(val))
						except Exception:
							pass
				# Extract Document Fiscal Period Focus (Q1/Q2/Q3/Q4/FY)
				fp_row = cover_df[cover_df['label'].str.contains('Document Fiscal Period Focus', case=False, na=False)]
				if not fp_row.empty:
					val = fp_row.iloc[0][date_col]
					if isinstance(val, str) and val:
						fiscal_period = val.strip().upper()
		except Exception as _e:
			# Ignore and fallback to calendar mapping
			pass

		if fiscal_year is not None:
			data['fiscal_year'] = fiscal_year
		else:
			# Fallback: derive from calendar year
			period_date = datetime.strptime(period_end_date, '%Y-%m-%d')
			data['fiscal_year'] = period_date.year

		if fiscal_period in {'Q1','Q2','Q3','Q4'}:
			data['fiscal_quarter'] = fiscal_period
		elif fiscal_period == 'FY':
			data['fiscal_quarter'] = None
		else:
			# Fallback: estimate based on calendar month
			period_date = datetime.strptime(period_end_date, '%Y-%m-%d')
			month = period_date.month
			if month in [1, 2, 3]:
				data['fiscal_quarter'] = 'Q1'
			elif month in [4, 5, 6]:
				data['fiscal_quarter'] = 'Q2'
			elif month in [7, 8, 9]:
				data['fiscal_quarter'] = 'Q3'
			else:
				data['fiscal_quarter'] = 'Q4'
		
		return data
		
	except Exception as e:
		frappe.log_error(
			title="Financial Data Extraction Error",
			message=f"Error extracting data: {str(e)}\n{frappe.get_traceback()}"
		)
		return None


def _safe_extract_value(df: pd.DataFrame, label_variations: List[str], date_col: str) -> Optional[float]:
	"""
	Safely extract a value from DataFrame by trying multiple label variations.
	
	Args:
		df: DataFrame with 'label' column and date columns
		label_variations: List of possible label names to try
		date_col: Date column name to extract value from
		
	Returns:
		Float value or None if not found
	"""
	try:
		if df is None or df.empty or 'label' not in df.columns or date_col not in df.columns:
			return None
		
		# Try each label variation with case-insensitive matching
		for label in label_variations:
			# Case-insensitive search
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
