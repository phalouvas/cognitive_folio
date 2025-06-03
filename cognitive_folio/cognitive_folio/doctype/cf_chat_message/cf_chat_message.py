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

	@frappe.whitelist()
	def process(self):
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
			now=False,
			job_id=f"chat_message_{self.name}"
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
					'status': 'success',
					'message': f"Response ready for message {message_doc.name}"
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
						'message': f"Error processing message {self.name}: {error_message}"
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

			# Replace ((variable)) with portfolio fields once at the end
			def replace_portfolio_variables(match):
				variable_name = match.group(1)
				try:
					field_value = getattr(portfolio, variable_name, None)
					return str(field_value) if field_value is not None else ""
				except AttributeError:
					return match.group(0)
			
			prompt = re.sub(r'\(\((\w+)\)\)', replace_portfolio_variables, prompt)
			
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters={"portfolio": portfolio.name},
				fields=["name", "security"]
			)
			
			if holdings:
				# Find all ***HOLDINGS*** sections in the prompt
				holdings_pattern = r'\*\*\*HOLDINGS\*\*\*(.*?)\*\*\*HOLDINGS\*\*\*'
				holdings_matches = re.findall(holdings_pattern, prompt, re.DOTALL)
				
				if holdings_matches:
					# Process each holding separately and create sections for each
					all_holding_sections = []
					
					for holding_info in holdings:
						# Get both holding and security documents
						holding_doc = frappe.get_doc("CF Portfolio Holding", holding_info.name)
						security_doc = frappe.get_doc("CF Security", holding_info.security)
						
						# Process each ***HOLDINGS*** section for this holding
						holding_sections = []
						for holdings_content in holdings_matches:
							holding_prompt = holdings_content
							
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
							
							# Apply security and holding replacements
							holding_prompt = re.sub(r'\{\{(\w+)\}\}', replace_security_variables, holding_prompt)
							holding_prompt = re.sub(r'\[\[(\w+)\]\]', replace_holding_variables, holding_prompt)
							
							holding_sections.append(holding_prompt)
						
						# Join sections for this holding
						all_holding_sections.append("***HOLDINGS***" + "***HOLDINGS******HOLDINGS***".join(holding_sections) + "***HOLDINGS***")
					
					# Replace all ***HOLDINGS*** sections in the original prompt with processed content
					# First, get the content before first and after last ***HOLDINGS*** markers
					parts = re.split(r'\*\*\*HOLDINGS\*\*\*.*?\*\*\*HOLDINGS\*\*\*', prompt, flags=re.DOTALL)
					
					# Reconstruct the prompt with all holdings processed
					final_parts = []
					final_parts.append(parts[0])  # Content before first ***HOLDINGS***
					
					for holding_section in all_holding_sections:
						# Remove the ***HOLDINGS*** markers from the processed content
						clean_holding_section = holding_section.replace("***HOLDINGS***", "")
						final_parts.append(clean_holding_section)
					
					if len(parts) > 1:
						final_parts.append(parts[-1])  # Content after last ***HOLDINGS***
					
					prompt = "\n\n".join(final_parts)
				
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

		# Extract text from PDF attachments if PdfReader is available
		try:
			from PyPDF2 import PdfReader
			pdf_text = self.extract_pdf_text()
			if pdf_text:
				prompt += "\n\n--- File Content ---\n" + pdf_text
				# Update the last message with the PDF content
				messages[-1]["content"] = prompt
		except ImportError:
			# PdfReader not available, continue without PDF extraction
			pass

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

	def extract_pdf_text(self):
		"""Extract text from PDF attachments of the current chat message"""
		try:
			from PyPDF2 import PdfReader
			import os
		except ImportError:
			return ""
		
		pdf_texts = []
		
		# Get file attachments for current chat message only
		files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "CF Chat Message",
				"attached_to_name": self.name,
				"file_url": ["like", "%.pdf"]
			},
			fields=["file_url", "file_name"]
		)
		
		for file_info in files:
			try:
				# Get the full file path
				file_path = frappe.get_site_path() + file_info.file_url
				
				if os.path.exists(file_path):
					# Extract text from PDF
					with open(file_path, 'rb') as pdf_file:
						pdf_reader = PdfReader(pdf_file)
						text_content = ""
						
						for page in pdf_reader.pages:
							text_content += page.extract_text() + "\n"
						
						if text_content.strip():
							pdf_texts.append(f"--- {file_info.file_name} ---\n{text_content.strip()}")
			
			except Exception as e:
				frappe.log_error(f"Error extracting PDF text from {file_info.file_name}: {str(e)}")
				continue
		
		return "\n\n".join(pdf_texts) if pdf_texts else ""