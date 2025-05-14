# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CFAssetAllocation(Document):
    def validate(self):
        self.calculate_current_allocation()
        self.calculate_difference()
        self.validate_target_percentage()
        
    def validate_target_percentage(self):
        """Ensures target percentages for the same portfolio and allocation type don't exceed 100%"""
        if not self.portfolio or not self.allocation_type:
            return
            
        # Get all allocations for this portfolio and allocation type
        allocations = frappe.get_all(
            "CF Asset Allocation",
            filters={
                "portfolio": self.portfolio,
                "allocation_type": self.allocation_type,
                "name": ["!=", self.name if not self.is_new() else ""]
            },
            fields=["target_percentage"]
        )
        
        total_percentage = self.target_percentage
        for allocation in allocations:
            total_percentage += allocation.target_percentage
            
        if total_percentage > 100:
            frappe.throw(f"Total target allocation for {self.allocation_type} exceeds 100%. Please adjust your allocations.")
        
    def calculate_current_allocation(self):
        """Calculate current allocation based on holdings data"""
        if not self.portfolio or not self.allocation_type or not self.asset_class:
            return
            
        # This will need customization based on how you categorize securities
        # The default implementation is a placeholder
        
        if not frappe.db.table_exists("CF Portfolio Holding"):
            self.current_percentage = 0
            return
            
        # Get all holdings for this portfolio
        holdings = frappe.get_all(
            "CF Portfolio Holding",
            filters={"portfolio": self.portfolio},
            fields=["security", "current_value"]
        )
        
        if not holdings:
            self.current_percentage = 0
            return
            
        # Calculate total portfolio value
        total_value = sum(h.current_value for h in holdings if h.current_value)
        
        if total_value == 0:
            self.current_percentage = 0
            return
            
        # Calculate value for this asset class or category
        # This is a simplified approach - you'll need to adjust based on your data model
        asset_class_value = 0
        
        for holding in holdings:
            if holding.security and holding.current_value:
                security = frappe.get_doc("CF Security", holding.security)
                
                # Match based on allocation type
                if self.allocation_type == "Asset Class" and hasattr(security, "security_type") and security.security_type == self.asset_class:
                    asset_class_value += holding.current_value
                elif self.allocation_type == "Sector" and hasattr(security, "sector") and security.sector == self.asset_class:
                    asset_class_value += holding.current_value
                elif self.allocation_type == "Industry" and hasattr(security, "industry") and security.industry == self.asset_class:
                    asset_class_value += holding.current_value
                # Add more conditions for other allocation types as needed
                
        # Calculate percentage
        self.current_percentage = (asset_class_value / total_value) * 100 if total_value > 0 else 0
        
    def calculate_difference(self):
        """Calculate difference between target and current allocation"""
        if self.target_percentage is not None and self.current_percentage is not None:
            self.difference = self.current_percentage - self.target_percentage
