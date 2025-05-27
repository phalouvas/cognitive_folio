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
		# Save a placeholder message
		self.response = "Processing your request..."
		self.response_html = frappe.utils.markdown(self.response)
		
		# Enqueue the job to run after the document is saved
		frappe.db.commit()
		frappe.enqueue(
			method=self.process_in_background,
			queue="long",
			timeout=300,
			is_async=True,
			job_name=f"chat_message_{self.name}"
		)

	def process_in_background(self):
		try:
			# Reload the document from the database
			message_doc = frappe.get_doc("CF Chat Message", self.name)
			
			# Process the message (use the reloaded document)
			message_doc.send()
			
			# Save the document with the updated response (use update_db directly)
			message_doc.db_update()
			frappe.db.commit()
			
			# Notify the user that the response is ready
			frappe.publish_realtime(
				event='chat_message_completed',
				message={
					'message_id': message_doc.name,
					'chat_id': message_doc.chat,
					'status': 'success'
				},
				user=frappe.session.user
			)
		except Exception as e:
			error_message = str(e)
			frappe.log_error(title=f"Chat Message Processing Error: {self.name}", message=error_message)
			
			try:
				# Reload the document and update it with error
				message_doc = frappe.get_doc("CF Chat Message", self.name)
				message_doc.response = f"Error processing request: {error_message}"
				message_doc.response_html = frappe.utils.markdown(message_doc.response)
				message_doc.db_update()
				frappe.db.commit()
			except Exception as inner_e:
				# Log the inner exception but continue to notification
				frappe.log_error(title=f"Failed to update chat message with error: {self.name}", 
							   message=f"Original error: {error_message}\nUpdate error: {str(inner_e)}")
			
			# Always try to notify user about the error - moved outside the inner try block
			try:
				frappe.publish_realtime(
					event='chat_message_completed',
					message={
						'message_id': self.name,  # Use self.name as fallback
						'chat_id': getattr(message_doc, 'chat', self.chat),  # Use message_doc if available, else self
						'status': 'error',
						'error': error_message
					},
					user=frappe.session.user
				)
				
				# Add a system notification as a backup method
				frappe.publish_realtime(
					event='eval_js',
					message='frappe.show_alert({message: "Chat message processing failed. Please check the chat for details.", indicator: "red"});',
					user=frappe.session.user
				)
			except Exception as notify_e:
				# Last resort - log that we couldn't even notify the user
				frappe.log_error(title=f"Failed to notify user of chat error: {self.name}", 
							   message=f"Original error: {error_message}\nNotification error: {str(notify_e)}")

	def send(self):
		
		try:
			from openai import OpenAI			
		except ImportError:
			frappe.throw("OpenAI package is not installed. Please run 'bench pip install openai'")
			return 0
		
		chat = frappe.get_doc("CF Chat", self.chat)
		portfolio = frappe.get_doc("CF Portfolio", chat.portfolio)
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
				if security:
					field_value = getattr(security, variable_name, None)
				elif portfolio:
					field_value = getattr(portfolio, variable_name, None)
				else:
					field_value = None
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