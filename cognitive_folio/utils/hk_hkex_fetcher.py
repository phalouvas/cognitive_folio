"""
Hong Kong HKEX XBRL Data Fetcher

Downloads and parses HKFRS (Hong Kong Financial Reporting Standards) XBRL accounts
from Hong Kong Stock Exchange (HKEX) for HKG-listed companies.

HKEX does not provide a public API. Financial reports are available through:
- HKEXnews portal: https://www1.hkexnews.hk
- Search by stock code, company name, or document type

Implementation Strategy:
- Manual upload mode (MVP): Users download XBRL from HKEXnews and place in directory
- Optional automation: Playwright/Selenium script for batch downloads (future)

HKFRS is based on IFRS with local modifications, so we use IFRS/HKFRS taxonomy mapper.
"""

from pathlib import Path
from typing import Dict, List, Optional
import frappe

from cognitive_folio.utils.base_xbrl_fetcher import BaseXBRLFetcher


class HKEXFetcher(BaseXBRLFetcher):
	"""Fetcher for Hong Kong HKEX XBRL accounts"""

	HKEXNEWS_URL = "https://www1.hkexnews.hk"
	HKEXNEWS_SEARCH = "https://www1.hkexnews.hk/search/titlesearch.xhtml"

	def get_data_source_name(self) -> str:
		return "HKEX"

	def get_filing_identifiers(self) -> Dict[str, str]:
		"""
		Get identifiers needed to fetch HKEX filings.
		
		Returns:
			Dict with stock_code (HKEX numeric code like "0700", "0005")
		"""
		identifiers = {}
		
		# HKEX stock code - numeric code with leading zeros
		# Can be stored in a custom field or derived from symbol
		if hasattr(self.security, 'hk_stock_code') and self.security.hk_stock_code:
			identifiers['stock_code'] = self.security.hk_stock_code
		elif hasattr(self.security, 'symbol') and self.security.symbol:
			# Try to extract from symbol (e.g., "0700.HK" -> "0700")
			symbol = self.security.symbol
			if '.HK' in symbol.upper():
				code = symbol.upper().split('.HK')[0]
				identifiers['stock_code'] = code.zfill(4)  # Pad to 4 digits
		
		# Company name for reference
		if hasattr(self.security, 'security_name') and self.security.security_name:
			identifiers['company_name'] = self.security.security_name
		
		return identifiers

	def get_filing_types(self) -> Dict[str, str]:
		"""
		Get mapping of HKEX filing types to period types.
		
		HKEX filings:
		- Annual Report (mandatory)
		- Interim Report (half-yearly, common)
		- Quarterly reports (less common)
		"""
		return {
			"Annual": "Annual",
			# Half-yearly can be added when needed
			# "Interim": "Quarterly"
		}

	def download_filings(self, identifiers: Dict[str, str], filing_types: List[str]) -> Path:
		"""
		Download HKEX XBRL filings.
		
		Phase 3 MVP Strategy:
		Manual upload mode - users download from HKEXnews and place files in:
		sites/private/files/hkex/<stock_code>/Annual/<filing_date>/report.xhtml
		
		Future enhancement: Automated download using Playwright/Selenium
		"""
		
		stock_code = identifiers.get('stock_code')
		company_name = identifiers.get('company_name', 'Unknown')
		
		if not stock_code:
			raise RuntimeError(
				"HK stock code required for HKEX filing downloads. "
				"Set symbol like '0700.HK' or add 'hk_stock_code' field to CF Security."
			)
		
		# Base directory for HKEX filings
		base_dir = Path(frappe.get_site_path("private", "files", "hkex", stock_code))
		base_dir.mkdir(parents=True, exist_ok=True)
		
		# Check if manual files exist
		annual_dir = base_dir / "Annual"
		if annual_dir.exists() and any(annual_dir.iterdir()):
			frappe.msgprint(
				f"Using manually uploaded HKEX files for {stock_code} ({company_name})",
				alert=True,
				indicator='blue'
			)
			return base_dir
		
		# No files found - provide guidance for manual upload
		frappe.msgprint(
			f"No HKEX filings found for {stock_code}. Please upload XBRL files to: {annual_dir}",
			alert=True,
			indicator='orange'
		)
		
		# Create placeholder structure to guide manual uploads
		annual_dir.mkdir(parents=True, exist_ok=True)
		readme = annual_dir / "README.txt"
		if not readme.exists():
			readme.write_text(
				f"HKEX XBRL Filing Directory for Stock Code: {stock_code}\n"
				f"Company: {company_name}\n\n"
				f"Upload annual HKFRS XHTML/XML reports here in the following structure:\n"
				f"  YYYY-MM-DD/\n"
				f"    report.xhtml  (or .xml)\n"
				f"    [additional supporting files]\n\n"
				f"HKFRS (XBRL) reports can be downloaded from:\n"
				f"  HKEXnews: {self.HKEXNEWS_SEARCH}\n\n"
				f"Search Instructions:\n"
				f"  1. Go to {self.HKEXNEWS_SEARCH}\n"
				f"  2. Enter stock code: {stock_code}\n"
				f"  3. Select 'Financial Statements/ESG Information'\n"
				f"  4. Look for 'Annual Report' or documents with XBRL attachments\n"
				f"  5. Download the XBRL/iXBRL file (usually .xhtml or .xml extension)\n"
				f"  6. Create a folder named YYYY-MM-DD (report date) here\n"
				f"  7. Place the downloaded file as 'report.xhtml' in that folder\n\n"
				f"Example structure:\n"
				f"  2024-12-31/\n"
				f"    report.xhtml\n"
				f"  2023-12-31/\n"
				f"    report.xhtml\n\n"
				f"Note: HKEX filings are in HKFRS (Hong Kong IFRS) format.\n"
			)
		
		return base_dir

	def _find_xbrl_file(self, filing_dir: Path) -> Optional[Path]:
		"""Find the primary HKEX XBRL document"""
		# HKEX typically uses .xhtml or .xml for XBRL filings
		patterns = [
			"*.xhtml",
			"*report*.xhtml",
			"*financial*.xhtml",
			"*.html",
			"*.htm",
			"*.xml",
			"*instance*.xml"
		]
		
		for pattern in patterns:
			files = list(filing_dir.glob(pattern))
			if files:
				# Prefer files with 'report' or 'financial' in name
				for f in files:
					name_lower = f.name.lower()
					if 'report' in name_lower or 'financial' in name_lower or 'instance' in name_lower:
						return f
				# Otherwise return first match
				return files[0]
		
		return None


