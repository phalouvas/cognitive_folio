import frappe
from frappe.model.document import Document
import re
from cognitive_folio.utils.markdown import safe_markdown_to_html

class CFChatMessage(Document):

	def validate(self):
		if not self.system_prompt:
			chat = frappe.get_doc("CF Chat", self.chat)
			if chat.system_prompt:
				self.system_prompt = chat.system_prompt

	def before_save(self):
		# Skip processing if this is a duplicated message
		if getattr(self.flags, 'ignore_before_save', False):
			return
			
		self.status = "Processing"
		
		self.response = "Processing your request..."
		self.response_html = safe_markdown_to_html(self.response)
		
		# Enqueue the job to run after the document is saved
		frappe.db.commit()
		frappe.enqueue(
			method=self.process_in_background,
			queue="long",
			timeout=300,
			is_async=False,
			job_name=f"chat_message_{self.name}"
		)

	def process_in_background(self):
		try:
			# Reload the document from the database
			message_doc = frappe.get_doc("CF Chat Message", self.name)
			
			# Update status to processing
			message_doc.db_set("status", "Processing", update_modified=False)
			frappe.db.commit()
			
			# Process the message (use the reloaded document)
			message_doc.send()
			
			# Update status to success and save the response
			message_doc.db_set("status", "Success", update_modified=False)
			message_doc.db_update()
			frappe.db.commit()
			
			# Notify the user that the response is ready
			frappe.publish_realtime(
				event='cf_job_completed',
				message={
					'message_id': message_doc.name,
					'chat_id': message_doc.chat,
					'status': 'success'
				},
				user=message_doc.owner
			)
		except Exception as e:
			error_message = str(e)
			frappe.log_error(title=f"Chat Message Processing Error: {self.name}", message=error_message)
			
			try:
				# Reload the document and update it with error
				message_doc = frappe.get_doc("CF Chat Message", self.name)
				message_doc.response = f"Error processing request: {error_message}"
				message_doc.response_html = safe_markdown_to_html(message_doc.response)
				message_doc.db_set("status", "Failed", update_modified=False)
				message_doc.db_update()
				frappe.db.commit()
			except Exception as inner_e:
				# Log the inner exception but continue to notification
				frappe.log_error(title=f"Failed to update chat message with error: {self.name}", 
							   message=f"Original error: {error_message}\nUpdate error: {str(inner_e)}")
				# Set status to failed even if update fails
				try:
					frappe.db.set_value("CF Chat Message", self.name, "status", "Failed", update_modified=False)
					frappe.db.commit()
				except:
					pass
			
			# Always try to notify user about the error - moved outside the inner try block
			try:
				frappe.publish_realtime(
					event='cf_job_completed',
					message={
						'message_id': self.name,  # Use self.name as fallback
						'chat_id': getattr(message_doc, 'chat', self.chat),  # Use message_doc if available, else self
						'status': 'error',
						'error': error_message
					},
					user=getattr(message_doc, 'owner', self.owner)  # Use message_doc owner if available, else self
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
		portfolio = None
		if chat.portfolio:
			portfolio = frappe.get_doc("CF Portfolio", chat.portfolio)
		security = None
		if chat.security:
			security = frappe.get_doc("CF Security", chat.security)
		settings = frappe.get_single("CF Settings")
		client = OpenAI(api_key=settings.get_password('open_ai_api_key'), base_url=settings.open_ai_url)

		messages = [
			{"role": "system", "content": self.system_prompt if self.system_prompt else settings.system_content}
		]

		# Add previous messages from the chat
		chat_messages = frappe.get_all(
			"CF Chat Message",
			filters={
				"chat": chat.name,
				"name": ["!=", self.name]  # Exclude the current message
			},
			fields=["prompt", "response"]
		)
		for message in chat_messages:
			messages.append({"role": "user", "content": message.prompt})
			messages.append({"role": "assistant", "content": message.response})
		
		# Handle current message prompt
		prompt = self.prompt
		
		# Replace {{variable_name}} with actual values from self
		if portfolio:
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters={"portfolio": portfolio.name},
				fields=["name", "security"]
			)
			
			if holdings:
				# Process each holding separately and create a section for each
				holding_sections = []
				for holding_info in holdings:
					# Get both holding and security documents
					holding_doc = frappe.get_doc("CF Portfolio Holding", holding_info.name)
					security_doc = frappe.get_doc("CF Security", holding_info.security)
					
					# Replace variables for this holding
					holding_prompt = prompt
                    
					# Replace {{variable}} with security fields
					def replace_security_variables(match):
						variable_name = match.group(1)
						try:
							field_value = getattr(security_doc, variable_name, None)
							return str(field_value) if field_value is not None else ""
						except AttributeError:
							return match.group(0)
					
					# Replace [[variable]] with holding fields
					def replace_holding_variables(match):
						variable_name = match.group(1)
						try:
							field_value = getattr(holding_doc, variable_name, None)
							return str(field_value) if field_value is not None else ""
						except AttributeError:
							return match.group(0)
					
					# Replace ((variable)) with portfolio fields
					def replace_portfolio_variables(match):
						variable_name = match.group(1)
						try:
							field_value = getattr(portfolio, variable_name, None)
							return str(field_value) if field_value is not None else ""
						except AttributeError:
							return match.group(0)
					
					# Apply all replacements
					holding_prompt = re.sub(r'\{\{(\w+)\}\}', replace_security_variables, holding_prompt)
					holding_prompt = re.sub(r'\[\[(\w+)\]\]', replace_holding_variables, holding_prompt)
					holding_prompt = re.sub(r'\(\((\w+)\)\)', replace_portfolio_variables, holding_prompt)
					
					holding_sections.append(holding_prompt)
				
				# Join all holding sections
				prompt = "\n\n".join(holding_sections)
			
		elif security:
			# Only replace security variables when dealing with single security
			def replace_variables(match):
				variable_name = match.group(1)
				try:
					field_value = getattr(security, variable_name, None)
					if field_value is not None:
						return str(field_value)
					else:
						return ""
				except AttributeError:
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
		self.response_html = safe_markdown_to_html(self.response)
		self.tokens = response.usage.to_json()