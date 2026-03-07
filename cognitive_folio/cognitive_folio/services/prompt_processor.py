import frappe

from cognitive_folio.utils.url_fetcher import fetch_and_embed_url_content


class PromptProcessor:
    """Prompt augmentation and extraction routines for chat messages."""

    def __init__(self, chat_message):
        self.chat_message = chat_message

    def prepare_prompt_without_mutation(self, prompt_text, portfolio, security):
        original_prompt = self.chat_message.prompt
        try:
            self.chat_message.prompt = prompt_text
            return self.chat_message.prepare_prompt(portfolio, security)
        finally:
            self.chat_message.prompt = original_prompt

    def extract_pdf_text_for_prompt(self, prompt_text):
        original_prompt = self.chat_message.prompt
        try:
            self.chat_message.prompt = prompt_text
            return self.chat_message.extract_pdf_text()
        finally:
            self.chat_message.prompt = original_prompt

    def embed_url_content(self, prompt_text):
        try:
            return fetch_and_embed_url_content(prompt_text, self.chat_message)
        except Exception as exc:
            frappe.log_error(
                f"URL embedding failed for message {self.chat_message.name}: {str(exc)}",
                "URL Fetch Error",
            )
            return prompt_text
