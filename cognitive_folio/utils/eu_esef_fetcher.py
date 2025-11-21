"""
EU ESEF (European Single Electronic Format) XBRL Data Fetcher

Downloads and parses ESEF/IFRS XBRL accounts from European national regulators
for major EU exchanges: Germany (GER), France (PAR), Netherlands (AMS), 
Italy (MIL), and Spain (MCE).

ESEF became mandatory in EU from 2020 onwards for listed companies.
Each country has its own official filing repository (OAM - Officially Appointed Mechanism).

Implementation Strategy:
- Germany (BaFin/Bundesanzeiger): Use https://www.bundesanzeiger.de API
- France (AMF): Use https://www.amf-france.org or ESMA FIRDS
- Netherlands (AFM): Use https://www.afm.nl or local OAM
- Italy (CONSOB): Use https://www.consob.it or local OAM  
- Spain (CNMV): Use https://www.cnmv.es or local OAM

For Phase 3 MVP, we'll implement a unified approach using ESMA's public ESEF database
which aggregates filings from all EU regulators.
"""

from pathlib import Path
from typing import Dict, List, Optional
import json
import requests
import frappe
from datetime import datetime, timedelta

from cognitive_folio.utils.base_xbrl_fetcher import BaseXBRLFetcher


class EUESEFFetcher(BaseXBRLFetcher):
	"""Fetcher for EU ESEF/IFRS XBRL accounts"""

	# ESMA ESEF public database (aggregates all EU filings)
	# Note: This is a placeholder - actual implementation would use proper ESMA API or national OAMs
	ESMA_FIRRDS_API = "https://registers.esma.europa.eu/solr/esma_registers_firds_files"
	
	# National regulator endpoints (for future direct integration)
	NATIONAL_ENDPOINTS = {
		"DE": "https://www.bundesanzeiger.de",  # Germany - BaFin/Bundesanzeiger
		"FR": "https://www.amf-france.org",      # France - AMF
		"NL": "https://www.afm.nl",              # Netherlands - AFM
		"IT": "https://www.consob.it",           # Italy - CONSOB
		"ES": "https://www.cnmv.es"              # Spain - CNMV
	}
	
	# Map stock exchange codes to country codes
	EXCHANGE_TO_COUNTRY = {
		"GER": "DE",  # Germany (XETRA, Frankfurt)
		"PAR": "FR",  # France (Euronext Paris)
		"AMS": "NL",  # Netherlands (Euronext Amsterdam)
		"MIL": "IT",  # Italy (Borsa Italiana)
		"MCE": "ES"   # Spain (Bolsa de Madrid)
	}

	def get_data_source_name(self) -> str:
		return "EU ESEF"

	def get_filing_identifiers(self) -> Dict[str, str]:
		"""
		Get identifiers needed to fetch EU filings.
		
		Returns:
			Dict with ISIN, LEI, or company registration number
		"""
		identifiers = {}
		
		# ISIN is the primary identifier for EU securities
		if hasattr(self.security, 'isin') and self.security.isin:
			identifiers['isin'] = self.security.isin
		
		# Stock exchange to determine country
		if hasattr(self.security, 'stock_exchange') and self.security.stock_exchange:
			exchange = self.security.stock_exchange.upper()
			if exchange in self.EXCHANGE_TO_COUNTRY:
				identifiers['country'] = self.EXCHANGE_TO_COUNTRY[exchange]
		
		# Company name as fallback
		if hasattr(self.security, 'security_name') and self.security.security_name:
			identifiers['company_name'] = self.security.security_name
		
		# Symbol for searching
		if hasattr(self.security, 'symbol') and self.security.symbol:
			identifiers['symbol'] = self.security.symbol
		
		return identifiers

	def get_filing_types(self) -> Dict[str, str]:
		"""
		Get mapping of EU filing types to period types.
		
		EU ESEF requires:
		- Annual Financial Report (mandatory from 2020)
		- Half-yearly reports (optional but common)
		"""
		return {
			"Annual": "Annual",
			# Quarterly/Half-yearly ESEF adoption is still evolving
			# "Half-Yearly": "Quarterly"
		}

	def download_filings(self, identifiers: Dict[str, str], filing_types: List[str]) -> Path:
		"""
		Download ESEF XBRL filings from national regulators or ESMA.
		
		Phase 3 MVP Strategy:
		Since direct API access to each national regulator requires:
		- Different authentication methods per country
		- Country-specific search APIs
		- Legal/compliance registration in some cases
		
		We'll implement a phased approach:
		1. MVP: Manual download directory structure (user provides files)
		2. Future: Direct API integration per country
		3. Future: ESMA aggregated database once publicly accessible
		
		For now, we expect ESEF files to be manually placed in:
		sites/private/files/eu_esef/<ISIN>/Annual/<filing_date>/report.xhtml
		"""
		
		isin = identifiers.get('isin')
		country = identifiers.get('country', 'EU')
		
		if not isin:
			raise RuntimeError("ISIN required for EU ESEF filing downloads. Set ISIN on CF Security.")
		
		# Base directory for EU ESEF filings
		base_dir = Path(frappe.get_site_path("private", "files", "eu_esef", isin))
		base_dir.mkdir(parents=True, exist_ok=True)
		
		# Check if manual files exist
		annual_dir = base_dir / "Annual"
		if annual_dir.exists() and any(annual_dir.iterdir()):
			frappe.msgprint(
				f"Using manually uploaded ESEF files for {isin}",
				alert=True,
				indicator='blue'
			)
			return base_dir
		
		# Future: Implement automated download from national regulators
		# For now, log that manual upload is expected
		frappe.msgprint(
			f"No ESEF filings found for {isin}. Please upload XBRL files to: {annual_dir}",
			alert=True,
			indicator='orange'
		)
		
		# Create placeholder structure to guide manual uploads
		annual_dir.mkdir(parents=True, exist_ok=True)
		readme = annual_dir / "README.txt"
		if not readme.exists():
			readme.write_text(
				f"EU ESEF XBRL Filing Directory for ISIN: {isin}\n\n"
				f"Upload annual ESEF XHTML/XML reports here in the following structure:\n"
				f"  YYYY-MM-DD/\n"
				f"    report.xhtml  (or .xml)\n"
				f"    [additional supporting files]\n\n"
				f"ESEF reports can be downloaded from national regulators:\n"
				f"  Germany: https://www.bundesanzeiger.de\n"
				f"  France: https://www.amf-france.org\n"
				f"  Netherlands: https://www.afm.nl\n"
				f"  Italy: https://www.consob.it\n"
				f"  Spain: https://www.cnmv.es\n\n"
				f"Look for 'ESEF', 'iXBRL', or 'Annual Financial Report' filings.\n"
			)
		
		return base_dir

	def _find_xbrl_file(self, filing_dir: Path) -> Optional[Path]:
		"""Find the primary ESEF XBRL document"""
		# ESEF typically uses .xhtml extension for iXBRL
		patterns = [
			"*.xhtml",
			"*report*.xhtml",
			"*esef*.xhtml",
			"*.html",
			"*.htm",
			"*.xml",
			"*instance*.xml"
		]
		
		for pattern in patterns:
			files = list(filing_dir.glob(pattern))
			if files:
				# Prefer files with 'report' or 'esef' in name
				for f in files:
					name_lower = f.name.lower()
					if 'report' in name_lower or 'esef' in name_lower or 'instance' in name_lower:
						return f
				# Otherwise return first match
				return files[0]
		
		return None


