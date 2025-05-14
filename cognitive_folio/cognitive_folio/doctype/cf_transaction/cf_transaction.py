# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CFTransaction(Document):
    def validate(self):
        self.calculate_total_amount()
        self.calculate_total_fees()
        
    def calculate_total_amount(self):
        """Calculate total amount based on quantity and price per unit"""
        if self.quantity and self.price_per_unit:
            self.total_amount = self.quantity * self.price_per_unit
            
    def calculate_total_fees(self):
        """Calculate total fees (sum of fees and commission)"""
        total = 0
        if self.fees:
            total += self.fees
        if self.commission:
            total += self.commission
        
        self.total_fees = total
        
    def on_submit(self):
        """When a transaction is submitted, update the portfolio holding"""
        self.update_portfolio_holding()
        
    def on_cancel(self):
        """When a transaction is cancelled, reverse its effect on the portfolio holding"""
        self.update_portfolio_holding(cancel=True)
        
    def update_portfolio_holding(self, cancel=False):
        """Update portfolio holding based on this transaction"""
        if not frappe.db.table_exists("CF Portfolio Holding"):
            return
            
        # Find if a holding already exists for this portfolio-security combination
        holding = frappe.get_all(
            "CF Portfolio Holding",
            filters={
                "portfolio": self.portfolio,
                "security": self.security
            },
            fields=["name", "quantity", "average_purchase_price"]
        )
        
        multiplier = -1 if cancel else 1
        
        if self.transaction_type == "Buy":
            self.process_buy_transaction(holding, multiplier)
        elif self.transaction_type == "Sell":
            self.process_sell_transaction(holding, multiplier)
        # Additional transaction types can be handled here
        
    def process_buy_transaction(self, existing_holdings, multiplier=1):
        """Process a buy transaction and update portfolio holdings"""
        if not existing_holdings:
            # Create a new holding if one doesn't exist
            if multiplier > 0:  # Only create on actual submission, not on cancellation
                holding = frappe.get_doc({
                    "doctype": "CF Portfolio Holding",
                    "portfolio": self.portfolio,
                    "security": self.security,
                    "quantity": self.quantity,
                    "average_purchase_price": self.price_per_unit
                })
                holding.insert()
            return
            
        # Update existing holding
        holding = frappe.get_doc("CF Portfolio Holding", existing_holdings[0].name)
        
        # Calculate new average purchase price and quantity
        old_quantity = holding.quantity
        old_value = old_quantity * holding.average_purchase_price
        
        new_quantity = old_quantity + (self.quantity * multiplier)
        if new_quantity <= 0:
            frappe.throw("Transaction would result in negative holdings. Please check the quantity.")
            
        new_value = old_value + (self.total_amount * multiplier)
        
        # Update the holding
        holding.quantity = new_quantity
        holding.average_purchase_price = new_value / new_quantity if new_quantity > 0 else 0
        holding.save()
        
    def process_sell_transaction(self, existing_holdings, multiplier=1):
        """Process a sell transaction and update portfolio holdings"""
        if not existing_holdings:
            frappe.throw("Cannot sell securities that are not in the portfolio")
            
        # Update existing holding
        holding = frappe.get_doc("CF Portfolio Holding", existing_holdings[0].name)
        
        # Calculate new quantity
        new_quantity = holding.quantity - (self.quantity * multiplier)
        
        if new_quantity < 0 and multiplier > 0:
            frappe.throw("Cannot sell more securities than available in the portfolio")
            
        if new_quantity == 0:
            # Delete the holding if quantity becomes zero
            frappe.delete_doc("CF Portfolio Holding", holding.name)
        else:
            # Update the holding quantity (average price remains unchanged for sells)
            holding.quantity = new_quantity
            holding.save()
