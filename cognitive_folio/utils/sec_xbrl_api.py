import frappe
import requests
from datetime import datetime, date
from typing import Dict, Optional, Tuple

USER_AGENT = "Cognitive Folio App (contact@example.com)"

TAXONOMY_MAP = {
    # Income Statement
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


def _parse_date(s: str) -> Optional[date]:
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None


def fetch_company_facts(cik: str) -> Optional[Dict]:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def import_from_sec_company_facts(security_name: str, cik: str) -> Dict:
    security = frappe.get_doc("CF Security", security_name)

    facts = fetch_company_facts(cik)
    if not facts or "facts" not in facts:
        return {
            "success": False,
            "error": "SEC CompanyFacts not available",
            "imported_count": 0,
            "updated_count": 0,
            "upgraded_count": 0,
            "skipped_count": 0,
        }

    usgaap = facts.get("facts", {}).get("us-gaap", {})

    # Aggregate by period end date
    by_period: Dict[date, Dict[str, float]] = {}
    meta: Dict[date, Dict[str, str]] = {}

    for concept, mapping in TAXONOMY_MAP.items():
        node = usgaap.get(concept)
        if not node:
            continue
        units = node.get("units", {})
        # Prefer USD
        series = None
        for pref in ("USD", "usd", "USD/shares", "pure"):
            if pref in units:
                series = units[pref]
                break
        if not series:
            # take any unit
            if units:
                series = next(iter(units.values()))
        if not series:
            continue
        for item in series:
            try:
                end = _parse_date(item.get("end"))
                if not end:
                    continue
                val = item.get("val")
                if val is None:
                    continue
                try:
                    fval = float(val)
                except Exception:
                    continue
                bucket = by_period.setdefault(end, {})
                bucket[mapping] = fval
                # Meta for period type
                fy = item.get("fy")
                fp = item.get("fp")  # e.g., Q1..Q4 or FY
                meta.setdefault(end, {})
                if fy:
                    meta[end]["fy"] = str(fy)
                if fp:
                    meta[end]["fp"] = str(fp)
            except Exception:
                continue

    if not by_period:
        return {
            "success": False,
            "error": "No mappable us-gaap facts",
            "imported_count": 0,
            "updated_count": 0,
            "upgraded_count": 0,
            "skipped_count": 0,
        }

    imported = updated = upgraded = skipped = 0
    quality = 95

    # Save most recent ~20 periods
    for end in sorted(by_period.keys(), reverse=True)[:20]:
        data = by_period[end]
        m = meta.get(end, {})
        fy = int(m.get("fy")) if m.get("fy") and str(m.get("fy")).isdigit() else end.year
        fp = m.get("fp")
        period_type = "Annual" if (fp == "FY" or (fp is None and end.month in (9, 12))) else "Quarterly"
        fiscal_quarter = None
        if period_type == "Quarterly":
            month = end.month
            if month in (1, 2, 3):
                fiscal_quarter = "Q1"
            elif month in (4, 5, 6):
                fiscal_quarter = "Q2"
            elif month in (7, 8, 9):
                fiscal_quarter = "Q3"
            else:
                fiscal_quarter = "Q4"

        filters = {"security": security.name, "period_type": period_type, "fiscal_year": fy}
        if fiscal_quarter:
            filters["fiscal_quarter"] = fiscal_quarter

        existing = frappe.db.get_value(
            "CF Financial Period",
            filters,
            ["name", "data_quality_score", "override_yahoo"],
            as_dict=True,
        )

        if existing and existing.override_yahoo:
            skipped += 1
            continue

        is_upgrade = False
        if existing:
            if existing.data_quality_score < quality:
                is_upgrade = True
                period = frappe.get_doc("CF Financial Period", existing.name)
            elif existing.data_quality_score >= quality:
                skipped += 1
                continue
            else:
                period = frappe.get_doc("CF Financial Period", existing.name)
        else:
            period = frappe.new_doc("CF Financial Period")
            period.security = security.name
            period.period_type = period_type
            period.fiscal_year = fy
            if fiscal_quarter:
                period.fiscal_quarter = fiscal_quarter
            period.period_end_date = end

        period.data_source = "SEC Edgar"
        period.data_quality_score = quality
        period.currency = security.currency or "USD"

        # Map values
        for k, v in data.items():
            setattr(period, k, v)

        # Derived
        if getattr(period, "gross_profit", None) is None and getattr(period, "total_revenue", None) is not None and getattr(period, "cost_of_revenue", None) is not None:
            period.gross_profit = period.total_revenue - period.cost_of_revenue
        if getattr(period, "capital_expenditures", None) is not None and period.capital_expenditures < 0:
            period.capital_expenditures = abs(period.capital_expenditures)
        if getattr(period, "operating_cash_flow", None) is not None and getattr(period, "capital_expenditures", None) is not None:
            period.free_cash_flow = period.operating_cash_flow - period.capital_expenditures

        period.save()

        if is_upgrade:
            upgraded += 1
        elif existing:
            updated += 1
        else:
            imported += 1

    frappe.db.commit()

    return {
        "success": True,
        "imported_count": imported,
        "updated_count": updated,
        "upgraded_count": upgraded,
        "skipped_count": skipped,
        "total_periods": imported + updated + upgraded,
        "errors": None,
        "data_source_used": "SEC Edgar",
    }
