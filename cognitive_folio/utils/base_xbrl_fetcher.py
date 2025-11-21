"""
Base XBRL Fetcher for Regional Exchange Integration

Abstract base class for implementing XBRL-based financial data fetchers
for different regional stock exchanges. Provides common functionality
for downloading, parsing, and mapping XBRL filings to CF Financial Period.

Subclasses should implement exchange-specific downloading and endpoint logic.
"""

import frappe
import json
from abc import ABC, abstractmethod
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
try:
	from xbrl import XBRLParser
except ImportError:
	XBRLParser = None
from cognitive_folio.utils.taxonomy_mapper import TaxonomyMapper


class BaseXBRLFetcher(ABC):
	"""Abstract base class for regional XBRL fetchers"""
	
	def __init__(self, security_name: str, quality_score: int = 95):
		"""
		Initialize fetcher.
		
		Args:
			security_name: Name of the CF Security document
			quality_score: Data quality score for this source (default: 95)
		"""
		self.security_name = security_name
		self.security = frappe.get_doc("CF Security", security_name)
		self.quality_score = quality_score
		self.taxonomy_mapper = None  # Set by detect_taxonomy after parsing
		
		# Counters for reporting
		self.imported_count = 0
		self.updated_count = 0
		self.upgraded_count = 0
		self.skipped_count = 0
		self.errors = []
	
	@abstractmethod
	def get_filing_identifiers(self) -> Dict[str, str]:
		"""
		Get exchange-specific filing identifiers.
		
		Returns:
			Dict with identifiers needed to fetch filings (e.g., CIK, company number, etc.)
		
		Example:
			{'cik': '0000320193'} for SEC
			{'company_number': '00000006'} for UK Companies House
		"""
		pass
	
	@abstractmethod
	def download_filings(self, identifiers: Dict[str, str], filing_types: List[str]) -> Path:
		"""
		Download XBRL filings from the exchange.
		
		Args:
			identifiers: Dict of exchange-specific identifiers
			filing_types: List of filing types to download (e.g., ['10-K', '10-Q'])
			
		Returns:
			Path to directory containing downloaded filings
		"""
		pass
	
	@abstractmethod
	def get_filing_types(self) -> Dict[str, str]:
		"""
		Get mapping of filing types to period types.
		
		Returns:
			Dict mapping filing type to 'Annual' or 'Quarterly'
			
		Example:
			{'10-K': 'Annual', '10-Q': 'Quarterly'} for SEC
			{'Full-Accounts': 'Annual', 'Half-Yearly': 'Quarterly'} for UK
		"""
		pass
	
	def fetch_financials(self) -> Dict:
		"""
		Main entry point: Download and parse all filings.
		
		Returns:
			Dict with results and counts
		"""
		try:
			# Ensure parser is available
			if XBRLParser is None:
				return self._error_result("python-xbrl library not installed. Install with: bench pip install python-xbrl")
			# Get identifiers for this security
			identifiers = self.get_filing_identifiers()
			if not identifiers:
				return self._error_result("No filing identifiers found for this security")
			
			# Get filing types
			filing_type_map = self.get_filing_types()
			filing_types = list(filing_type_map.keys())
			
			# Download filings
			filings_path = self.download_filings(identifiers, filing_types)
			if not filings_path or not filings_path.exists():
				return self._error_result(f"No filings downloaded to {filings_path}")
			
			# Process each filing type
			for filing_type, period_type in filing_type_map.items():
				filing_dir = filings_path / filing_type
				if not filing_dir.exists():
					continue
				
				# Process all filings of this type
				for filing_subdir in sorted(filing_dir.iterdir(), reverse=True):
					if filing_subdir.is_dir():
						self._process_filing(filing_subdir, period_type, filing_type)
			
			frappe.db.commit()
			
			return {
				"success": True,
				"imported_count": self.imported_count,
				"updated_count": self.updated_count,
				"upgraded_count": self.upgraded_count,
				"skipped_count": self.skipped_count,
				"total_periods": self.imported_count + self.updated_count + self.upgraded_count,
				"errors": self.errors if self.errors else None,
				"data_source_used": self.get_data_source_name()
			}
			
		except Exception as e:
			frappe.log_error(
				title=f"{self.get_data_source_name()} Fetch Error: {self.security_name}",
				message=str(e)
			)
			return self._error_result(str(e))
	
	def _process_filing(self, filing_dir: Path, period_type: str, filing_type: str):
		"""Process a single XBRL filing"""
		try:
			# Find XBRL/HTML file
			xbrl_file = self._find_xbrl_file(filing_dir)
			if not xbrl_file:
				self.errors.append(f"No XBRL file found in {filing_dir.name}")
				self.skipped_count += 1
				return
			
			# Parse XBRL
			xbrl_parser = XBRLParser()
			xbrl = xbrl_parser.parse(str(xbrl_file))
			
			# Detect taxonomy and create mapper
			namespaces = self._extract_namespaces(xbrl)
			taxonomy = TaxonomyMapper.detect_taxonomy_from_namespace(namespaces)
			self.taxonomy_mapper = TaxonomyMapper(taxonomy)
			
			# Extract financial facts
			financial_data = self._extract_facts(xbrl, period_type)
			
			if not financial_data or "period_end_date" not in financial_data:
				self.errors.append(f"No valid financial data extracted from {filing_dir.name}")
				self.skipped_count += 1
				return
			
			# Create or update CF Financial Period
			result = self._create_or_update_period(financial_data, period_type, filing_dir, filing_type)
			
			self.imported_count += result["imported"]
			self.updated_count += result["updated"]
			self.upgraded_count += result["upgraded"]
			self.skipped_count += result["skipped"]
			
		except Exception as e:
			frappe.log_error(
				title=f"Filing Processing Error: {filing_dir.name}",
				message=str(e)
			)
			self.errors.append(f"{filing_dir.name}: {str(e)}")
			self.skipped_count += 1
	
	def _find_xbrl_file(self, filing_dir: Path) -> Optional[Path]:
		"""Find the primary XBRL document in a filing directory"""
		# Look for common patterns
		patterns = [
			"*primary-document*.html",
			"*primary-document*.htm",
			"*.html",
			"*.htm",
			"*.xbrl",
			"*.xml"
		]
		
		for pattern in patterns:
			files = list(filing_dir.glob(pattern))
			if files:
				return files[0]
		
		return None
	
	def _extract_namespaces(self, xbrl) -> Dict[str, str]:
		"""Extract namespace mappings from XBRL document"""
		namespaces = {}
		try:
			# BeautifulSoup-based extraction
			if hasattr(xbrl, 'find_all'):
				root = xbrl if xbrl.name else xbrl.find()
				if root and hasattr(root, 'attrs'):
					for attr, value in root.attrs.items():
						if attr.startswith('xmlns'):
							prefix = attr.split(':', 1)[1] if ':' in attr else 'default'
							namespaces[prefix] = value
		except:
			pass
		
		return namespaces
	
	def _extract_facts(self, xbrl, period_type: str) -> Optional[Dict]:
		"""
		Extract financial facts from XBRL document.
		
		Args:
			xbrl: Parsed XBRL document
			period_type: 'Annual' or 'Quarterly'
			
		Returns:
			Dict with extracted financial data
		"""
		try:
			# Find contexts (reporting periods)
			contexts = xbrl.find_all('xbrli:context')
			if not contexts:
				contexts = xbrl.find_all('context')
			
			if not contexts:
				return None
			
			# Find the most recent duration context
			period_context_id, period_end_date, period_start_date = self._find_latest_context(contexts)
			
			if not period_context_id:
				return None
			
			# Extract financial facts using taxonomy mapper
			financial_data = {}
			
			# Get all numeric facts with the target context
			facts = xbrl.find_all(attrs={'contextref': period_context_id})
			
			for fact in facts:
				concept_name = fact.get('name') or fact.name
				if not concept_name:
					continue
				
				# Map to our field
				our_field = self.taxonomy_mapper.map_concept(concept_name)
				if not our_field:
					continue
				
				# Extract value
				value_text = fact.text.strip() if fact.text else None
				if not value_text:
					continue
				
				try:
					value = float(value_text.replace(',', ''))
					
					# Handle scale/decimals
					decimals = fact.get('decimals', '')
					scale = fact.get('scale', '')
					
					if scale:
						value = value * (10 ** int(scale))
					elif decimals and decimals.startswith('-'):
						value = value * (10 ** int(decimals))
					
					financial_data[our_field] = value
				except (ValueError, TypeError):
					continue
			
			if not financial_data:
				return None
			
			# Add period metadata
			financial_data["period_end_date"] = period_end_date
			financial_data["fiscal_year"] = period_end_date.year
			
			# Determine quarter
			if period_type == "Quarterly":
				month = period_end_date.month
				quarters = {1: "Q1", 2: "Q1", 3: "Q1", 4: "Q2", 5: "Q2", 6: "Q2",
				           7: "Q3", 8: "Q3", 9: "Q3", 10: "Q4", 11: "Q4", 12: "Q4"}
				financial_data["fiscal_quarter"] = quarters.get(month, "Q4")
			
			# Calculate derived metrics
			self._calculate_derived_metrics(financial_data)
			
			return financial_data
			
		except Exception as e:
			frappe.log_error(
				title="XBRL Fact Extraction Error",
				message=f"Error: {str(e)}\n{frappe.get_traceback()}"
			)
			return None
	
	def _find_latest_context(self, contexts) -> Tuple[Optional[str], Optional[date], Optional[date]]:
		"""Find the most recent duration context from XBRL contexts"""
		period_context_id = None
		period_end_date = None
		period_start_date = None
		
		for ctx in contexts:
			period = ctx.find('xbrli:period') or ctx.find('period')
			if not period:
				continue
			
			# Look for duration (not instant)
			start = period.find('xbrli:startdate') or period.find('startdate')
			end = period.find('xbrli:enddate') or period.find('enddate')
			
			if start and end:
				try:
					end_date = datetime.fromisoformat(end.text.strip()).date()
					start_date = datetime.fromisoformat(start.text.strip()).date()
					
					if not period_end_date or end_date > period_end_date:
						period_end_date = end_date
						period_start_date = start_date
						period_context_id = ctx.get('id')
				except:
					continue
		
		return period_context_id, period_end_date, period_start_date
	
	def _calculate_derived_metrics(self, financial_data: Dict):
		"""Calculate derived financial metrics"""
		# Gross profit
		if "gross_profit" not in financial_data and "total_revenue" in financial_data and "cost_of_revenue" in financial_data:
			financial_data["gross_profit"] = financial_data["total_revenue"] - financial_data["cost_of_revenue"]
		
		# Ensure capex is positive
		if "capital_expenditures" in financial_data:
			financial_data["capital_expenditures"] = abs(financial_data["capital_expenditures"])
		
		# Free cash flow
		if "operating_cash_flow" in financial_data and "capital_expenditures" in financial_data:
			financial_data["free_cash_flow"] = financial_data["operating_cash_flow"] - financial_data["capital_expenditures"]
	
	def _create_or_update_period(self, financial_data: Dict, period_type: str, filing_dir: Path, filing_type: str) -> Dict:
		"""Create or update CF Financial Period document"""
		fiscal_year = financial_data.get("fiscal_year")
		fiscal_quarter = financial_data.get("fiscal_quarter") if period_type == "Quarterly" else None
		period_end_date = financial_data.get("period_end_date")
		
		# Check for existing period
		filters = {
			"security": self.security.name,
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
		
		# Skip if override flag set
		if existing and existing.override_yahoo:
			return {"imported": 0, "updated": 0, "upgraded": 0, "skipped": 1}
		
		# Determine operation type
		is_upgrade = False
		is_update = False
		
		if existing:
			if existing.data_quality_score < self.quality_score:
				is_upgrade = True
				period = frappe.get_doc("CF Financial Period", existing.name)
			elif existing.data_quality_score >= self.quality_score:
				return {"imported": 0, "updated": 0, "upgraded": 0, "skipped": 1}
			else:
				is_update = True
				period = frappe.get_doc("CF Financial Period", existing.name)
		else:
			period = frappe.new_doc("CF Financial Period")
			period.security = self.security.name
			period.period_type = period_type
			period.fiscal_year = fiscal_year
			if fiscal_quarter:
				period.fiscal_quarter = fiscal_quarter
			period.period_end_date = period_end_date
		
		# Set metadata
		period.data_source = self.get_data_source_name()
		period.data_quality_score = self.quality_score
		period.currency = self.security.currency or "USD"
		
		# Map financial data to period fields
		self._map_data_to_period(period, financial_data)
		
		# Store raw data reference
		period.raw_income_statement = json.dumps({
			"source": f"{self.get_data_source_name()} XBRL",
			"filing": filing_dir.name,
			"filing_type": filing_type,
			"taxonomy": self.taxonomy_mapper.taxonomy if self.taxonomy_mapper else "Unknown"
		}, indent=2)
		
		period.save()
		
		if is_upgrade:
			return {"imported": 0, "updated": 0, "upgraded": 1, "skipped": 0}
		elif is_update:
			return {"imported": 0, "updated": 1, "upgraded": 0, "skipped": 0}
		else:
			return {"imported": 1, "updated": 0, "upgraded": 0, "skipped": 0}
	
	def _map_data_to_period(self, period, financial_data: Dict):
		"""Map extracted financial data to CF Financial Period fields"""
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
	
	def _error_result(self, error_message: str) -> Dict:
		"""Return standardized error result"""
		return {
			"success": False,
			"error": error_message,
			"imported_count": 0,
			"updated_count": 0,
			"upgraded_count": 0,
			"skipped_count": 0,
			"data_source_used": self.get_data_source_name()
		}
	
	@abstractmethod
	def get_data_source_name(self) -> str:
		"""
		Get the display name for this data source.
		
		Returns:
			String like "SEC Edgar", "Companies House", etc.
		"""
		pass
