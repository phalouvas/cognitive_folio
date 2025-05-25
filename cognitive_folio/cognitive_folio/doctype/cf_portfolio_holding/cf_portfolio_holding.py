# Copyright (c) 2025, YourCompany and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.setup.utils import get_exchange_rate
import json
from frappe import _

class CFPortfolioHolding(Document):

    def onload(self):
        if not self.ai_suggestion:
            ai_suggestion = frappe.get_value("CF Security", self.security, "ai_suggestion")
            self.ai_suggestion = ai_suggestion

    def validate(self):
        self.convert_average_purchase_price()
        self.calculate_current_value()
        self.calculate_dividend_data()
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
                    if security.currency.upper() == 'GBP':
                        conversion_rate = conversion_rate / 100
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

        if self.security:
            security = frappe.get_doc("CF Security", self.security)
            portfolio = frappe.get_doc("CF Portfolio", self.portfolio)
            conversion_rate = get_exchange_rate(security.currency, portfolio.currency)
            if security.currency.upper() == 'GBP':
                conversion_rate = conversion_rate / 100
            price_in_security_currency = flt(security.current_price)
            self.current_price = flt(price_in_security_currency * conversion_rate)
        else:
            return

        if self.quantity and self.current_price:
            self.current_value = flt(self.quantity * self.current_price)
            
    def calculate_profit_loss(self):
        """Calculate profit/loss based on purchase price and current value"""
        self.base_cost = flt(self.base_average_purchase_price * self.quantity)
        self.profit_loss = flt(self.current_value + self.total_dividend_income - self.base_cost)
        self.profit_loss_percentage = flt((self.profit_loss / self.base_cost) * 100, 2)

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

        return self.allocation_percentage
            
    def on_update(self):
        """Update parent portfolio when holdings change"""
        # get all holdings for this portfolio except this one
        holdings = frappe.get_all(
            "CF Portfolio Holding",
            filters={"portfolio": self.portfolio, "name": ["!=", self.name]},
            fields=["name"]
        )
        # for each holding, calculate_allocation_percentage
        for holding in holdings:
            holding_doc = frappe.get_doc("CF Portfolio Holding", holding.name)
            allocation_percentage = holding_doc.calculate_allocation_percentage()
            # update the holding directly
            holding_doc.db_set("allocation_percentage", allocation_percentage)
            
    @frappe.whitelist()
    def fetch_current_price(self):

        if self.security_type == "Cash":
            return {"success": True}
        
        """Fetch the current price from the related security"""
        if not self.security:
            frappe.throw("Security must be specified to fetch current price.")
            
        try:
            # Get the security document
            security = frappe.get_doc("CF Security", self.security)
            security.fetch_current_price()

            return {"success": True}
        except Exception as e:
            frappe.log_error(f"Error fetching current price: {str(e)}", "Portfolio Holding Error")
            frappe.throw("Error fetching current price. Please check the security.")

    @frappe.whitelist()
    def fetch_fundamentals(self):

        if self.security_type == "Cash":
            return {"success": True}
        
        """Fetch the current price from the related security"""
        if not self.security:
            frappe.throw("Security must be specified to fetch current price.")
            
        try:
            # Get the security document
            security = frappe.get_doc("CF Security", self.security)
            security.fetch_fundamentals()
            
            return {"success": True}
        except Exception as e:
            frappe.log_error(f"Error fetching current price: {str(e)}", "Portfolio Holding Error")
            frappe.throw("Error fetching current price. Please check the security.")
            
    @frappe.whitelist()
    def generate_ai_suggestion(self):
        """Generate AI suggestion for the holding via the security"""

        if self.security_type == "Cash":
            return {'success': True}

        if not self.security:
            return {'success': False, 'error': 'No security specified'}
            
        try:
            # Get the security document
            security = frappe.get_doc("CF Security", self.security)
            
            # Call the generate_ai_suggestion method on the security
            result = security.generate_ai_suggestion()
            
            # Pass through the result
            return result
        except Exception as e:
            frappe.log_error(f"Error generating AI suggestion: {str(e)}", "Portfolio Holding Error")
            return {'success': False, 'error': str(e)}

    def calculate_dividend_data(self):
        """Calculate dividend yield and yearly dividend income"""
        if not self.ticker_info:
            return
            
        try:
            # Parse ticker_info JSON if it's a string
            if isinstance(self.ticker_info, str):
                ticker_data = json.loads(self.ticker_info)
            else:
                ticker_data = self.ticker_info
                
            # Get dividend yield from ticker data
            if ticker_data.get("dividendYield"):
                self.dividend_yield = flt(ticker_data.get("dividendYield"), 2)
            
            # Get latest dividend from dividend history
            security = frappe.get_doc("CF Security", self.security)
            if security.dividends:
                # get portfolio start_date
                portfolio = frappe.get_doc("CF Portfolio", self.portfolio)
                dividends = json.loads(security.dividends) if isinstance(security.dividends, str) else security.dividends
                if dividends:
                    # Sort dates in descending order to get the most recent one
                    dates = sorted(dividends.keys(), reverse=True)
                    if dates:
                        # Calculate total dividend income since portfolio start date
                        total_dividend_income = 0
                        from datetime import datetime

                        for date_str in dates:
                            # Convert string date to datetime.date object for comparison
                            try:
                                # Handle full ISO format date string (YYYY-MM-DDTHH:MM:SS.sssZ)
                                if 'T' in date_str:
                                    # Parse ISO 8601 format with time component
                                    dividend_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                                else:
                                    # Handle simple YYYY-MM-DD format
                                    dividend_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                                
                                # Convert portfolio.start_date to datetime.date if it's a string
                                portfolio_start_date = portfolio.start_date
                                if isinstance(portfolio_start_date, str):
                                    portfolio_start_date = datetime.strptime(portfolio_start_date, '%Y-%m-%d').date()
                                
                                # Only count dividends after portfolio start date
                                if portfolio_start_date and dividend_date >= portfolio_start_date:
                                    total_dividend_income += flt(dividends[date_str]) * self.quantity
                            except ValueError as e:
                                # Skip if date format is invalid
                                frappe.log_error(
                                    f"Invalid date format in dividend data: {date_str}, error: {str(e)}",
                                    "Portfolio Holding Dividend Calculation Error"
                                )

                        # Convert total dividend income to portfolio currency if needed
                        if total_dividend_income > 0 and security.currency != portfolio.currency:
                            try:
                                conversion_rate = get_exchange_rate(security.currency, portfolio.currency)
                                if security.currency.upper() == 'GBP':
                                    conversion_rate = conversion_rate / 100
                                total_dividend_income = flt(total_dividend_income * conversion_rate)
                            except Exception as e:
                                frappe.log_error(
                                    f"Currency conversion failed for dividend total: {str(e)}",
                                    "Portfolio Holding Dividend Currency Conversion Error"
                                )

                        self.total_dividend_income = flt(total_dividend_income, 2)
                
        except Exception as e:
            frappe.log_error(
                f"Dividend calculation failed: {str(e)}",
                "Portfolio Holding Dividend Calculation Error"
            )
