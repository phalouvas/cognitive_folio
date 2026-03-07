import unittest
from unittest.mock import patch

from cognitive_folio.cognitive_folio.doctype.cf_chat_message.cf_chat_message import CFChatMessage


class TestChatMessageDeleteCleanup(unittest.TestCase):
    def test_on_trash_clears_tool_metric_last_message_links(self):
        doc = CFChatMessage.__new__(CFChatMessage)
        doc.name = "MSG-DELETE-001"

        with patch("frappe.db.set_value") as mock_set_value:
            doc.on_trash()

        mock_set_value.assert_called_once_with(
            "CF Tool Metric",
            {"last_message": doc.name},
            "last_message",
            None,
            update_modified=False,
        )
