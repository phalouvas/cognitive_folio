import unittest
from unittest.mock import patch

from cognitive_folio.cognitive_folio.doctype.cf_chat.cf_chat import CFChat


class TestChatDeleteCleanup(unittest.TestCase):
    def test_on_trash_clears_tool_metric_last_chat_and_deletes_messages(self):
        doc = CFChat.__new__(CFChat)
        doc.name = "CHAT-DELETE-001"

        with patch("frappe.db.set_value") as mock_set_value, patch("frappe.db.delete") as mock_delete, patch(
            "frappe.db.commit"
        ) as mock_commit:
            doc.on_trash()

        mock_set_value.assert_called_once_with(
            "CF Tool Metric",
            {"last_chat": doc.name},
            "last_chat",
            None,
            update_modified=False,
        )
        mock_delete.assert_called_once_with("CF Chat Message", {"chat": doc.name})
        mock_commit.assert_called_once()
