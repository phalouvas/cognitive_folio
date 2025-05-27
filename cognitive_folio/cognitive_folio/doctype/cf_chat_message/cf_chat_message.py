import frappe
from frappe.model.document import Document
import re


class CFChatMessage(Document):

	def validate(self):
		if not self.system_prompt:
			chat = frappe.get_doc("CF Chat", self.chat)
			if chat.system_prompt:
				self.system_prompt = chat.system_prompt

	def before_save(self):
		
		try:
			from openai import OpenAI			
		except ImportError:
			frappe.throw("OpenAI package is not installed. Please run 'bench pip install openai'")
			return 0
		
		chat = frappe.get_doc("CF Chat", self.chat)
		security = frappe.get_doc("CF Security", chat.security)
		settings = frappe.get_single("CF Settings")
		client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)

		messages = [
			{"role": "system", "content": self.system_prompt if self.system_prompt else settings.system_content}
		]

		# Add previous messages from the chat
		chat_messages = frappe.get_all(
			"CF Chat Message",
			filters={"chat": chat.name},
			fields=["prompt", "response"]
		)
		for message in chat_messages:
			messages.append({"role": "user", "content": message.prompt})
			messages.append({"role": "assistant", "content": message.response})
		
		# Handle current message prompt
		prompt = self.prompt
		
		# Replace {{variable_name}} with actual values from self
		def replace_variables(match):
			variable_name = match.group(1)
			try:
				# Get the actual field value from the document
				field_value = getattr(security, variable_name, None)
				if field_value is not None:
					return str(field_value)
				else:
					# Field exists but is None/empty, return empty string
					return ""
			except AttributeError:
				# Field doesn't exist in this doctype, return original placeholder
				return match.group(0)
		
		prompt = re.sub(r'\{\{(\w+)\}\}', replace_variables, prompt)
		messages.append({"role": "user", "content": prompt})

		response = client.chat.completions.create(
			model=self.model,
			messages=messages,
			stream=False,
			temperature=0.2
		)

		self.prompt = prompt
		self.response = response.choices[0].message.content if response.choices else "No response from OpenAI"
		self.response_html = frappe.utils.markdown(self.response)
		self.tokens = response.usage.to_json()