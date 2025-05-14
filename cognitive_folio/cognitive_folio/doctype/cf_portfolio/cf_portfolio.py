# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CFPortfolio(Document):
    def validate(self):
        self.validate_start_date()
    
    def validate_start_date(self):
        """Ensure start date is not in future"""
        if self.start_date and self.start_date > frappe.utils.today():
            frappe.throw("Start Date cannot be in the future")
    
    def on_update(self):
        """Update linked records or perform other operations when portfolio is updated"""
        pass
