"""
SEC Edgar inline XBRL Data Fetcher

This module handles downloading and parsing inline XBRL (iXBRL) financial statements
from SEC Edgar for US-listed companies. It provides higher quality data (95% accuracy) 
compared to Yahoo Finance (85% accuracy).

Uses python-xbrl library to extract US-GAAP facts from HTML filings.
"""

import frappe
import json
import warnings
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional
from xbrl import XBRLParser

# Suppress noisy parser warnings (benign for inline XBRL embedded in HTML)
warnings.filterwarnings("ignore", message="It looks like you're parsing an XML document using an HTML parser.")
warnings.filterwarnings("ignore", message="The 'strip_cdata' option of HTMLParser() has never done anything")


def fetch_sec_edgar_financials(security_name: str, cik: str) -> Dict:
	"""
	Fetch financial data from SEC Edgar for a given security.
	
	Args:
		security_name: Name of the CF Security document
		cik: SEC Central Index Key (10-digit zero-padded string)
		
	Returns:
		Dict with success status and results
	"""
	try:
		from sec_edgar_downloader import Downloader
		
		# Create downloader with proper user agent
		dl = Downloader(
			"CognitiveFollio",
			"compliance@example.com",
			download_folder=frappe.get_site_path("private", "files", "sec_edgar")
		)
		
		# Remove leading zeros for the API
		cik_num = str(int(cik))
		
		# Download 10-K (annual) and 10-Q (quarterly) filings with details
		# Limit to 3 years of annual data and 12 quarters for fundamental analysis
		try:
			annual_count = dl.get("10-K", cik_num, limit=3, download_details=True)
			quarterly_count = dl.get("10-Q", cik_num, limit=12, download_details=True)
		except Exception as e:
			frappe.log_error(
				title=f"SEC Edgar Download Error: {security_name}",
				message=f"CIK: {cik}\nError: {str(e)}"
			)
			return {
				"success": False,
				"error": f"Failed to download SEC filings: {str(e)}",
				"imported_count": 0,
				"updated_count": 0,
				"upgraded_count": 0,
				"skipped_count": 0
			}
		
		# Note: sec-edgar-downloader always creates directories with 10-digit zero-padded CIK
		# regardless of what we pass to get(), so use the original zero-padded CIK for parsing
		cik_for_parsing = cik.zfill(10)
		
		# Parse the downloaded iXBRL files
		result = parse_sec_ixbrl_files(security_name, cik_for_parsing)
		
		return result
		
	except ImportError:
		frappe.log_error(
			title="SEC Edgar Library Missing",
			message="sec-edgar-downloader library is not installed. Run: bench pip install sec-edgar-downloader"
		)
		return {
			"success": False,
			"error": "SEC Edgar library not installed",
			"imported_count": 0,
			"updated_count": 0,
			"upgraded_count": 0,
			"skipped_count": 0
		}
	except Exception as e:
		frappe.log_error(
			title=f"SEC Edgar Fetch Error: {security_name}",
			message=str(e)
		)
		return {
			"success": False,
			"error": str(e),
			"imported_count": 0,
			"updated_count": 0,
			"upgraded_count": 0,
			"skipped_count": 0
		}


def parse_sec_ixbrl_files(security_name: str, cik: str) -> Dict:
	"""
	Parse downloaded inline XBRL HTML files and create/update financial periods.
	
	Args:
		security_name: Name of the CF Security document
		cik: SEC Central Index Key (without leading zeros)
		
	Returns:
		Dict with parsing results
	"""
	security = frappe.get_doc("CF Security", security_name)
	
	imported_count = 0
	updated_count = 0
	upgraded_count = 0
	skipped_count = 0
	errors = []
	
	# SEC Edgar quality score
	sec_quality_score = 95
	
	# Path to downloaded SEC filings
	sec_path = Path(frappe.get_site_path("private", "files", "sec_edgar", "sec-edgar-filings", cik))
	
	if not sec_path.exists():
		return {
			"success": False,
			"error": f"No SEC filings found at {sec_path}",
			"imported_count": 0,
			"updated_count": 0,
			"upgraded_count": 0,
			"skipped_count": 0,
			"data_source_used": "SEC Edgar"
		}
	
	# Process 10-K files (Annual)
	annual_path = sec_path / "10-K"
	if annual_path.exists():
		for filing_dir in sorted(annual_path.iterdir(), reverse=True):
			if filing_dir.is_dir():
				result = process_ixbrl_filing(
					security,
					filing_dir,
					"Annual",
					sec_quality_score
				)
				
				imported_count += result["imported"]
				updated_count += result["updated"]
				upgraded_count += result["upgraded"]
				skipped_count += result["skipped"]
				if result["error"]:
					errors.append(result["error"])
	
	# Process 10-Q files (Quarterly)
	quarterly_path = sec_path / "10-Q"
	if quarterly_path.exists():
		for filing_dir in sorted(quarterly_path.iterdir(), reverse=True):
			if filing_dir.is_dir():
				result = process_ixbrl_filing(
					security,
					filing_dir,
					"Quarterly",
					sec_quality_score
				)
				
				imported_count += result["imported"]
				updated_count += result["updated"]
				upgraded_count += result["upgraded"]
				skipped_count += result["skipped"]
				if result["error"]:
					errors.append(result["error"])
	
	frappe.db.commit()
	
	return {
		"success": True,
		"imported_count": imported_count,
		"updated_count": updated_count,
		"upgraded_count": upgraded_count,
		"skipped_count": skipped_count,
		"total_periods": imported_count + updated_count + upgraded_count,
		"errors": errors if errors else None,
		"data_source_used": "SEC Edgar"
	}


