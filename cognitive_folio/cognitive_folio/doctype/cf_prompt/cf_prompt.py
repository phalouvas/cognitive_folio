# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CFPrompt(Document):
	
	@frappe.whitelist()
	def copy_prompt_to_securities(self):
		"""Copy content field from this CF Prompt to ai_prompt field of all CF Security records with security_type = 'Stock'"""
		
		# Count existing CF Security records with security_type = 'Stock'
		count_result = frappe.db.sql("SELECT COUNT(*) as count FROM `tabCF Security` WHERE security_type = 'Stock'", as_dict=True)
		total_records = count_result[0].count if count_result else 0
		
		if total_records == 0:
			frappe.msgprint("No CF Security records with security_type = 'Stock' found")
			return
		
		# Get content value (empty string if content is None or empty)
		content_value = self.content or ""
		
		# Use direct SQL update for better performance - only update Stock securities
		frappe.db.sql("""
			UPDATE `tabCF Security` 
			SET ai_prompt = %s, modified = %s, modified_by = %s
			WHERE security_type = 'Stock'
		""", (content_value, frappe.utils.now(), frappe.session.user))
		
		if content_value:
			frappe.msgprint(f"Successfully updated {total_records} Stock securities with prompt content")
		else:
			frappe.msgprint(f"Successfully cleared ai_prompt field in {total_records} Stock securities (content was empty)")
