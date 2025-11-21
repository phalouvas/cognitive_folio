"""
Switzerland SIX Swiss Exchange XBRL Fetcher

This module fetches Swiss XBRL financial statements for companies listed on the SIX Swiss Exchange (EBS).

Data Source: SIX Exchange Regulation - e-Reporting Platform
Website: https://www.ser-ag.com/en/resources/notifications-market-participants/e-reporting.html
Access: Manual download (no public API)

Swiss Financial Reporting:
- Swiss listed companies file annual reports through the e-reporting platform
- XBRL filings use Swiss GAAP FER or IFRS taxonomy
- Files distributed by SIX Exchange Regulation (SER-AG)
- Public access through SIX website requires manual navigation

Implementation Approach:
Since SIX Swiss Exchange does not provide a public REST API for programmatic access:
1. Manual file upload by users following structured directory convention
2. This module parses the uploaded XBRL files using the taxonomy mapper
3. Extracted financial data creates CF Financial Period records (quality score 95)

Directory Structure (manual upload):
sites/private/files/six/<isin>/Annual/<YYYY-MM-DD>/
  report.xhtml  (or report.xml)

Example:
sites/private/files/six/CH0038863350/Annual/2023-12-31/
  report.xhtml  # Nestlé 2023 annual report

Swiss-Specific Notes:
- ISIN (Swiss Securities Number): CH + 10 digits (e.g., CH0038863350)
- Many Swiss companies use IFRS for consolidated financials
- Some use Swiss GAAP FER (Swiss accounting standard)
- Currency: CHF (Swiss Franc)

Author: Cognitive Folio Development Team
"""

import os
import frappe
from frappe import _
from datetime import datetime
from pathlib import Path
from cognitive_folio.utils.base_xbrl_fetcher import BaseXBRLFetcher


class SIXFetcher(BaseXBRLFetcher):
    """
    Fetcher for Switzerland SIX Swiss Exchange XBRL filings (manual upload mode).
    
    Handles Swiss companies listed on the SIX Swiss Exchange (stock_exchange = 'EBS').
    Expects XBRL files in sites/private/files/six/<isin>/Annual/<date>/report.xhtml
    
    Workflow:
    1. Extract ISIN from CF Security
    2. Search manual upload directory: sites/private/files/six/<isin>/Annual/
    3. Parse XBRL files using taxonomy mapper (IFRS or Swiss GAAP FER)
    4. Create CF Financial Period records (quality score 95)
    5. Fall back to Yahoo Finance if no files or parsing errors
    """
    
    def __init__(self, security_doc):
        """
        Initialize SIX fetcher.
        
        Args:
            security_doc: CF Security document
        """
        super().__init__(security_doc)
        self.isin = security_doc.isin
        
        if not self.isin:
            frappe.throw(_("ISIN is required for Switzerland SIX Swiss Exchange securities. Please add ISIN to CF Security: {0}").format(security_doc.name))
        
        # Validate ISIN format (CH + 10 digits)
        if not (self.isin.startswith("CH") and len(self.isin) == 12 and self.isin[2:].isdigit()):
            frappe.log_error(
                title="Invalid Swiss ISIN Format",
                message=f"ISIN {self.isin} for security {security_doc.name} does not match Swiss format (CH + 10 digits)"
            )
    
    def fetch_filings(self):
        """
        Fetch available XBRL filings for this Swiss security.
        
        Manual upload mode: Scans sites/private/files/six/<isin>/Annual/ for XHTML/XML files.
        
        Returns:
            list: List of dicts with 'filing_date' (datetime) and 'file_path' (str)
        """
        private_files_path = frappe.get_site_path("private", "files")
        six_base = os.path.join(private_files_path, "six", self.isin, "Annual")
        
        if not os.path.exists(six_base):
            frappe.msgprint(
                _("No manual uploads found for Swiss ISIN {0}. Please upload XBRL files to: {1}").format(
                    self.isin, 
                    f"sites/private/files/six/{self.isin}/Annual/<YYYY-MM-DD>/report.xhtml"
                ),
                indicator="orange"
            )
            return []
        
        filings = []
        
        # Iterate through date directories (e.g., 2023-12-31/)
        for date_dir in os.listdir(six_base):
            date_path = os.path.join(six_base, date_dir)
            if not os.path.isdir(date_path):
                continue
            
            # Parse date from directory name
            try:
                filing_date = datetime.strptime(date_dir, "%Y-%m-%d")
            except ValueError:
                frappe.log_error(
                    title="Invalid SIX Date Directory",
                    message=f"Directory {date_dir} does not match expected YYYY-MM-DD format"
                )
                continue
            
            # Look for report.xhtml or report.xml
            for filename in ["report.xhtml", "report.xml"]:
                file_path = os.path.join(date_path, filename)
                if os.path.exists(file_path):
                    filings.append({
                        "filing_date": filing_date,
                        "file_path": file_path
                    })
                    break  # Use first found file
        
        if not filings:
            frappe.msgprint(
                _("No XBRL files found in {0}. Expected files: report.xhtml or report.xml").format(six_base),
                indicator="orange"
            )
        
        return sorted(filings, key=lambda x: x["filing_date"], reverse=True)
    
    def download_xbrl(self, filing):
        """
        'Download' XBRL file (actually just return local file path for manual uploads).
        
        Args:
            filing: Dict with 'file_path' key
            
        Returns:
            str: Local file path to XBRL file
        """
        return filing["file_path"]
    
    def get_identifier(self):
        """
        Get Swiss company identifier for error messages and logging.
        
        Returns:
            str: ISIN (e.g., "CH0038863350")
        """
        return self.isin