def process_ixbrl_filing(
	security,
	filing_dir: Path,
	period_type: str,
	quality_score: int
) -> Dict:
	"""
	Process a single iXBRL filing (10-K or 10-Q).
	
	Args:
		security: CF Security document
		filing_dir: Path to the filing directory
		period_type: "Annual" or "Quarterly"
		quality_score: Data quality score for this source
		
	Returns:
		Dict with counts of imported/updated/upgraded/skipped records
	"""
	result = {
		"imported": 0,
		"updated": 0,
		"upgraded": 0,
		"skipped": 0,
		"error": None
	}
	
	try:
		# Find the primary HTML document (inline XBRL)
		html_files = list(filing_dir.glob("*primary-document*.html")) or \
		             list(filing_dir.glob("*.htm"))
		
		if not html_files:
			result["error"] = f"No HTML document found in {filing_dir}"
			return result
		
		html_file = html_files[0]
		
		# Parse the iXBRL document using python-xbrl
		xbrl_parser = XBRLParser()
		xbrl = xbrl_parser.parse(str(html_file))
		
		# Extract financial facts
		financial_data = extract_usgaap_facts(xbrl, period_type)
		
		if not financial_data or "period_end_date" not in financial_data:
			return {
				"imported": 0,
				"updated": 0,
				"upgraded": 0,
				"skipped": 1,
				"error": f"No valid financial data extracted from {filing_dir.name}"
			}
		
		fiscal_year = financial_data.get("fiscal_year")
		fiscal_quarter = financial_data.get("fiscal_quarter") if period_type == "Quarterly" else None
		period_end_date = financial_data.get("period_end_date")
		
		# Check for existing period
		filters = {
			"security": security.name,
			"period_type": period_type,
			"fiscal_year": fiscal_year
		}
		
		if period_type == "Quarterly" and fiscal_quarter:
			filters["fiscal_quarter"] = fiscal_quarter
		
		existing = frappe.db.get_value(
			"CF Financial Period",
			filters,
			["name", "data_quality_score", "override_yahoo"],
			as_dict=True
		)
		
		# Skip if override_yahoo is set
		if existing and existing.override_yahoo:
			return {
				"imported": 0,
				"updated": 0,
				"upgraded": 0,
				"skipped": 1,
				"error": None
			}
		
		# Determine if upgrade is needed
		is_upgrade = False
		is_update = False
		
		if existing:
			if existing.data_quality_score < quality_score:
				is_upgrade = True
				period = frappe.get_doc("CF Financial Period", existing.name)
			elif existing.data_quality_score >= quality_score:
				return {
					"imported": 0,
					"updated": 0,
					"upgraded": 0,
					"skipped": 1,
					"error": None
				}
			else:
				is_update = True
				period = frappe.get_doc("CF Financial Period", existing.name)
		else:
			period = frappe.new_doc("CF Financial Period")
			period.security = security.name
			period.period_type = period_type
			period.fiscal_year = fiscal_year
			if fiscal_quarter:
				period.fiscal_quarter = fiscal_quarter
			period.period_end_date = period_end_date
		
		# Set metadata
		period.data_source = "SEC Edgar"
		period.data_quality_score = quality_score
		period.currency = security.currency or "USD"
		
		# Map US-GAAP fields to our structure
		map_financial_data_to_period(period, financial_data)
		
		# Store raw data reference
		period.raw_income_statement = json.dumps({
			"source": "SEC Edgar iXBRL",
			"filing": filing_dir.name,
			"file": "primary-document.html",
			"period_type": period_type
		}, indent=2)
		
		period.save()
		
		if is_upgrade:
			return {"imported": 0, "updated": 0, "upgraded": 1, "skipped": 0, "error": None}
		elif is_update:
			return {"imported": 0, "updated": 1, "upgraded": 0, "skipped": 0, "error": None}
		else:
			return {"imported": 1, "updated": 0, "upgraded": 0, "skipped": 0, "error": None}
			
	except Exception as e:
		frappe.log_error(
			title=f"iXBRL Processing Error: {filing_dir.name}",
			message=str(e)
		)
		return {
			"imported": 0,
			"updated": 0,
			"upgraded": 0,
			"skipped": 0,
			"error": f"{filing_dir.name}: {str(e)}"
		}


