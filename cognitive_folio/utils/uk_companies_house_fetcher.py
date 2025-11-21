"""
UK Companies House XBRL Data Fetcher

Downloads and parses iXBRL/XBRL accounts filed with UK Companies House
for LSE/IOB-listed companies, mapping financials into CF Financial Periods.

Requires a Companies House API key configured in Frappe config as
`companies_house_api_key`.
"""

from pathlib import Path
from typing import Dict, List, Optional
import os
import json
import requests
import frappe

from cognitive_folio.utils.base_xbrl_fetcher import BaseXBRLFetcher


class UKCompaniesHouseFetcher(BaseXBRLFetcher):
    """Fetcher for UK Companies House iXBRL accounts"""

    BASE_API = "https://api.company-information.service.gov.uk"
    DOCUMENT_API = "https://document-api.company-information.service.gov.uk"

    def get_data_source_name(self) -> str:
        return "UK Companies House"

    def get_filing_identifiers(self) -> Dict[str, str]:
        company_number = getattr(self.security, 'companies_house_number', None)
        if not company_number:
            return {}
        return {"company_number": company_number}

    def get_filing_types(self) -> Dict[str, str]:
        # Focus on Annual accounts first; UK interim accounts are less consistently available as iXBRL
        return {
            "Full-Accounts": "Annual",
            # Additional types we may support later (commented for now)
            # "Interim-Accounts": "Quarterly",
            # "Half-Yearly": "Quarterly",
            # "Small-Full": "Annual"
        }

    def download_filings(self, identifiers: Dict[str, str], filing_types: List[str]) -> Path:
        api_key = frappe.conf.get("companies_house_api_key") if hasattr(frappe, 'conf') else None
        if not api_key:
            raise RuntimeError("Missing Companies House API key. Set 'companies_house_api_key' in site config.")

        company_number = identifiers["company_number"]
        base_dir = Path(frappe.get_site_path("private", "files", "companies_house", company_number))
        base_dir.mkdir(parents=True, exist_ok=True)

        # Fetch filing history limited to accounts category
        url = f"{self.BASE_API}/company/{company_number}/filing-history"
        params = {"category": "accounts", "items_per_page": 50}
        resp = requests.get(url, auth=(api_key, ""), params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Companies House API error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        items = data.get("items", [])
        if not items:
            return base_dir

        # Known account types to prefer for annual filings
        preferred_types = {
            "AA": "Full-Accounts",            # Full accounts
            "F1": "Full-Accounts",            # Full accounts (alt code)
            "AA01": "Full-Accounts",         # Previous accounts
            "DCAA": "Full-Accounts",         # Dormant company accounts
            "QFIS": "Full-Accounts",         # Accounts (generic)
            # Interim variants could be mapped to Quarterly later
        }

        for item in items:
            try:
                doc_type_code = item.get("type")
                mapped_type = preferred_types.get(doc_type_code)
                if not mapped_type or mapped_type not in filing_types:
                    continue

                links = item.get("links", {})
                meta_url = links.get("document_metadata")
                if not meta_url:
                    # Some filings don't expose metadata; skip
                    continue

                # Retrieve document metadata to find available formats
                meta_resp = requests.get(meta_url, auth=(api_key, ""), timeout=30)
                if meta_resp.status_code != 200:
                    continue
                meta = meta_resp.json()

                # Prefer application/xhtml+xml (iXBRL) or text/html
                resources = meta.get("resources", {})
                resource_key = None
                if "application/xhtml+xml" in resources:
                    resource_key = "application/xhtml+xml"
                elif "text/html" in resources:
                    resource_key = "text/html"
                elif "application/xml" in resources or "application/xbrl+xml" in resources:
                    resource_key = "application/xml" if "application/xml" in resources else "application/xbrl+xml"
                else:
                    continue

                res = resources[resource_key]
                doc_url = res.get("uri") or res.get("url") or res.get("links", {}).get("self")
                if not doc_url:
                    # Build from document ID if present
                    doc_id = meta.get("id") or meta.get("document_id")
                    if doc_id:
                        doc_url = f"{self.DOCUMENT_API}/document/{doc_id}"
                    else:
                        continue

                # Append format if required by the document API
                if self.DOCUMENT_API in doc_url and resource_key:
                    # Request the correct rendition
                    headers = {"Accept": resource_key}
                else:
                    headers = {}

                # Prepare destination path structure: <base>/<FilingType>/<transaction_id>/primary-document.html
                filing_type_dir = base_dir / mapped_type
                filing_type_dir.mkdir(parents=True, exist_ok=True)
                txn_id = item.get("transaction_id") or item.get("barcode") or item.get("date")
                if not txn_id:
                    # Fallback to an index
                    txn_id = str(len(list(filing_type_dir.iterdir())))
                filing_dir = filing_type_dir / str(txn_id)
                filing_dir.mkdir(parents=True, exist_ok=True)

                dest_ext = "html" if "html" in resource_key or resource_key == "text/html" else ("xml" if "xml" in resource_key else "xbrl")
                dest_path = filing_dir / f"primary-document.{dest_ext}"

                # Download the document
                with requests.get(doc_url, auth=(api_key, ""), headers=headers, timeout=60, stream=True) as r:
                    if r.status_code != 200:
                        # Some resources use a 'location' indirection; follow if provided
                        if r.status_code in (302, 303) and r.headers.get("Location"):
                            loc = r.headers["Location"]
                            r2 = requests.get(loc, auth=(api_key, ""), headers=headers, timeout=60, stream=True)
                            if r2.status_code != 200:
                                continue
                            with open(dest_path, "wb") as f:
                                for chunk in r2.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                        else:
                            continue
                    else:
                        with open(dest_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)

            except Exception as e:
                # Log and continue with other items
                frappe.log_error(title="Companies House Filing Download Error", message=str(e))
                continue

        return base_dir


def fetch_companies_house_financials(security_name: str) -> Dict:
    """Public function to fetch UK accounts for a security"""
    fetcher = UKCompaniesHouseFetcher(security_name, quality_score=95)
    return fetcher.fetch_financials()
