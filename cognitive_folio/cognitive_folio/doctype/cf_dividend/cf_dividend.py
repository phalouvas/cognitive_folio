# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class CFDividend(Document):
    def validate(self):
        self.validate_dates()
        self.fetch_shares_owned()
        self.calculate_amounts()
        
    def validate_dates(self):
        """Validate that payment date is after or equal to ex-dividend date"""
        if self.ex_dividend_date and self.payment_date and self.payment_date < self.ex_dividend_date:
            frappe.throw("Payment Date cannot be before Ex-Dividend Date")
            
    def fetch_shares_owned(self):
        """Fetch the number of shares owned at ex-dividend date if not provided"""
        if not self.shares_owned or flt(self.shares_owned) == 0:
            # Try to get the shares from portfolio holdings
            if not frappe.db.table_exists("CF Portfolio Holding"):
                return
                
            holdings = frappe.get_all(
                "CF Portfolio Holding",
                filters={
                    "portfolio": self.portfolio,
                    "security": self.security
                },
                fields=["quantity"]
            )
            
            if holdings and len(holdings) > 0:
                self.shares_owned = holdings[0].quantity
            else:
                # Try to calculate from transactions up to ex-dividend date
                if not frappe.db.table_exists("CF Transaction"):
                    return
                    
                total_shares = 0
                transactions = frappe.get_all(
                    "CF Transaction",
                    filters={
                        "portfolio": self.portfolio,
                        "security": self.security,
                        "transaction_date": ["<=", self.ex_dividend_date],
                        "docstatus": 1  # Only submitted transactions
                    },
                    fields=["transaction_type", "quantity"]
                )
                
                for txn in transactions:
                    if txn.transaction_type == "Buy":
                        total_shares += flt(txn.quantity)
                    elif txn.transaction_type == "Sell":
                        total_shares -= flt(txn.quantity)
                
                if total_shares > 0:
                    self.shares_owned = total_shares
    
    def calculate_amounts(self):
        """Calculate total and net amounts"""
        if self.amount_per_share and self.shares_owned:
            self.total_amount = flt(self.amount_per_share) * flt(self.shares_owned)
            
            net_amount = self.total_amount
            if self.tax_withheld:
                net_amount -= flt(self.tax_withheld)
                
            self.net_amount = net_amount if net_amount > 0 else 0
            
    def on_submit(self):
        """Create a transaction when dividend is submitted as paid"""
        if self.status == "Paid":
            self.create_dividend_transaction()
    
    def on_cancel(self):
        """Handle cancellation of dividend"""
        self.cancel_dividend_transaction()
    
    def create_dividend_transaction(self):
        """Create a transaction record for this dividend payment"""
        if not frappe.db.table_exists("CF Transaction"):
            return
            
        # Check if a transaction already exists
        existing_txn = frappe.get_all(
            "CF Transaction",
            filters={
                "portfolio": self.portfolio,
                "security": self.security,
                "transaction_type": "Dividend",
                "transaction_date": self.payment_date,
                "notes": f"Dividend payment (Ref: {self.name})"
            }
        )
        
        if existing_txn:
            return
            
        # Create transaction
        txn = frappe.get_doc({
            "doctype": "CF Transaction",
            "portfolio": self.portfolio,
            "security": self.security,
            "transaction_type": "Dividend",
            "transaction_date": self.payment_date,
            "quantity": self.shares_owned,
            "price_per_unit": self.amount_per_share,
            "total_amount": self.net_amount,
            "notes": f"Dividend payment (Ref: {self.name})"
        })
        
        txn.insert(ignore_permissions=True)
        txn.submit()
        
    def cancel_dividend_transaction(self):
        """Cancel the associated transaction if this dividend is cancelled"""
        if not frappe.db.table_exists("CF Transaction"):
            return
            
        # Find associated transaction
        transactions = frappe.get_all(
            "CF Transaction",
            filters={
                "portfolio": self.portfolio,
                "security": self.security,
                "transaction_type": "Dividend",
                "transaction_date": self.payment_date,
                "notes": f"Dividend payment (Ref: {self.name})",
                "docstatus": 1  # Submitted
            }
        )
        
        for txn_name in transactions:
            txn = frappe.get_doc("CF Transaction", txn_name.name)
            txn.cancel()
            
    def on_update(self):
        """Handle status change to Paid"""
        if not self.is_new() and self.has_value_changed("status") and self.status == "Paid" and self.docstatus == 1:
            self.create_dividend_transaction()
