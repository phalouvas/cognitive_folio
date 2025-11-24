import json
from datetime import datetime, date
from typing import Dict, Optional, Tuple

# Compatibility shim for libraries expecting collections.Mutable* on Python >= 3.10
try:
    import collections
    import collections.abc as cabc
    if not hasattr(collections, "MutableSet"):
        collections.MutableSet = cabc.MutableSet  # type: ignore[attr-defined]
    if not hasattr(collections, "MutableMapping"):
        collections.MutableMapping = cabc.MutableMapping  # type: ignore[attr-defined]
    if not hasattr(collections, "Mapping"):
        collections.Mapping = cabc.Mapping  # type: ignore[attr-defined]
    if not hasattr(collections, "Sequence"):
        collections.Sequence = cabc.Sequence  # type: ignore[attr-defined]
except Exception:
    pass


def _get_end_date_from_context(ctx) -> Optional[date]:
    try:
        # duration contexts have endDatetime; instants have instantDatetime
        if getattr(ctx, "isPeriodDuration", False):
            dt = getattr(ctx, "endDatetime", None)
        else:
            dt = getattr(ctx, "instantDatetime", None)
        if dt is None:
            return None
        # Arelle returns Python datetime
        return dt.date() if hasattr(dt, "date") else None
    except Exception:
        return None


def extract_financial_data_arelle(file_path: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Load an iXBRL/XBRL file with Arelle and extract US-GAAP facts needed
    to populate a CF Financial Period. Returns (financial_data, error).
    """
    try:
        # Ensure Arelle works within a writable directory (avoid system HOME)
        import os
        import frappe  # type: ignore
        arelle_home = frappe.get_site_path("private", "files", "arelle_home")
        os.makedirs(arelle_home, exist_ok=True)
        os.environ.setdefault("HOME", arelle_home)
        os.environ.setdefault("ARELLE_USER_APP_DIR", arelle_home)
        os.environ.setdefault("XDG_CONFIG_HOME", arelle_home)
        os.environ.setdefault("XDG_CACHE_HOME", arelle_home)
        os.environ.setdefault("ARELLE_HOME", arelle_home)

        from arelle import Cntlr

        cntlr = Cntlr.Cntlr(logFileName=None)
        model_xbrl = cntlr.modelManager.load(files=[file_path])

        # Map of (namespace contains 'us-gaap', localname) -> our field
        taxonomy_map = {
            "Revenues": "total_revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax": "total_revenue",
            "CostOfRevenue": "cost_of_revenue",
            "CostOfGoodsAndServicesSold": "cost_of_revenue",
            "GrossProfit": "gross_profit",
            "OperatingExpenses": "operating_expenses",
            "OperatingIncomeLoss": "operating_income",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "pretax_income",
            "IncomeTaxExpenseBenefit": "tax_provision",
            "NetIncomeLoss": "net_income",
            "EarningsPerShareBasic": "basic_eps",
            "EarningsPerShareDiluted": "diluted_eps",
            # Balance Sheet
            "Assets": "total_assets",
            "AssetsCurrent": "current_assets",
            "CashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",
            "AccountsReceivableNetCurrent": "accounts_receivable",
            "InventoryNet": "inventory",
            "Liabilities": "total_liabilities",
            "LiabilitiesCurrent": "current_liabilities",
            "DebtLongTerm": "long_term_debt",
            "LongTermDebt": "long_term_debt",
            "StockholdersEquity": "shareholders_equity",
            "RetainedEarningsAccumulatedDeficit": "retained_earnings",
            # Cash Flow
            "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
            "PaymentsToAcquirePropertyPlantAndEquipment": "capital_expenditures",
            "NetCashProvidedByUsedInInvestingActivities": "investing_cash_flow",
            "NetCashProvidedByUsedInFinancingActivities": "financing_cash_flow",
            "PaymentsOfDividends": "dividends_paid",
        }

        # Collect candidate facts grouped by context end date
        facts_by_enddate: Dict[date, Dict[str, float]] = {}

        for f in getattr(model_xbrl, "facts", []) or []:
            try:
                concept = getattr(f, "concept", None)
                if concept is None:
                    continue
                qn = getattr(concept, "qname", None)
                if qn is None:
                    continue
                ns = getattr(qn, "namespaceURI", "") or ""
                if "us-gaap" not in ns:
                    continue
                local = getattr(qn, "localName", None)
                if local not in taxonomy_map:
                    continue
                ctx = getattr(f, "context", None)
                if ctx is None:
                    continue
                end_date = _get_end_date_from_context(ctx)
                if end_date is None:
                    continue
                # Prefer numeric xValue; fallback to string value
                xval = getattr(f, "xValue", None)
                try:
                    val = float(xval)
                except Exception:
                    try:
                        val = float(getattr(f, "value", None))
                    except Exception:
                        continue

                mapped = taxonomy_map[local]
                bucket = facts_by_enddate.setdefault(end_date, {})
                # Keep last value if duplicates; SEC often has multiple contexts
                bucket[mapped] = val
            except Exception:
                continue

        if not facts_by_enddate:
            return None, "No US-GAAP facts found in iXBRL"

        # Choose the most recent period end date available
        end_date = sorted(facts_by_enddate.keys())[-1]
        data = facts_by_enddate[end_date]

        # Derive additional fields
        if "gross_profit" not in data and "total_revenue" in data and "cost_of_revenue" in data:
            data["gross_profit"] = data["total_revenue"] - data["cost_of_revenue"]

        if "capital_expenditures" in data:
            data["capital_expenditures"] = abs(data["capital_expenditures"])  # normalize sign

        if "operating_cash_flow" in data and "capital_expenditures" in data:
            data["free_cash_flow"] = data["operating_cash_flow"] - data["capital_expenditures"]

        # Period metadata
        fiscal_year = end_date.year
        m = end_date.month
        if m in (1, 2, 3):
            fq = "Q1"
        elif m in (4, 5, 6):
            fq = "Q2"
        elif m in (7, 8, 9):
            fq = "Q3"
        else:
            fq = "Q4"

        data.update({
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fq,
            "period_end_date": end_date,
        })

        return data, None

    except Exception as e:
        return None, str(e)
