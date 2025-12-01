# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

import frappe
import json
import re
from typing import Dict, List, Tuple

# Conditional import for test framework (not required for validator usage)
try:
	from frappe.tests.utils import FrappeTestCase as UnitTestCase
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase
except ImportError:
	# Fallback for older Frappe versions or when tests module not available
	try:
		from frappe.tests import UnitTestCase, IntegrationTestCase
	except ImportError:
		# Define dummy classes if test framework not available
		class UnitTestCase:
			pass
		class IntegrationTestCase:
			pass


# On IntegrationTestCase, the doctype test records and all
# link-field test record depdendencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class UnitTestCFFinancialPeriod(UnitTestCase):
	"""
	Unit tests for CFFinancialPeriod.
	Use this class for testing individual functions and methods.
	"""

	pass


class IntegrationTestCFFinancialPeriod(IntegrationTestCase):
	"""
	Integration tests for CFFinancialPeriod.
	Use this class for testing interactions between multiple components.
	"""

	pass


class FinancialPeriodDataValidator:
	"""
	Comprehensive validator for CF Financial Period data completeness and prompt variable replacement.
	
	This class provides automated testing for:
	1. Fundamental data fetching (SEC Edgar, Yahoo Finance)
	2. Financial period data completeness validation
	3. Prompt variable replacement testing
	4. Diagnostic reporting for AI agents
	
	Usage:
		validator = FinancialPeriodDataValidator("AAPL")
		result = validator.run_full_validation()
		print(validator.get_diagnostic_report(result))
	"""
	
	def __init__(self, symbol: str):
		"""
		Initialize validator for a specific security symbol.
		
		Args:
			symbol: Stock ticker symbol (e.g., "AAPL", "MSFT", "BRK.B")
		"""
		self.symbol = symbol
		self.security_name = None
		self.security_doc = None
		
	def run_full_validation(self) -> Dict:
		"""
		Execute complete validation suite.
		
		Returns:
			Dict with structure:
			{
				'success': bool,
				'security': {...},
				'fetch_result': {...},
				'data_validation': {...},
				'variable_tests': {...},
				'summary': {...}
			}
		"""
		result = {
			'success': True,
			'security': None,
			'fetch_result': None,
			'data_validation': None,
			'variable_tests': None,
			'summary': {},
			'errors': []
		}
		
		try:
			# Step 1: Get or create security
			result['security'] = self._get_or_create_security()
			if not result['security']['success']:
				result['success'] = False
				return result
			
			# Step 2: Fetch fundamentals
			result['fetch_result'] = self._fetch_fundamentals()
			if not result['fetch_result']['success']:
				result['success'] = False
				result['errors'].append("Fundamental fetch failed")
			
			# Step 3: Validate data completeness
			result['data_validation'] = self._validate_data_completeness()
			
			# Step 4: Test prompt variable replacement
			result['variable_tests'] = self._test_variable_replacement()
			
			# Step 5: Generate summary
			result['summary'] = self._generate_summary(result)
			
			# Determine overall success
			result['success'] = (
				result['security']['success'] and
				result['fetch_result']['success'] and
				result['data_validation']['critical_fields_ok'] and
				result['variable_tests']['all_passed']
			)
			
		except Exception as e:
			result['success'] = False
			result['errors'].append(f"Validation error: {str(e)}")
			frappe.log_error(
				title=f"Validation Error: {self.symbol}",
				message=f"{str(e)}\n{frappe.get_traceback()}"
			)
		
		return result
	
	def _get_or_create_security(self) -> Dict:
		"""Get existing or create new CF Security for testing."""
		try:
			# Check if security exists
			existing = frappe.db.get_value("CF Security", {"symbol": self.symbol}, "name")
			
			if existing:
				self.security_name = existing
				self.security_doc = frappe.get_doc("CF Security", existing)
				return {
					'success': True,
					'name': self.security_name,
					'action': 'found_existing',
					'country': self.security_doc.country,
					'sec_cik': self.security_doc.sec_cik
				}
			else:
				# Create new security
				security = frappe.new_doc("CF Security")
				security.symbol = self.symbol
				security.security_name = f"Test Security {self.symbol}"
				security.security_type = "Stock"
				security.insert(ignore_permissions=True)
				frappe.db.commit()
				
				self.security_name = security.name
				self.security_doc = security
				
				return {
					'success': True,
					'name': self.security_name,
					'action': 'created_new',
					'country': security.country,
					'sec_cik': security.sec_cik
				}
				
		except Exception as e:
			return {
				'success': False,
				'error': str(e)
			}
	
	def _fetch_fundamentals(self) -> Dict:
		"""Trigger fundamental data fetch and capture results."""
		try:
			# Trigger fetch with fundamentals
			self.security_doc.fetch_data(with_fundamentals=True)
			
			# Reload to get updated data
			self.security_doc.reload()
			
			# Parse import result if available
			import_result = {}
			if self.security_doc.last_period_import_result:
				try:
					import_result = json.loads(self.security_doc.last_period_import_result)
				except:
					pass
			
			# Count created periods
			period_counts = self._count_periods()
			
			return {
				'success': True,
				'data_source': import_result.get('data_source_used', 'Unknown'),
				'import_result': import_result,
				'period_counts': period_counts,
				'has_ticker_info': bool(self.security_doc.ticker_info),
				'has_fundamentals': bool(self.security_doc.profit_loss)
			}
			
		except Exception as e:
			return {
				'success': False,
				'error': str(e)
			}
	
	def _count_periods(self) -> Dict:
		"""Count financial periods by type."""
		annual_count = frappe.db.count(
			"CF Financial Period",
			{"security": self.security_name, "period_type": "Annual"}
		)
		quarterly_count = frappe.db.count(
			"CF Financial Period",
			{"security": self.security_name, "period_type": "Quarterly"}
		)
		
		return {
			'annual': annual_count,
			'quarterly': quarterly_count,
			'total': annual_count + quarterly_count
		}
	
	def _validate_data_completeness(self) -> Dict:
		"""Validate completeness of financial period data."""
		validation = {
			'critical_fields_ok': True,
			'annual_periods': [],
			'quarterly_periods': [],
			'field_coverage': {},
			'issues': [],
			'zero_value_issues': []
		}
		
		# Define critical fields that should be populated AND non-zero
		# These align with fields required by AI prompt template for quantitative anchoring
		critical_fields = {
			'income_statement': ['total_revenue', 'net_income', 'operating_income'],
			'balance_sheet': ['total_assets', 'total_liabilities', 'shareholders_equity'],
			'cash_flow': ['operating_cash_flow', 'free_cash_flow'],
			'calculated_metrics': ['gross_margin', 'operating_margin', 'net_margin', 'roe'],
			'financial_ratios': ['current_ratio', 'debt_to_equity']
		}
		
		# Additional fields to check for suspicious zeros (should not be zero if related fields exist)
		# Derived fields: flag suspicious zeros when dependencies exist but derived field is zero
		# These checks ensure auto-calculations are working correctly
		derived_fields = {
			'total_revenue': ['gross_profit', 'cost_of_revenue'],  # If these exist, revenue should too
			'operating_income': ['gross_profit', 'operating_expenses'],  # If these exist, op income should too
			'operating_cash_flow': ['net_income'],  # If net income exists, OCF should exist
			'free_cash_flow': ['operating_cash_flow', 'capital_expenditures'],  # If these exist, FCF should too (critical for Management rating)
			'gross_margin': ['total_revenue', 'gross_profit'],  # Should calculate from these (critical for Moat rating)
			'operating_margin': ['total_revenue', 'operating_income'],  # Critical for margin analysis
			'net_margin': ['total_revenue', 'net_income'],  # Critical for Financials rating
			'current_ratio': ['current_assets', 'current_liabilities'],  # Critical for liquidity assessment
			'debt_to_equity': ['total_liabilities', 'shareholders_equity'],  # Critical for Management rating
			'roe': ['net_income', 'shareholders_equity'],  # Critical for Moat rating
			'roa': ['net_income', 'total_assets']  # Secondary metric
		}
		
		# Validate annual periods (get all fields for comprehensive check)
		all_field_names = [
			"name", "fiscal_year", "period_end_date", "data_source", "data_quality_score",
			"total_revenue", "cost_of_revenue", "gross_profit", "operating_expenses", 
			"operating_income", "ebit", "ebitda", "interest_expense", "pretax_income",
			"tax_provision", "net_income", "diluted_eps", "basic_eps",
			"total_assets", "current_assets", "cash_and_equivalents", "accounts_receivable",
			"inventory", "total_liabilities", "current_liabilities", "total_debt",
			"long_term_debt", "shareholders_equity", "retained_earnings",
			"operating_cash_flow", "capital_expenditures", "free_cash_flow",
			"investing_cash_flow", "financing_cash_flow",
			"gross_margin", "operating_margin", "net_margin", "roe", "roa",
			"current_ratio", "debt_to_equity"
		]
		
		annual_periods = frappe.get_all(
			"CF Financial Period",
			filters={"security": self.security_name, "period_type": "Annual"},
			fields=all_field_names,
			order_by="fiscal_year DESC",
			limit=10
		)
		
		validation['annual_periods'] = self._analyze_periods(annual_periods, critical_fields, derived_fields)
		
		# Validate quarterly periods
		quarterly_periods = frappe.get_all(
			"CF Financial Period",
			filters={"security": self.security_name, "period_type": "Quarterly"},
			fields=all_field_names + ["fiscal_quarter"],
			order_by="fiscal_year DESC, fiscal_quarter DESC",
			limit=16
		)
		
		validation['quarterly_periods'] = self._analyze_periods(quarterly_periods, critical_fields, derived_fields)
		
		# Calculate field coverage across all periods (checking both None and Zero)
		all_periods = annual_periods + quarterly_periods
		if all_periods:
			for category, fields in critical_fields.items():
				validation['field_coverage'][category] = {}
				for field in fields:
					populated = sum(1 for p in all_periods if p.get(field) is not None and p.get(field) != 0)
					total = len(all_periods)
					validation['field_coverage'][category][field] = {
						'populated': populated,
						'total': total,
						'percentage': round((populated / total * 100), 2) if total > 0 else 0
					}
		
		# Collect zero-value issues from period analysis
		for period_analysis in validation['annual_periods'] + validation['quarterly_periods']:
			if period_analysis.get('suspicious_zeros'):
				for zero_issue in period_analysis['suspicious_zeros']:
					validation['zero_value_issues'].append(
						f"{period_analysis['name']}: {zero_issue}"
					)
		
		# Check for critical issues
		if len(annual_periods) < 3:
			validation['issues'].append(f"Only {len(annual_periods)} annual periods (target: 10+)")
			validation['critical_fields_ok'] = False
		
		if len(quarterly_periods) < 8:
			validation['issues'].append(f"Only {len(quarterly_periods)} quarterly periods (target: 16)")
			validation['critical_fields_ok'] = False
		
		# Check field coverage (now detecting zeros as missing)
		for category, fields_coverage in validation['field_coverage'].items():
			for field, coverage in fields_coverage.items():
				if coverage['percentage'] < 70:
					validation['issues'].append(
						f"{field} only {coverage['percentage']}% populated (non-zero) in {category}"
					)
					if coverage['percentage'] < 50:
						validation['critical_fields_ok'] = False
		
		# Add zero-value issues to main issues list
		if validation['zero_value_issues']:
			validation['issues'].extend(validation['zero_value_issues'][:5])  # Add top 5
			validation['critical_fields_ok'] = False
		
		return validation
	
	def _analyze_periods(self, periods: List[Dict], critical_fields: Dict, derived_fields: Dict = None) -> List[Dict]:
		"""Analyze individual periods for data completeness and suspicious zeros."""
		analyzed = []
		
		for period in periods:
			analysis = {
				'name': period.get('name'),
				'fiscal_year': period.get('fiscal_year'),
				'fiscal_quarter': period.get('fiscal_quarter'),
				'period_end_date': str(period.get('period_end_date')),
				'data_source': period.get('data_source'),
				'data_quality_score': period.get('data_quality_score'),
				'completeness': {},
				'missing_critical': [],
				'suspicious_zeros': []
			}
			
			# Check each category (now considering zeros as problematic)
			for category, fields in critical_fields.items():
				populated = sum(1 for f in fields if period.get(f) is not None and period.get(f) != 0)
				total = len(fields)
				analysis['completeness'][category] = {
					'populated': populated,
					'total': total,
					'percentage': round((populated / total * 100), 2) if total > 0 else 0
				}
				
				# Track missing or zero critical fields
				for field in fields:
					val = period.get(field)
					if val is None:
						analysis['missing_critical'].append(f"{category}.{field} (None)")
					elif val == 0:
						analysis['missing_critical'].append(f"{category}.{field} (Zero)")
			
			# Check for suspicious zeros in derived fields
			if derived_fields:
				for target_field, dependency_fields in derived_fields.items():
					target_val = period.get(target_field)
					# Check if target is zero/None but dependencies exist
					if (target_val is None or target_val == 0):
						dependencies_exist = []
						for dep_field in dependency_fields:
							dep_val = period.get(dep_field)
							if dep_val is not None and dep_val != 0:
								dependencies_exist.append(f"{dep_field}={dep_val}")
						
						if dependencies_exist:
							analysis['suspicious_zeros'].append(
								f"{target_field} is {target_val} but has data: {', '.join(dependencies_exist)}"
							)
			
			analyzed.append(analysis)
		
		return analyzed
	
	def _test_variable_replacement(self) -> Dict:
		"""Test all prompt variable patterns and check for zero values in rendered output."""
		tests = {
			'all_passed': True,
			'tests': [],
			'zero_value_warnings': []
		}
		
		# Define test cases for different variable patterns
		test_cases = [
			# Basic field variables
			{
				'name': 'security_name',
				'pattern': '{{security_name}}',
				'expected_type': str,
				'should_not_be_empty': True
			},
			{
				'name': 'symbol',
				'pattern': '{{symbol}}',
				'expected_type': str,
				'should_not_be_empty': True
			},
			{
				'name': 'current_price',
				'pattern': '{{current_price}}',
				'expected_type': (str, float),
				'should_not_be_empty': True
			},
			{
				'name': 'currency',
				'pattern': '{{currency}}',
				'expected_type': str,
				'should_not_be_empty': True
			},
			{
				'name': 'sector',
				'pattern': '{{sector}}',
				'expected_type': str,
				'should_not_be_empty': False
			},
			{
				'name': 'industry',
				'pattern': '{{industry}}',
				'expected_type': str,
				'should_not_be_empty': False
			},
			# JSON field navigation
			{
				'name': 'ticker_info.marketCap',
				'pattern': '{{ticker_info.marketCap}}',
				'expected_type': (str, int, float),
				'should_not_be_empty': False
			},
			{
				'name': 'ticker_info.trailingPE',
				'pattern': '{{ticker_info.trailingPE}}',
				'expected_type': (str, float),
				'should_not_be_empty': False
			},
			{
				'name': 'ticker_info.forwardPE',
				'pattern': '{{ticker_info.forwardPE}}',
				'expected_type': (str, float),
				'should_not_be_empty': False
			},
			{
				'name': 'ticker_info.priceToBook',
				'pattern': '{{ticker_info.priceToBook}}',
				'expected_type': (str, float),
				'should_not_be_empty': False
			},
			# Period tags - Annual (test multiple ranges)
			{
				'name': 'periods:annual:5:markdown',
				'pattern': '{{periods:annual:5:markdown}}',
				'expected_type': str,
				'should_not_be_empty': True,
				'min_length': 100,
				'check_for_zeros': True  # New flag to check rendered content for zeros
			},
			{
				'name': 'periods:annual:10:markdown',
				'pattern': '{{periods:annual:10:markdown}}',
				'expected_type': str,
				'should_not_be_empty': True,
				'min_length': 100,
				'check_for_zeros': True
			},
			# Period tags - Quarterly
			{
				'name': 'periods:quarterly:8:markdown',
				'pattern': '{{periods:quarterly:8:markdown}}',
				'expected_type': str,
				'should_not_be_empty': True,
				'min_length': 100,
				'check_for_zeros': True
			},
			{
				'name': 'periods:quarterly:16:markdown',
				'pattern': '{{periods:quarterly:16:markdown}}',
				'expected_type': str,
				'should_not_be_empty': True,
				'min_length': 100,
				'check_for_zeros': True
			},
			# Comparison tags
			{
				'name': 'periods:compare:latest_annual:previous_annual',
				'pattern': '{{periods:compare:latest_annual:previous_annual}}',
				'expected_type': str,
				'should_not_be_empty': True,
				'min_length': 50,
				'check_for_zeros': True
			},
			{
				'name': 'periods:compare:latest_annual:annual_minus_2',
				'pattern': '{{periods:compare:latest_annual:annual_minus_2}}',
				'expected_type': str,
				'should_not_be_empty': True,
				'min_length': 50,
				'check_for_zeros': True
			},
			{
				'name': 'periods:compare:latest_quarterly:previous_quarterly',
				'pattern': '{{periods:compare:latest_quarterly:previous_quarterly}}',
				'expected_type': str,
				'should_not_be_empty': True,
				'min_length': 50,
				'check_for_zeros': True
			},
			{
				'name': 'periods:compare:latest_quarterly:yoy_quarterly',
				'pattern': '{{periods:compare:latest_quarterly:yoy_quarterly}}',
				'expected_type': str,
				'should_not_be_empty': True,
				'min_length': 50,
				'check_for_zeros': True
			}
		]
		
		# Execute each test
		for test_case in test_cases:
			result = self._execute_variable_test(test_case)
			tests['tests'].append(result)
			
			if not result['passed']:
				tests['all_passed'] = False
			
			# Check for suspicious zero patterns in rendered output
			if result.get('passed') and test_case.get('check_for_zeros'):
				zero_warnings = self._check_for_zero_patterns(result['output'], test_case['name'])
				if zero_warnings:
					tests['zero_value_warnings'].extend(zero_warnings)
					# Don't fail the test, but flag as warning
		
		# If there are zero-value warnings, consider test failed
		if tests['zero_value_warnings']:
			tests['all_passed'] = False
		
		return tests
	
	def _execute_variable_test(self, test_case: Dict) -> Dict:
		"""Execute a single variable replacement test."""
		from cognitive_folio.utils.helper import replace_variables
		
		result = {
			'name': test_case['name'],
			'pattern': test_case['pattern'],
			'passed': False,
			'output': None,
			'output_length': 0,
			'error': None
		}
		
		try:
			# Create a match object for the pattern
			match = re.match(r'\{\{(.+?)\}\}', test_case['pattern'])
			if not match:
				result['error'] = "Invalid pattern format"
				return result
			
			# Execute replacement
			output = replace_variables(match, self.security_doc)
			result['output'] = output
			result['output_length'] = len(str(output))
			
			# Validate output type
			if not isinstance(output, test_case['expected_type']):
				result['error'] = f"Expected type {test_case['expected_type']}, got {type(output)}"
				return result
			
			# Validate not empty if required
			if test_case.get('should_not_be_empty') and not output:
				result['error'] = "Output is empty but should not be"
				return result
			
			# Validate minimum length if specified
			if test_case.get('min_length') and len(str(output)) < test_case['min_length']:
				result['error'] = f"Output length {len(str(output))} < minimum {test_case['min_length']}"
				return result
			
			result['passed'] = True
			
		except Exception as e:
			result['error'] = str(e)
		
		return result
	
	def _check_for_zero_patterns(self, output: str, test_name: str) -> List[str]:
		"""Check rendered period output for suspicious zero patterns."""
		warnings = []
		
		if not output or not isinstance(output, str):
			return warnings
		
		# Pattern 1: Check for fields explicitly showing 0 or 0.0
		# Look for patterns like "Revenue: 0" or "Revenue | 0.0" in tables
		zero_patterns = [
			r'Revenue[:\|]\s*[-\$€£¥]?\s*0\.?0*\b',
			r'Operating Income[:\|]\s*[-\$€£¥]?\s*0\.?0*\b',
			r'Operating Cash Flow[:\|]\s*[-\$€£¥]?\s*0\.?0*\b',
			r'Gross Margin[:\|]\s*0\.?0*%',
			r'Net Margin[:\|]\s*0\.?0*%',
			r'Operating Margin[:\|]\s*0\.?0*%',
			r'Free Cash Flow[:\|]\s*[-\$€£¥]?\s*0\.?0*\b'
		]
		
		for pattern in zero_patterns:
			matches = re.findall(pattern, output, re.IGNORECASE)
			if matches:
				for match in matches:
					warnings.append(f"{test_name}: Found suspicious zero - '{match.strip()}'")
		
		# Pattern 2: Check for dash/hyphen placeholders that might indicate missing data
		dash_patterns = [
			r'Revenue[:\|]\s*[-−–—]',
			r'Operating Income[:\|]\s*[-−–—]',
			r'Operating Cash Flow[:\|]\s*[-−–—]'
		]
		
		for pattern in dash_patterns:
			matches = re.findall(pattern, output, re.IGNORECASE)
			if matches:
				for match in matches:
					warnings.append(f"{test_name}: Found missing data placeholder - '{match.strip()}'")
		
		return warnings
	
	def _generate_summary(self, result: Dict) -> Dict:
		"""Generate executive summary of validation results."""
		summary = {
			'overall_status': 'PASS' if result.get('success') else 'FAIL',
			'security_symbol': self.symbol,
			'security_name': self.security_name,
			'data_source': None,
			'period_summary': {},
			'data_quality': {},
			'variable_replacement': {},
			'recommendations': []
		}
		
		# Data source info
		if result.get('fetch_result'):
			summary['data_source'] = result['fetch_result'].get('data_source')
			summary['period_summary'] = result['fetch_result'].get('period_counts', {})
		
		# Data quality summary
		if result.get('data_validation'):
			dv = result['data_validation']
			summary['data_quality'] = {
				'critical_fields_ok': dv.get('critical_fields_ok'),
				'annual_periods': len(dv.get('annual_periods', [])),
				'quarterly_periods': len(dv.get('quarterly_periods', [])),
				'issues_count': len(dv.get('issues', []))
			}
			
			# Add recommendations based on issues
			if dv.get('issues'):
				for issue in dv['issues'][:3]:  # Top 3 issues
					summary['recommendations'].append(issue)
		
		# Variable replacement summary
		if result.get('variable_tests'):
			vt = result['variable_tests']
			tests = vt.get('tests', [])
			passed = sum(1 for t in tests if t.get('passed'))
			total = len(tests)
			zero_warnings = len(vt.get('zero_value_warnings', []))
			
			summary['variable_replacement'] = {
				'tests_passed': passed,
				'tests_total': total,
				'success_rate': round((passed / total * 100), 2) if total > 0 else 0,
				'all_passed': vt.get('all_passed'),
				'zero_value_warnings': zero_warnings
			}
			
			# Add failed test details
			failed_tests = [t for t in tests if not t.get('passed')]
			if failed_tests:
				summary['recommendations'].append(
					f"{len(failed_tests)} variable replacement test(s) failed"
				)
			
			# Add zero-value warnings
			if zero_warnings > 0:
				summary['recommendations'].append(
					f"{zero_warnings} zero-value warning(s) found in rendered output"
				)
		
		return summary
	
	def get_diagnostic_report(self, result: Dict) -> str:
		"""
		Generate human-readable diagnostic report for AI agents.
		
		Args:
			result: Output from run_full_validation()
		
		Returns:
			Formatted diagnostic report string
		"""
		lines = []
		lines.append("=" * 80)
		lines.append("FINANCIAL PERIOD DATA VALIDATION REPORT")
		lines.append("=" * 80)
		lines.append("")
		
		# Summary section
		summary = result.get('summary', {})
		lines.append(f"STATUS: {summary.get('overall_status')}")
		lines.append(f"Security: {summary.get('security_symbol')} ({summary.get('security_name')})")
		lines.append(f"Data Source: {summary.get('data_source', 'Unknown')}")
		lines.append("")
		
		# Period counts
		lines.append("PERIOD COUNTS:")
		period_summary = summary.get('period_summary', {})
		lines.append(f"  Annual Periods: {period_summary.get('annual', 0)} (Target: 10+)")
		lines.append(f"  Quarterly Periods: {period_summary.get('quarterly', 0)} (Target: 16)")
		lines.append(f"  Total Periods: {period_summary.get('total', 0)}")
		lines.append("")
		
		# Data quality
		lines.append("DATA QUALITY:")
		dq = summary.get('data_quality', {})
		lines.append(f"  Critical Fields: {'✓ OK' if dq.get('critical_fields_ok') else '✗ ISSUES'}")
		lines.append(f"  Issues Found: {dq.get('issues_count', 0)}")
		lines.append("")
		
		# Variable replacement
		lines.append("VARIABLE REPLACEMENT TESTS:")
		vr = summary.get('variable_replacement', {})
		lines.append(f"  Tests Passed: {vr.get('tests_passed', 0)}/{vr.get('tests_total', 0)}")
		lines.append(f"  Success Rate: {vr.get('success_rate', 0)}%")
		lines.append(f"  Status: {'✓ ALL PASSED' if vr.get('all_passed') else '✗ SOME FAILED'}")
		
		# Show zero-value warnings if any
		if result.get('variable_tests', {}).get('zero_value_warnings'):
			zero_warnings = result['variable_tests']['zero_value_warnings']
			lines.append(f"  Zero-Value Warnings: {len(zero_warnings)}")
		lines.append("")
		
		# Detailed issues
		if result.get('data_validation', {}).get('issues'):
			lines.append("DATA ISSUES:")
			for issue in result['data_validation']['issues'][:15]:  # Increased from 10 to show more
				lines.append(f"  • {issue}")
			lines.append("")
		
		# Show zero-value warnings in detail
		if result.get('variable_tests', {}).get('zero_value_warnings'):
			lines.append("ZERO-VALUE WARNINGS IN RENDERED OUTPUT:")
			for warning in result['variable_tests']['zero_value_warnings'][:10]:
				lines.append(f"  • {warning}")
			lines.append("")
		
		# Failed variable tests
		if result.get('variable_tests', {}).get('tests'):
			failed = [t for t in result['variable_tests']['tests'] if not t.get('passed')]
			if failed:
				lines.append("FAILED VARIABLE TESTS:")
				for test in failed[:5]:
					lines.append(f"  • {test['name']}: {test.get('error', 'Unknown error')}")
				lines.append("")
		
		# Recommendations
		if summary.get('recommendations'):
			lines.append("RECOMMENDATIONS:")
			for rec in summary['recommendations'][:5]:
				lines.append(f"  • {rec}")
			lines.append("")
		
		# Field coverage details
		if result.get('data_validation', {}).get('field_coverage'):
			lines.append("FIELD COVERAGE BY CATEGORY:")
			for category, fields in result['data_validation']['field_coverage'].items():
				lines.append(f"  {category.replace('_', ' ').title()}:")
				for field, coverage in fields.items():
					pct = coverage['percentage']
					status = "✓" if pct >= 70 else "✗"
					lines.append(f"    {status} {field}: {pct}% ({coverage['populated']}/{coverage['total']})")
			lines.append("")
		
		lines.append("=" * 80)
		lines.append("END OF REPORT")
		lines.append("=" * 80)
		
		return "\n".join(lines)


# Convenience function for quick testing
@frappe.whitelist()
def validate_security_data(symbol: str) -> Dict:
	"""
	Validate financial period data for a security symbol.
	
	Args:
		symbol: Stock ticker symbol (e.g., "AAPL")
	
	Returns:
		Dict with validation results and diagnostic report
	
	Usage (from bench console or API):
		from cognitive_folio.cognitive_folio.doctype.cf_financial_period.test_cf_financial_period import validate_security_data
		result = validate_security_data("AAPL")
		print(result['report'])
	"""
	validator = FinancialPeriodDataValidator(symbol)
	result = validator.run_full_validation()
	
	return {
		'validation_result': result,
		'report': validator.get_diagnostic_report(result)
	}
