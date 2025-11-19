"""
SEC Edgar XBRL Data Fetcher

This module handles downloading and parsing XBRL financial statements from SEC Edgar
for US-listed companies. It provides higher quality data (95% accuracy) compared to
Yahoo Finance (85% accuracy).

Phase 2 Implementation - US-GAAP taxonomy support
"""

import frappe
import os
import json
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from pathlib import Path


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
		
		# Download 10-K (annual) and 10-Q (quarterly) filings
		# Limit to last 5 years
		try:
			# Request detailed files (instance docs, filing summary) for XBRL parsing
			annual_count = dl.get("10-K", cik_num, limit=5, download_details=True)
			quarterly_count = dl.get("10-Q", cik_num, limit=20, download_details=True)  # ~5 years of quarters
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
		
		# Parse the downloaded XBRL files
		result = parse_sec_xbrl_files(security_name, cik_num)
		
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


def parse_sec_xbrl_files(security_name: str, cik: str) -> Dict:
	"""
	Parse downloaded XBRL files and create/update financial periods.
	
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
			"skipped_count": 0
		}
	
	# Process 10-K files (Annual)
	annual_path = sec_path / "10-K"
	if annual_path.exists():
		for filing_dir in sorted(annual_path.iterdir(), reverse=True):
			if filing_dir.is_dir():
				result = process_xbrl_filing(
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
				result = process_xbrl_filing(
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


def process_xbrl_filing(
	security,
	filing_dir: Path,
	period_type: str,
	quality_score: int
) -> Dict:
	"""
	Process a single XBRL filing directory.
	
	Args:
		security: CF Security document
		filing_dir: Path to filing directory
		period_type: "Annual" or "Quarterly"
		quality_score: Data quality score (95 for SEC Edgar)
		
	Returns:
		Dict with counts: imported, updated, upgraded, skipped, error
	"""
	try:
		# Prefer iXBRL primary HTML; fallback to any XML/HTM
		candidate: Optional[Path] = None
		primary = filing_dir / "primary-document.html"
		if primary.exists():
			candidate = primary
		else:
			# Common alternatives
			for pat in ("*-xbrl.xml", "*.xml", "*.htm", "*.html"):
				for f in filing_dir.glob(pat):
					candidate = f
					break
				if candidate:
					break

		if not candidate:
			return {
				"imported": 0,
				"updated": 0,
				"upgraded": 0,
				"skipped": 0,
				"error": f"No iXBRL/XBRL file found in {filing_dir.name}"
			}

		# Use lxml-based iXBRL extraction first (fast and self-contained)
		financial_data = None
		err = None
		try:
			from cognitive_folio.utils.ixbrl_lxml_parser import extract_financial_data_ixbrl
			financial_data, err = extract_financial_data_ixbrl(str(candidate))
		except Exception as le:
			err = str(le)

		# If lxml approach failed or returned nothing, skip Arelle to avoid env issues
		# (We rely on exhibit crawling + lxml iXBRL parsing below)

		# If still no data and candidate is primary doc, try downloading linked exhibit HTMLs
		if (not financial_data):
			try:
				from lxml import etree
				import requests
				parser = etree.HTMLParser(recover=True)
				tree = etree.parse(str(candidate), parser)
				links = []
				for a in tree.findall('.//a'):
					href = a.get('href') or ''
					if not href:
						continue
					lower = href.lower()
					if lower.endswith('.htm') or lower.endswith('.html'):
						# Prefer Inline XBRL exhibit files referenced locally or on sec.gov
						if 'exhibit' in lower or 'financial' in lower or 'statement' in lower:
							links.append(href)
					# Download and test each
				for href in links[:10]:  # limit to avoid overfetching
					try:
						if href.startswith('http'):
							url = href
							fname = href.split('/')[-1]
						else:
							# relative file inside same directory
							url = None
							fname = href
						local_path = filing_dir / fname
						if not local_path.exists() and url:
							resp = requests.get(url, headers={"User-Agent": "Cognitive Folio (compliance@example.com)"}, timeout=20)
							if resp.status_code == 200 and resp.text:
								local_path.write_text(resp.text, encoding='utf-8', errors='ignore')
						# Try parse downloaded file
						from cognitive_folio.utils.ixbrl_lxml_parser import extract_financial_data_ixbrl
						fd, e2 = extract_financial_data_ixbrl(str(local_path))
						if fd:
							financial_data, err = fd, None
							candidate = local_path
							break
					except Exception:
						continue
			except Exception:
				pass
		if err or not financial_data:
			return {
				"imported": 0,
				"updated": 0,
				"upgraded": 0,
				"skipped": 1,
				"error": err or f"No financial data extracted from {candidate.name}"
			}
		
		if not financial_data:
			return {
				"imported": 0,
				"updated": 0,
				"upgraded": 0,
				"skipped": 1,
				"error": f"No financial data extracted from {candidate.name}"
			}
		
		# Determine fiscal year and quarter
		fiscal_year = financial_data.get("fiscal_year")
		fiscal_quarter = financial_data.get("fiscal_quarter") if period_type == "Quarterly" else None
		period_end_date = financial_data.get("period_end_date")
		
		if not fiscal_year or not period_end_date:
			return {
				"imported": 0,
				"updated": 0,
				"upgraded": 0,
				"skipped": 1,
				"error": f"Missing fiscal year or period end date in {candidate.name}"
			}
		
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
		
		# Store raw XBRL data reference
		period.raw_income_statement = json.dumps({
			"source": "SEC Edgar iXBRL",
			"filing": filing_dir.name,
			"file": candidate.name,
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
			title=f"XBRL Processing Error: {filing_dir.name}",
			message=str(e)
		)
		return {
			"imported": 0,
			"updated": 0,
			"upgraded": 0,
			"skipped": 0,
			"error": f"{filing_dir.name}: {str(e)}"
		}


def extract_usgaap_data(instance) -> Optional[Dict]:
	"""
	Extract financial data from XBRL instance using US-GAAP taxonomy.
	
	Args:
		instance: Parsed XBRL instance
		
	Returns:
		Dict with extracted financial data or None
	"""
	try:
		# US-GAAP taxonomy mappings
		# These are the standard US-GAAP element names
		taxonomy_map = {
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
			"us-gaap:PaymentsOfDividends": "dividends_paid",
		}
		
		# Extract context information (period dates)
		contexts = getattr(instance, 'context', {})
		period_info = extract_period_info(contexts)
		
		if not period_info:
			return None
		
		# Extract facts from XBRL
		facts = getattr(instance, 'facts', {})
		financial_data = period_info.copy()
		
		for fact in facts:
			element_name = getattr(fact, 'concept', None)
			value = getattr(fact, 'value', None)
			
			if element_name in taxonomy_map and value is not None:
				our_field = taxonomy_map[element_name]
				try:
					financial_data[our_field] = float(value)
				except (ValueError, TypeError):
					continue
		
		# Calculate derived fields if not present
		if "gross_profit" not in financial_data:
			if "total_revenue" in financial_data and "cost_of_revenue" in financial_data:
				financial_data["gross_profit"] = financial_data["total_revenue"] - financial_data["cost_of_revenue"]
		
		if "capital_expenditures" in financial_data:
			# Capital expenditures are usually negative in cash flow, make positive
			financial_data["capital_expenditures"] = abs(financial_data["capital_expenditures"])
		
		# Calculate free cash flow if possible
		if "operating_cash_flow" in financial_data and "capital_expenditures" in financial_data:
			financial_data["free_cash_flow"] = financial_data["operating_cash_flow"] - financial_data["capital_expenditures"]
		
		return financial_data
		
	except Exception as e:
		frappe.log_error(
			title="US-GAAP Extraction Error",
			message=str(e)
		)
		return None


def extract_period_info(contexts) -> Optional[Dict]:
	"""
	Extract fiscal period information from XBRL contexts.
	
	Args:
		contexts: XBRL contexts object
		
	Returns:
		Dict with fiscal_year, fiscal_quarter, period_end_date or None
	"""
	try:
		# This is a simplified implementation
		# Real XBRL context parsing is more complex
		period_info = {}
		
		# Look for duration context (not instant/point-in-time)
		for context_id, context in contexts.items():
			period = getattr(context, 'period', None)
			if not period:
				continue
			
			end_date = getattr(period, 'end_date', None) or getattr(period, 'instant', None)
			
			if end_date:
				if isinstance(end_date, str):
					end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).date()
				elif isinstance(end_date, datetime):
					end_date = end_date.date()
				
				period_info["period_end_date"] = end_date
				period_info["fiscal_year"] = end_date.year
				
				# Determine quarter based on month
				month = end_date.month
				if month in [1, 2, 3]:
					period_info["fiscal_quarter"] = "Q1"
				elif month in [4, 5, 6]:
					period_info["fiscal_quarter"] = "Q2"
				elif month in [7, 8, 9]:
					period_info["fiscal_quarter"] = "Q3"
				else:
					period_info["fiscal_quarter"] = "Q4"
				
				break
		
		return period_info if period_info else None
		
	except Exception as e:
		frappe.log_error(
			title="Period Info Extraction Error",
			message=str(e)
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
