import frappe


@frappe.whitelist()
def submit_user_feedback(chat_message, rating, feedback_text=None):
    if not frappe.db.exists("DocType", "CF User Feedback"):
        return {"ok": False, "reason": "doctype_missing"}

    rating_value = max(1, min(5, int(rating or 0)))
    message_doc = frappe.get_doc("CF Chat Message", chat_message)

    doc = frappe.get_doc(
        {
            "doctype": "CF User Feedback",
            "feedback_date": frappe.utils.nowdate(),
            "chat": message_doc.chat,
            "chat_message": message_doc.name,
            "rating": rating_value,
            "feedback_text": str(feedback_text or "")[:2000],
            "user": frappe.session.user,
        }
    )
    doc.insert(ignore_permissions=True)
    return {"ok": True, "name": doc.name}
