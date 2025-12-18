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

    def after_insert(self):
        """If duplicated_from then copy the chat messages from the original chat"""
        if self.duplicated_from:
            # Fetch messages from the cf_chat_message doctype
            messages = frappe.get_all(
                "CF Chat Message",
                filters={"chat": self.duplicated_from},
                fields=["name"],
                order_by="creation asc"
            )
            for message in messages:
                old_message = frappe.get_doc("CF Chat Message", message.name)
                new_message = frappe.copy_doc(old_message)
                new_message.chat = self.name
                new_message.flags.ignore_before_save = True
                new_message.insert()

@frappe.whitelist()
def amend_cf_chat(name):
    doc = frappe.get_doc("CF Chat", name)
    doc.status = "Cancelled"
    new_doc = frappe.copy_doc(doc)
    new_doc.duplicated_from = doc.name
    new_doc.title = f"{doc.title} (Amended)"
    new_doc.insert()
    return new_doc.name
