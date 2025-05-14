# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CFPortfolioHolding(Document):
    def validate(self):
        self.calculate_current_value()
        self.calculate_profit_loss()
        self.calculate_allocation_percentage()
        
    def calculate_current_value(self):
        """Calculate current value based on quantity and security price"""
        if self.security and self.quantity:
            security = frappe.get_doc("CF Security", self.security)
            self.current_value = self.quantity * security.current_price
            
    def calculate_profit_loss(self):
        """Calculate profit/loss based on purchase price and current value"""
        if self.average_purchase_price and self.quantity and self.current_value:
            total_cost = self.average_purchase_price * self.quantity
            self.profit_loss = self.current_value - total_cost
            
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
            self.allocation_percentage = (self.current_value / total_value) * 100
        else:
            self.allocation_percentage = 0
            
    def on_update(self):
        """Update parent portfolio when holdings change"""
        pass  # Add portfolio update logic when needed
