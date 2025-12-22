# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCFSecurity(FrappeTestCase):
	def setUp(self):
		"""Create a test security"""
		self.security = frappe.new_doc("CF Security")
		self.security.security_name = "Test Security"
		self.security.symbol = "TEST"
		self.security.security_type = "Stock"
		self.security.currency = "USD"
		self.security.current_price = 100
		self.security.suggestion_buy_price = 95
		self.security.suggestion_sell_price = 110
	
	def test_price_alert_status_no_alert(self):
		"""Test price_alert_status is empty when current_price is between thresholds"""
		self.security.current_price = 100
		self.security.save()
		
		doc = frappe.get_doc("CF Security", self.security.symbol)
		self.assertEqual(doc.price_alert_status, "")
	
	def test_price_alert_status_buy_signal(self):
		"""Test price_alert_status is 'Buy Signal' when current_price <= suggestion_buy_price"""
		self.security.current_price = 90
		self.security.save()
		
		doc = frappe.get_doc("CF Security", self.security.symbol)
		self.assertEqual(doc.price_alert_status, "Buy Signal")
	
	def test_price_alert_status_sell_signal(self):
		"""Test price_alert_status is 'Sell Signal' when current_price >= suggestion_sell_price"""
		self.security.current_price = 115
		self.security.save()
		
		doc = frappe.get_doc("CF Security", self.security.symbol)
		self.assertEqual(doc.price_alert_status, "Sell Signal")
	
	def test_price_alert_status_at_buy_price_boundary(self):
		"""Test price_alert_status when current_price equals suggestion_buy_price"""
		self.security.current_price = 95
		self.security.save()
		
		doc = frappe.get_doc("CF Security", self.security.symbol)
		self.assertEqual(doc.price_alert_status, "Buy Signal")
	
	def test_price_alert_status_at_sell_price_boundary(self):
		"""Test price_alert_status when current_price equals suggestion_sell_price"""
		self.security.current_price = 110
		self.security.save()
		
		doc = frappe.get_doc("CF Security", self.security.symbol)
		self.assertEqual(doc.price_alert_status, "Sell Signal")
	
	def test_price_alert_status_no_thresholds(self):
		"""Test price_alert_status is empty when thresholds are not set"""
		self.security.suggestion_buy_price = None
		self.security.suggestion_sell_price = None
		self.security.save()
		
		doc = frappe.get_doc("CF Security", self.security.symbol)
		self.assertEqual(doc.price_alert_status, "")
	
	def test_price_alert_status_no_current_price(self):
		"""Test price_alert_status is empty when current_price is not set"""
		self.security.current_price = None
		self.security.save()
		
		doc = frappe.get_doc("CF Security", self.security.symbol)
		self.assertEqual(doc.price_alert_status, "")