def fetch_six_financials(security_name):
    """
    Main entry point: Fetch Swiss XBRL financials for a security.
    
    Called by CF Security when stock_exchange = 'EBS' (SIX Swiss Exchange).
    
    Workflow:
    1. Load CF Security document
    2. Validate ISIN exists
    3. Initialize SIXFetcher
    4. Call process_filings() (inherited from BaseXBRLFetcher)
    5. Create CF Financial Period records for parsed data
    
    Args:
        security_name: Name of the CF Security document
        
    Returns:
        dict: Summary with 'success', 'periods_created', 'source', 'message'
    """
    try:
        security_doc = frappe.get_doc("CF Security", security_name)
        
        if not security_doc.isin:
            return {
                "success": False,
                "message": _("ISIN is required for Switzerland SIX Swiss Exchange. Please add ISIN to CF Security: {0}").format(security_name),
                "source": "SIX Error"
            }
        
        fetcher = SIXFetcher(security_doc)
        result = fetcher.process_filings()
        
        if result["success"]:
            frappe.msgprint(
                _("Successfully imported {0} financial period(s) from Switzerland SIX XBRL for {1}").format(
                    result.get("periods_created", 0),
                    security_name
                ),
                indicator="green"
            )
        
        return result
        
    except Exception as e:
        frappe.log_error(
            title="SIX XBRL Fetch Error",
            message=f"Error fetching Swiss financials for {security_name}: {str(e)}"
        )
        return {
            "success": False,
            "message": str(e),
            "source": "SIX Error"
        }


def download_six_with_playwright():
    """
    Optional: Automate downloading Swiss XBRL files using Playwright.
    
    NOTE: This is a placeholder for future implementation.
    SIX Exchange Regulation e-reporting platform may require authentication
    and does not have a simple public download interface like HKEX.
    
    For now, manual download is recommended:
    1. Visit https://www.six-exchange-regulation.com/en/home/publications/significant-shareholders.html
    2. Navigate to company disclosures
    3. Download annual report XBRL files
    4. Place in sites/private/files/six/<isin>/Annual/<YYYY-MM-DD>/report.xhtml
    
    Future Enhancement:
    - Implement Playwright automation if clear download patterns are identified
    - Consider scraping SIX company pages for direct XBRL links
    - May require handling Swiss-specific authentication/captchas
    
    Raises:
        NotImplementedError: This function is not yet implemented
    """
    raise NotImplementedError(
        "Playwright automation for SIX Swiss Exchange is not yet implemented. "
        "Please download XBRL files manually from the SIX website and place them in "
        "sites/private/files/six/<isin>/Annual/<YYYY-MM-DD>/report.xhtml"
    )
