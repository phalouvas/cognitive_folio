from datetime import date, datetime
from typing import Dict, Optional, Tuple
from lxml import etree


NS = {
    "ix": "http://www.xbrl.org/2013/inlineXBRL",
    "xbrli": "http://www.xbrl.org/2003/instance",
}


def _parse_end_date(ctx_el) -> Optional[date]:
    period = ctx_el.find("xbrli:period", namespaces=NS)
    if period is None:
        return None
    end = period.findtext("xbrli:endDate", namespaces=NS)
    if not end:
        instant = period.findtext("xbrli:instant", namespaces=NS)
        end = instant
    if not end:
        return None
    try:
        return datetime.fromisoformat(end).date()
    except Exception:
        try:
            return datetime.strptime(end, "%Y-%m-%d").date()
        except Exception:
            return None


def extract_financial_data_ixbrl(file_path: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Minimal, robust iXBRL extractor for US-GAAP facts using lxml.
    Returns (financial_data, error).
    """
    try:
        parser = etree.HTMLParser(recover=True)
        tree = etree.parse(file_path, parser)

        # Build context end-date map
        contexts: Dict[str, date] = {}
        for ctx in tree.findall('.//xbrli:context', namespaces=NS):
            ctx_id = ctx.get('id')
            if not ctx_id:
                continue
            end = _parse_end_date(ctx)
            if end:
                contexts[ctx_id] = end

        if not contexts:
            return None, "No contexts found in iXBRL"

        # Target mapping
        map_local = {
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
            # Balance sheet
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
            # Cash flow
            "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
            "PaymentsToAcquirePropertyPlantAndEquipment": "capital_expenditures",
            "NetCashProvidedByUsedInInvestingActivities": "investing_cash_flow",
            "NetCashProvidedByUsedInFinancingActivities": "financing_cash_flow",
            "PaymentsOfDividends": "dividends_paid",
        }

        # Collect facts bucketed by end-date
        by_end: Dict[date, Dict[str, float]] = {}
        for nf in tree.findall('.//ix:nonFraction', namespaces=NS):
            name = nf.get('name')
            if not name or not name.startswith('us-gaap:'):
                continue
            local = name.split(':', 1)[1]
            target = map_local.get(local)
            if not target:
                continue
            ctx_id = nf.get('contextRef')
            if not ctx_id or ctx_id not in contexts:
                continue
            txt = (nf.text or '').strip().replace(',', '')
            if not txt:
                continue
            try:
                val = float(txt)
            except Exception:
                continue
            # Apply scale if present
            scale = nf.get('scale')
            if scale:
                try:
                    val *= pow(10, int(scale))
                except Exception:
                    pass
            end = contexts[ctx_id]
            by_end.setdefault(end, {})[target] = val

        if not by_end:
            return None, "No US-GAAP ix:nonFraction facts found"

        end_date = sorted(by_end.keys())[-1]
        data = by_end[end_date]

        # Derived
        if 'gross_profit' not in data and 'total_revenue' in data and 'cost_of_revenue' in data:
            data['gross_profit'] = data['total_revenue'] - data['cost_of_revenue']

        if 'capital_expenditures' in data:
            data['capital_expenditures'] = abs(data['capital_expenditures'])

        if 'operating_cash_flow' in data and 'capital_expenditures' in data:
            data['free_cash_flow'] = data['operating_cash_flow'] - data['capital_expenditures']

        # Period metadata
        m = end_date.month
        if m in (1, 2, 3):
            fq = 'Q1'
        elif m in (4, 5, 6):
            fq = 'Q2'
        elif m in (7, 8, 9):
            fq = 'Q3'
        else:
            fq = 'Q4'

        data.update({
            'fiscal_year': end_date.year,
            'fiscal_quarter': fq,
            'period_end_date': end_date,
        })

        return data, None

    except Exception as e:
        return None, str(e)
