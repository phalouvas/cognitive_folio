"""
XBRL Taxonomy Mapping Layer

Maps financial concepts from different regional XBRL taxonomies to our unified
CF Financial Period field structure. Supports multiple accounting standards:
- US-GAAP (United States)
- IFRS (International/EU)
- ESEF (European Single Electronic Format)
- UK-GAAP (United Kingdom)
- HKFRS (Hong Kong)
- CA-GAAP (Canada)
- JGAAP (Japan)
- AIFRS (Australia)
"""

from typing import Dict, List, Optional
import re


class TaxonomyMapper:
	"""Maps XBRL concepts from various taxonomies to CF Financial Period fields"""
	
	def __init__(self, taxonomy: str = "US-GAAP"):
		"""
		Initialize mapper for a specific taxonomy.
		
		Args:
			taxonomy: One of US-GAAP, IFRS, ESEF, UK-GAAP, HKFRS, CA-GAAP, JGAAP, AIFRS
		"""
		self.taxonomy = taxonomy.upper()
		self.concept_map = self._build_concept_map()
	
	def _build_concept_map(self) -> Dict[str, str]:
		"""
		Build mapping dictionary for the selected taxonomy.
		
		Returns:
			Dict mapping taxonomy concepts to CF field names
		"""
		# Base mappings that work across most taxonomies
		base_income_statement = {
			# Income Statement - most common mappings
			"total_revenue": ["Revenues", "Revenue", "TurnoverRevenue", "SalesRevenueNet"],
			"cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfSales"],
			"gross_profit": ["GrossProfit"],
			"operating_expenses": ["OperatingExpenses", "OperatingCostsAndExpenses"],
			"operating_income": ["OperatingIncomeLoss", "OperatingProfit", "ProfitLossFromOperatingActivities"],
			"ebit": ["EarningsBeforeInterestAndTax", "EBIT"],
			"interest_expense": ["InterestExpense", "InterestPaid"],
			"pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxes", "ProfitLossBeforeTax"],
			"tax_provision": ["IncomeTaxExpenseBenefit", "TaxExpense", "IncomeTaxExpense"],
			"net_income": ["NetIncomeLoss", "ProfitLoss", "ProfitLossForPeriod", "NetProfit"],
			"diluted_eps": ["EarningsPerShareDiluted", "DilutedEarningsPerShare"],
			"basic_eps": ["EarningsPerShareBasic", "BasicEarningsPerShare"],
		}
		
		base_balance_sheet = {
			# Balance Sheet
			"total_assets": ["Assets"],
			"current_assets": ["AssetsCurrent", "CurrentAssets"],
			"cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue", "Cash", "CashAndCashEquivalents"],
			"accounts_receivable": ["AccountsReceivableNetCurrent", "TradeAndOtherReceivables", "TradeReceivables"],
			"inventory": ["InventoryNet", "Inventories"],
			"total_liabilities": ["Liabilities"],
			"current_liabilities": ["LiabilitiesCurrent", "CurrentLiabilities"],
			"long_term_debt": ["LongTermDebt", "NoncurrentBorrowings"],
			"total_debt": ["DebtCurrent", "TotalBorrowings"],
			"shareholders_equity": ["StockholdersEquity", "Equity", "TotalEquity"],
			"retained_earnings": ["RetainedEarningsAccumulatedDeficit", "RetainedEarnings"],
		}
		
		base_cash_flow = {
			# Cash Flow
			"operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities", "CashFlowFromOperatingActivities"],
			"capital_expenditures": ["PaymentsToAcquirePropertyPlantAndEquipment", "PurchaseOfPropertyPlantAndEquipment"],
			"investing_cash_flow": ["NetCashProvidedByUsedInInvestingActivities", "CashFlowFromInvestingActivities"],
			"financing_cash_flow": ["NetCashProvidedByUsedInFinancingActivities", "CashFlowFromFinancingActivities"],
			"dividends_paid": ["PaymentsOfDividends", "DividendsPaid"],
		}
		
		# Taxonomy-specific prefixes and variations
		if self.taxonomy == "US-GAAP":
			return self._build_us_gaap_map(base_income_statement, base_balance_sheet, base_cash_flow)
		elif self.taxonomy in ["IFRS", "ESEF"]:
			return self._build_ifrs_map(base_income_statement, base_balance_sheet, base_cash_flow)
		elif self.taxonomy == "UK-GAAP":
			return self._build_uk_gaap_map(base_income_statement, base_balance_sheet, base_cash_flow)
		elif self.taxonomy == "HKFRS":
			return self._build_hkfrs_map(base_income_statement, base_balance_sheet, base_cash_flow)
		elif self.taxonomy == "CA-GAAP":
			# Canada uses mostly IFRS now
			return self._build_ifrs_map(base_income_statement, base_balance_sheet, base_cash_flow)
		elif self.taxonomy == "JGAAP":
			return self._build_jgaap_map(base_income_statement, base_balance_sheet, base_cash_flow)
		elif self.taxonomy == "AIFRS":
			# Australia uses IFRS-based standards
			return self._build_ifrs_map(base_income_statement, base_balance_sheet, base_cash_flow)
		else:
			# Default to base mappings
			return self._flatten_concept_dict({**base_income_statement, **base_balance_sheet, **base_cash_flow})
	
	def _build_us_gaap_map(self, income: Dict, balance: Dict, cashflow: Dict) -> Dict[str, str]:
		"""Build US-GAAP specific mappings"""
		concept_map = {}
		prefix = "us-gaap:"
		
		# Add prefixed versions
		for our_field, concepts in {**income, **balance, **cashflow}.items():
			for concept in concepts:
				concept_map[f"{prefix}{concept}"] = our_field
				# Also support without prefix for flexibility
				concept_map[concept] = our_field
		
		# US-GAAP specific additions
		concept_map[f"{prefix}RevenueFromContractWithCustomerExcludingAssessedTax"] = "total_revenue"
		concept_map[f"{prefix}CostOfGoodsAndServicesSold"] = "cost_of_revenue"
		
		return concept_map
	
	def _build_ifrs_map(self, income: Dict, balance: Dict, cashflow: Dict) -> Dict[str, str]:
		"""Build IFRS/ESEF specific mappings"""
		concept_map = {}
		prefix = "ifrs-full:"
		
		for our_field, concepts in {**income, **balance, **cashflow}.items():
			for concept in concepts:
				concept_map[f"{prefix}{concept}"] = our_field
				concept_map[concept] = our_field
		
		# IFRS-specific terms
		concept_map[f"{prefix}Revenue"] = "total_revenue"
		concept_map[f"{prefix}ProfitLoss"] = "net_income"
		concept_map[f"{prefix}ProfitLossBeforeTax"] = "pretax_income"
		concept_map[f"{prefix}IncomeTaxExpenseContinuingOperations"] = "tax_provision"
		
		return concept_map
	
	def _build_uk_gaap_map(self, income: Dict, balance: Dict, cashflow: Dict) -> Dict[str, str]:
		"""Build UK-GAAP specific mappings"""
		concept_map = {}
		prefix = "uk-gaap:"
		
		for our_field, concepts in {**income, **balance, **cashflow}.items():
			for concept in concepts:
				concept_map[f"{prefix}{concept}"] = our_field
				concept_map[concept] = our_field
		
		# UK-GAAP specific terms
		concept_map[f"{prefix}TurnoverRevenue"] = "total_revenue"
		concept_map[f"{prefix}ProfitLossForPeriod"] = "net_income"
		concept_map[f"{prefix}ProfitLossBeforeTaxation"] = "pretax_income"
		
		return concept_map
	
	def _build_hkfrs_map(self, income: Dict, balance: Dict, cashflow: Dict) -> Dict[str, str]:
		"""Build HKFRS (Hong Kong) specific mappings"""
		concept_map = {}
		# HKFRS is based on IFRS with local variations
		prefix = "hkfrs:"
		
		for our_field, concepts in {**income, **balance, **cashflow}.items():
			for concept in concepts:
				concept_map[f"{prefix}{concept}"] = our_field
				concept_map[concept] = our_field
				# Also try ifrs-full prefix for compatibility
				concept_map[f"ifrs-full:{concept}"] = our_field
		
		return concept_map
	
	def _build_jgaap_map(self, income: Dict, balance: Dict, cashflow: Dict) -> Dict[str, str]:
		"""Build JGAAP (Japan) specific mappings"""
		concept_map = {}
		prefix = "jpcrp:"  # Japan Corporate Reporting
		
		for our_field, concepts in {**income, **balance, **cashflow}.items():
			for concept in concepts:
				concept_map[f"{prefix}{concept}"] = our_field
				concept_map[concept] = our_field
		
		# JGAAP specific additions (often use English terms in XBRL)
		concept_map[f"{prefix}NetSales"] = "total_revenue"
		concept_map[f"{prefix}OrdinaryIncome"] = "operating_income"
		
		return concept_map
	
	def _flatten_concept_dict(self, concept_dict: Dict[str, List[str]]) -> Dict[str, str]:
		"""Flatten a dict of field: [concepts] to concept: field"""
		result = {}
		for our_field, concepts in concept_dict.items():
			for concept in concepts:
				result[concept] = our_field
		return result
	
	def map_concept(self, xbrl_concept: str) -> Optional[str]:
		"""
		Map an XBRL concept name to a CF Financial Period field.
		
		Args:
			xbrl_concept: Full XBRL concept name (e.g., 'us-gaap:Revenues')
			
		Returns:
			CF field name or None if no mapping found
		"""
		# Try exact match first
		if xbrl_concept in self.concept_map:
			return self.concept_map[xbrl_concept]
		
		# Try case-insensitive match
		lower_concept = xbrl_concept.lower()
		for key, value in self.concept_map.items():
			if key.lower() == lower_concept:
				return value
		
		# Try without prefix
		if ':' in xbrl_concept:
			concept_no_prefix = xbrl_concept.split(':', 1)[1]
			if concept_no_prefix in self.concept_map:
				return self.concept_map[concept_no_prefix]
		
		return None
	
	def get_all_concepts_for_field(self, cf_field: str) -> List[str]:
		"""
		Get all XBRL concepts that map to a specific CF field.
		
		Args:
			cf_field: CF Financial Period field name
			
		Returns:
			List of XBRL concept names
		"""
		return [concept for concept, field in self.concept_map.items() if field == cf_field]
	
	@staticmethod
	def detect_taxonomy_from_namespace(namespaces: Dict[str, str]) -> str:
		"""
		Detect taxonomy from XBRL document namespaces.
		
		Args:
			namespaces: Dict of namespace prefixes to URIs
			
		Returns:
			Detected taxonomy name (US-GAAP, IFRS, etc.)
		"""
		for prefix, uri in namespaces.items():
			uri_lower = uri.lower()
			if 'us-gaap' in uri_lower or 'fasb.org' in uri_lower:
				return "US-GAAP"
			elif 'ifrs-full' in uri_lower or 'ifrs.org' in uri_lower:
				return "IFRS"
			elif 'esef' in uri_lower or 'esma.europa.eu' in uri_lower:
				return "ESEF"
			elif 'uk-gaap' in uri_lower or 'frc.org.uk' in uri_lower:
				return "UK-GAAP"
			elif 'hkfrs' in uri_lower or 'hkicpa.org.hk' in uri_lower:
				return "HKFRS"
			elif 'jpcrp' in uri_lower or 'xbrl.tdnet.info' in uri_lower:
				return "JGAAP"
		
		# Default to IFRS if unclear (most common international standard)
		return "IFRS"


# Convenience functions for common use cases
def map_us_gaap_concept(concept: str) -> Optional[str]:
	"""Quick mapping for US-GAAP concepts"""
	mapper = TaxonomyMapper("US-GAAP")
	return mapper.map_concept(concept)


def map_ifrs_concept(concept: str) -> Optional[str]:
	"""Quick mapping for IFRS concepts"""
	mapper = TaxonomyMapper("IFRS")
	return mapper.map_concept(concept)


def auto_map_concept(concept: str, namespaces: Dict[str, str]) -> Optional[str]:
	"""
	Automatically detect taxonomy and map concept.
	
	Args:
		concept: XBRL concept name
		namespaces: Document namespaces for taxonomy detection
		
	Returns:
		CF field name or None
	"""
	taxonomy = TaxonomyMapper.detect_taxonomy_from_namespace(namespaces)
	mapper = TaxonomyMapper(taxonomy)
	return mapper.map_concept(concept)
