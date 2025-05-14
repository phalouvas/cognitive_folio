# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, date_diff, add_months, add_days, getdate
import math


class CFPerformanceReport(Document):
    def validate(self):
        self.validate_dates()
        self.calculate_returns()
        
    def validate_dates(self):
        """Validate date ranges"""
        if self.start_date and self.end_date and self.end_date < self.start_date:
            frappe.throw("End Date cannot be before Start Date")
            
    def calculate_returns(self):
        """Calculate performance metrics"""
        if not (self.starting_value and self.ending_value):
            return
            
        # Calculate simple return value
        self.return_value = flt(self.ending_value) - flt(self.starting_value) - flt(self.deposits) + flt(self.withdrawals)
        
        # Calculate time-weighted return percentage
        adjusted_start = flt(self.starting_value)
        if adjusted_start > 0:
            self.return_percentage = (self.return_value / adjusted_start) * 100
        else:
            self.return_percentage = 0
            
        # Calculate annualized return
        if self.start_date and self.end_date and self.return_percentage:
            days = date_diff(self.end_date, self.start_date)
            if days > 0:
                # Convert to annualized return using compound interest formula
                # (1 + r)^(365/days) - 1
                daily_return = flt(self.return_percentage) / 100.0
                self.annualized_return = (math.pow(1 + daily_return, 365.0 / days) - 1) * 100
                
    def on_submit(self):
        """Actions when report is submitted"""
        self.create_next_period_report()
                
    def create_next_period_report(self):
        """Create the next period report template if this is a recurring report"""
        if self.report_period in ["Monthly", "Quarterly", "Half-Yearly", "Yearly"] and self.end_date:
            
            # Define next period dates
            next_start_date = add_days(self.end_date, 1)
            
            if self.report_period == "Monthly":
                next_end_date = add_months(next_start_date, 1)
                next_end_date = add_days(next_end_date, -1)
            elif self.report_period == "Quarterly":
                next_end_date = add_months(next_start_date, 3)
                next_end_date = add_days(next_end_date, -1)
            elif self.report_period == "Half-Yearly":
                next_end_date = add_months(next_start_date, 6)
                next_end_date = add_days(next_end_date, -1)
            elif self.report_period == "Yearly":
                next_end_date = add_months(next_start_date, 12)
                next_end_date = add_days(next_end_date, -1)
            
            # Get period name (e.g., "Jan 2025", "Q1 2025")
            period_name = self.get_period_name(next_start_date, next_end_date)
            
            # Check if report already exists
            existing_report = frappe.get_all(
                "CF Performance Report",
                filters={
                    "portfolio": self.portfolio,
                    "start_date": next_start_date,
                    "end_date": next_end_date
                }
            )
            
            if not existing_report:
                # Create next period report
                next_report = frappe.new_doc("CF Performance Report")
                next_report.portfolio = self.portfolio
                next_report.report_name = f"{self.report_period} Report - {period_name}"
                next_report.report_period = self.report_period
                next_report.start_date = next_start_date
                next_report.end_date = next_end_date
                next_report.starting_value = self.ending_value
                next_report.benchmark = self.benchmark
                next_report.save()
                
                frappe.msgprint(f"Created next {self.report_period} report: {next_report.report_name}")
    
    def get_period_name(self, start_date, end_date):
        """Generate a period name based on the start and end dates"""
        start = getdate(start_date)
        end = getdate(end_date)
        
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        if self.report_period == "Monthly":
            return f"{months[start.month-1]} {start.year}"
        elif self.report_period == "Quarterly":
            quarter = (start.month - 1) // 3 + 1
            return f"Q{quarter} {start.year}"
        elif self.report_period == "Half-Yearly":
            half = "H1" if start.month <= 6 else "H2"
            return f"{half} {start.year}"
        elif self.report_period == "Yearly":
            return f"{start.year}"
        else:
            return f"{months[start.month-1]} {start.year} - {months[end.month-1]} {end.year}"
