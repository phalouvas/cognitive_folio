# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CFChat(Document):
    def on_trash(self):
        """Delete all related chat messages before deleting the chat"""
        # Delete all cf_chat_messages linked to this chat
        frappe.db.delete("CF Chat Message", {"chat": self.name})
        
        # Commit the deletion of child records
        frappe.db.commit()