def fetch_eu_esef_financials(security_name: str) -> Dict:
	"""Public function to fetch EU ESEF accounts for a security"""
	fetcher = EUESEFFetcher(security_name, quality_score=95)
	return fetcher.fetch_financials()


# Helper function to download ESEF from specific national regulator
def download_from_bundesanzeiger(isin: str, company_name: str) -> Optional[Path]:
	"""
	Download ESEF filings from German Bundesanzeiger (placeholder for future implementation).
	
	Args:
		isin: Company ISIN
		company_name: Company name for searching
		
	Returns:
		Path to downloaded filing or None
		
	Note: Requires Bundesanzeiger API access or web scraping implementation
	"""
	# TODO: Implement Bundesanzeiger search and download
	# The official API requires registration and authentication
	# Alternative: Use their public search portal with requests/selenium
	frappe.log_error(
		title="Bundesanzeiger Download Not Implemented",
		message=f"Automated download from Bundesanzeiger not yet available. ISIN: {isin}"
	)
	return None


def download_from_amf_france(isin: str, company_name: str) -> Optional[Path]:
	"""
	Download ESEF filings from French AMF (placeholder for future implementation).
	
	Note: AMF provides public access to filings through their website
	"""
	# TODO: Implement AMF search and download
	frappe.log_error(
		title="AMF Download Not Implemented",
		message=f"Automated download from AMF not yet available. ISIN: {isin}"
	)
	return None


# Export country-specific downloaders for future use
COUNTRY_DOWNLOADERS = {
	"DE": download_from_bundesanzeiger,
	"FR": download_from_amf_france,
	# Add more as implemented
}