def extract_usgaap_facts(xbrl, period_type: str) -> Optional[Dict]:
	"""
	Extract US-GAAP financial facts from iXBRL document using python-xbrl.
	
	Args:
		xbrl: Parsed BeautifulSoup object from python-xbrl
		period_type: "Annual" or "Quarterly"
		
	Returns:
		Dict with extracted financial data or None
	"""
	try:
		# US-GAAP concept mappings to our field names
		concept_map = {
			# Income Statement
			"us-gaap:Revenues": "total_revenue",
			"us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": "total_revenue",
			"us-gaap:CostOfRevenue": "cost_of_revenue",
			"us-gaap:CostOfGoodsAndServicesSold": "cost_of_revenue",
			"us-gaap:GrossProfit": "gross_profit",
			"us-gaap:OperatingExpenses": "operating_expenses",
			"us-gaap:OperatingIncomeLoss": "operating_income",
			"us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "pretax_income",
			"us-gaap:IncomeTaxExpenseBenefit": "tax_provision",
			"us-gaap:NetIncomeLoss": "net_income",
			"us-gaap:EarningsPerShareBasic": "basic_eps",
			"us-gaap:EarningsPerShareDiluted": "diluted_eps",
			
			# Balance Sheet
			"us-gaap:Assets": "total_assets",
			"us-gaap:AssetsCurrent": "current_assets",
			"us-gaap:CashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",
			"us-gaap:AccountsReceivableNetCurrent": "accounts_receivable",
			"us-gaap:InventoryNet": "inventory",
			"us-gaap:Liabilities": "total_liabilities",
			"us-gaap:LiabilitiesCurrent": "current_liabilities",
			"us-gaap:LongTermDebt": "long_term_debt",
			"us-gaap:StockholdersEquity": "shareholders_equity",
			"us-gaap:RetainedEarningsAccumulatedDeficit": "retained_earnings",
			
			# Cash Flow
			"us-gaap:NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
			"us-gaap:PaymentsToAcquirePropertyPlantAndEquipment": "capital_expenditures",
			"us-gaap:NetCashProvidedByUsedInInvestingActivities": "investing_cash_flow",
			"us-gaap:NetCashProvidedByUsedInFinancingActivities": "financing_cash_flow",
		}
		
		# Get all contexts to find the main reporting period
		contexts = xbrl.find_all('xbrli:context')
		if not contexts:
			frappe.log_error(title="No XBRL Contexts", message="No contexts found in XBRL document")
			return None
		
		# Find the most recent period context (duration, not instant)
		period_context_id = None
		period_end_date = None
		period_start_date = None
		fiscal_period_label = None  # Will store fp metadata (Q1, Q2, Q3, Q4, FY)
		
		for ctx in contexts:
			period = ctx.find('xbrli:period')
			if not period:
				continue
				
			# Look for duration periods (not instant/point-in-time)
			start = period.find('xbrli:startdate')
			end = period.find('xbrli:enddate')
			
			if start and end:
				try:
					end_date = datetime.fromisoformat(end.text.strip()).date()
					start_date = datetime.fromisoformat(start.text.strip()).date()
					
					# Use the most recent complete period
					if not period_end_date or end_date > period_end_date:
						period_end_date = end_date
						period_start_date = start_date
						period_context_id = ctx.get('id')
						
						# Try to extract fiscal period from context ID or segments
						# SEC filings often have contextRef like "FY2025Q2" or contain fiscal period indicators
						ctx_id = ctx.get('id', '')
						if 'Q1' in ctx_id.upper():
							fiscal_period_label = 'Q1'
						elif 'Q2' in ctx_id.upper():
							fiscal_period_label = 'Q2'
						elif 'Q3' in ctx_id.upper():
							fiscal_period_label = 'Q3'
						elif 'Q4' in ctx_id.upper():
							fiscal_period_label = 'Q4'
						elif 'FY' in ctx_id.upper() or 'ANNUAL' in ctx_id.upper():
							fiscal_period_label = 'FY'
				except:
					continue
		
		if not period_context_id:
			frappe.log_error(title="No Period Context", message="Could not find valid period context")
			return None
		
		# Extract facts for this period
		financial_data = {}
		
		for us_gaap_name, our_field in concept_map.items():
			facts = xbrl.find_all(attrs={'name': us_gaap_name, 'contextref': period_context_id})
			
			if facts:
				# Use the first matching fact
				fact = facts[0]
				value_text = fact.text.strip() if fact.text else None
				
				if value_text:
					try:
						# Remove commas and convert to float
						value = float(value_text.replace(',', ''))
						
						# Check for scale/decimals
						decimals = fact.get('decimals', '')
						scale = fact.get('scale', '')
						
						# SEC filings often use scale or negative decimals to indicate thousands/millions
						if scale:
							value = value * (10 ** int(scale))
						elif decimals and decimals.startswith('-'):
							value = value * (10 ** int(decimals))
						
						financial_data[our_field] = value
					except (ValueError, TypeError) as e:
						frappe.log_error(
							title=f"Value Conversion Error: {us_gaap_name}",
							message=f"Could not convert '{value_text}' to float: {e}"
						)
						continue
		
		if not financial_data:
			return None
		
		# Determine fiscal year and quarter
		fiscal_year = period_end_date.year
		month = period_end_date.month
		
		# Use fiscal period label from SEC metadata if available, otherwise calculate from month
		if fiscal_period_label and fiscal_period_label in ['Q1', 'Q2', 'Q3', 'Q4']:
			fiscal_quarter = fiscal_period_label
		else:
			# Fallback: Map month to quarter as approximation
			if month in [1, 2, 3]:
				fiscal_quarter = "Q1"
			elif month in [4, 5, 6]:
				fiscal_quarter = "Q2"
			elif month in [7, 8, 9]:
				fiscal_quarter = "Q3"
			else:
				fiscal_quarter = "Q4"
		
		# Calculate derived fields
		if "gross_profit" not in financial_data and "total_revenue" in financial_data and "cost_of_revenue" in financial_data:
			financial_data["gross_profit"] = financial_data["total_revenue"] - financial_data["cost_of_revenue"]
		
		if "capital_expenditures" in financial_data:
			financial_data["capital_expenditures"] = abs(financial_data["capital_expenditures"])
		
		if "operating_cash_flow" in financial_data and "capital_expenditures" in financial_data:
			financial_data["free_cash_flow"] = financial_data["operating_cash_flow"] - financial_data["capital_expenditures"]
		
		# Add period metadata
		financial_data["period_end_date"] = period_end_date
		financial_data["fiscal_year"] = fiscal_year
		financial_data["fiscal_quarter"] = fiscal_quarter if period_type == "Quarterly" else None
		
		return financial_data
	
	except Exception as e:
		frappe.log_error(
			title="XBRL Parsing Error",
			message=f"Error parsing XBRL data: {str(e)}\n{frappe.get_traceback()}"
		)
		return None


def map_financial_data_to_period(period, financial_data: Dict):
	"""
	Map extracted financial data to CF Financial Period fields.
	
	Args:
		period: CF Financial Period document
		financial_data: Dict with extracted data
	"""
	# List of all possible fields
	fields = [
		"total_revenue", "cost_of_revenue", "gross_profit",
		"operating_expenses", "operating_income", "ebit", "ebitda",
		"interest_expense", "pretax_income", "tax_provision", "net_income",
		"diluted_eps", "basic_eps",
		"total_assets", "current_assets", "cash_and_equivalents",
		"accounts_receivable", "inventory",
		"total_liabilities", "current_liabilities", "total_debt",
		"long_term_debt", "shareholders_equity", "retained_earnings",
		"operating_cash_flow", "capital_expenditures", "free_cash_flow",
		"investing_cash_flow", "financing_cash_flow", "dividends_paid"
	]
	
	for field in fields:
		if field in financial_data and financial_data[field] is not None:
			setattr(period, field, financial_data[field])