def fetch_hkex_financials(security_name: str) -> Dict:
	"""Public function to fetch HKEX accounts for a security"""
	fetcher = HKEXFetcher(security_name, quality_score=95)
	return fetcher.fetch_financials()


# Optional: Helper function for future automated download
def download_hkex_with_playwright(stock_code: str, output_dir: Path) -> bool:
	"""
	Download HKEX filings using Playwright automation (future enhancement).
	
	Args:
		stock_code: HKEX stock code (e.g., "0700")
		output_dir: Directory to save downloaded files
		
	Returns:
		True if successful, False otherwise
		
	Note: Requires playwright installation: pip install playwright; playwright install chromium
	"""
	try:
		from playwright.sync_api import sync_playwright
		
		with sync_playwright() as p:
			browser = p.chromium.launch(headless=True)
			page = browser.new_page()
			
			# Navigate to HKEXnews search
			page.goto("https://www1.hkexnews.hk/search/titlesearch.xhtml")
			
			# Enter stock code
			page.fill('input[name="searchType"]', stock_code)
			
			# Select Financial Statements category
			page.click('text=Financial Statements')
			
			# Click search
			page.click('button[type="submit"]')
			
			# Wait for results
			page.wait_for_selector('.search-result')
			
			# Find and download XBRL files
			xbrl_links = page.query_selector_all('a[href*=".xhtml"], a[href*=".xml"]')
			
			for link in xbrl_links[:5]:  # Limit to 5 most recent
				href = link.get_attribute('href')
				if href:
					# Download the file
					download = page.expect_download()
					link.click()
					download_obj = download.value
					
					# Save to output directory
					file_path = output_dir / download_obj.suggested_filename
					download_obj.save_as(file_path)
			
			browser.close()
			return True
			
	except ImportError:
		frappe.log_error(
			title="Playwright Not Installed",
			message="Automated HKEX download requires Playwright. Install with: pip install playwright"
		)
		return False
	except Exception as e:
		frappe.log_error(
			title="HKEX Download Error",
			message=f"Error downloading from HKEX for {stock_code}: {str(e)}"
		)
		return False
