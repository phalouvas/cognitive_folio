import frappe
from frappe.model.document import Document


class CFChatMessage(Document):
	
	def before_insert(self):
		
		try:
			from openai import OpenAI			
		except ImportError:
			frappe.throw("OpenAI package is not installed. Please run 'bench pip install openai'")
			return 0
		
		chat = frappe.get_doc("CF Chat", self.chat)
		settings = frappe.get_single("CF Settings")
		client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)
		
		prompt = self.prompt

		messages = [
			{"role": "system", "content": chat.system_content if chat.system_content else "You are a helpful assistant."},
			{"role": "user", "content": prompt}			
		]

		response = client.chat.completions.create(
			model=self.model,
			messages=messages,
			stream=False,
			temperature=0.2
		)

		self.response = response.choices[0].message.content if response.choices else "No response from OpenAI"
		self.tokens = response.usage.to_json()
		pass