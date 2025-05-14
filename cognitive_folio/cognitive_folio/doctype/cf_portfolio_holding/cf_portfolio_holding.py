# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.setup.utils import get_exchange_rate


class CFPortfolioHolding(Document):
    def validate(self):
        self.convert_average_purchase_price()
        self.calculate_current_value()
        self.calculate_profit_loss()
        self.calculate_allocation_percentage()
        
    def convert_average_purchase_price(self):
        """Convert average purchase price to portfolio currency if changed"""
        if self.average_purchase_price and (not self.get_doc_before_save() or 
                                          self.average_purchase_price != self.get_doc_before_save().average_purchase_price):
            # Get portfolio currency
            if not self.portfolio:
                return
                
            portfolio = frappe.get_doc("CF Portfolio", self.portfolio)
            
            # Get security currency
            if not self.security:
                return
                
            security = frappe.get_doc("CF Security", self.security)
            
            # If currencies are the same, no conversion needed
            if security.currency == portfolio.currency:
                self.base_average_purchase_price = self.average_purchase_price
            else:
                # Convert from security currency to portfolio currency
                try:
                    conversion_rate = get_exchange_rate(security.currency, portfolio.currency)
                    if conversion_rate:
                        self.base_average_purchase_price = flt(self.average_purchase_price * conversion_rate)
                except Exception as e:
                    frappe.log_error(
                        f"Currency conversion failed for purchase price: {str(e)}",
                        "Portfolio Holding Currency Conversion Error"
                    )
                    # If conversion fails, use unconverted price
                    self.base_average_purchase_price = self.average_purchase_price
    
    def calculate_current_value(self):
        """Calculate current value based on quantity and current price"""
        if self.quantity and self.current_price:
            self.current_value = flt(self.quantity * self.current_price)
            
    def calculate_profit_loss(self):
        """Calculate profit/loss based on purchase price and current value"""
        total_cost = flt(self.base_average_purchase_price * self.quantity)
        self.profit_loss = flt(self.current_value - total_cost)
            
    def calculate_allocation_percentage(self):
        """Calculate allocation percentage based on total portfolio value"""
        if not self.current_value or not self.portfolio:
            return
            
        # Get all holdings for this portfolio
        holdings = frappe.get_all(
            "CF Portfolio Holding",
            filters={"portfolio": self.portfolio, "name": ["!=", self.name]},
            fields=["current_value"]
        )
        
        # Calculate total portfolio value
        total_value = self.current_value
        for holding in holdings:
            if holding.current_value:
                total_value += holding.current_value
                
        if total_value > 0:
            self.allocation_percentage = flt((self.current_value / total_value) * 100, 2)
        else:
            self.allocation_percentage = 0
            
    def on_update(self):
        """Update parent portfolio when holdings change"""
        pass  # Add portfolio update logic when needed
