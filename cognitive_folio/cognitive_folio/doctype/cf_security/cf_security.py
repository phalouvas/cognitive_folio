# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class CFSecurity(Document):
    def validate(self):
        self.validate_isin()
        self.set_last_updated()
    
    def validate_isin(self):
        """Validate ISIN format if provided"""
        if self.isin:
            # ISIN is a 12-character alphanumeric code
            if len(self.isin) != 12:
                frappe.throw("ISIN must be 12 characters long")
            
            # Basic format validation: 2 letters country code + 9 alphanumeric + 1 check digit
            if not (self.isin[:2].isalpha() and self.isin[2:11].isalnum() and self.isin[11].isalnum()):
                frappe.throw("ISIN format is invalid. It should be 2 letters country code followed by 9 alphanumeric characters and 1 check digit")
    
    def set_last_updated(self):
        """Update the last_updated timestamp when price changes"""
        if self.is_new() or self.has_value_changed("current_price"):
            self.last_updated = now_datetime()
            
    def on_update(self):
        """Update related documents when a security is updated"""
        self.update_portfolio_holdings()
            
    def update_portfolio_holdings(self):
        """Update the value of portfolio holdings that contain this security"""
        if self.has_value_changed("current_price"):
            # Check if CF Portfolio Holding DocType exists before trying to access it
            if frappe.db.table_exists("CF Portfolio Holding"):
                holdings = frappe.get_all(
                    "CF Portfolio Holding",
                    filters={"security": self.name},
                    fields=["name"]
                )
                
                for holding in holdings:
                    # Trigger value recalculation in each holding
                    holding_doc = frappe.get_doc("CF Portfolio Holding", holding.name)
                    holding_doc.save()
