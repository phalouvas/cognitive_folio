import frappe
from frappe.model.document import Document
import re
from cognitive_folio.utils.markdown import safe_markdown_to_html
from cognitive_folio.utils.helper import replace_variables

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
		self.save()
		
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
			import tiktoken
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

		# Initialize tokenizer for the model
		try:
			encoding = tiktoken.encoding_for_model(self.model)
		except KeyError:
			# Fallback to a common encoding if model not found
			encoding = tiktoken.get_encoding("cl100k_base")

		messages = [
			{"role": "system", "content": self.system_prompt if self.system_prompt else settings.system_content}
		]

		# Add previous messages from the chat with token management
		chat_messages = frappe.get_all(
			"CF Chat Message",
			filters={
				"chat": chat.name,
				"name": ["!=", self.name]  # Exclude the current message
			},
			fields=["prompt", "response"],
			order_by="creation desc"  # Get most recent messages first
		)
		
		# Calculate tokens for system message and reserve space for current prompt
		system_tokens = len(encoding.encode(messages[0]["content"]))
		max_context_tokens = 60000  # Leave buffer for response
		available_tokens = max_context_tokens - system_tokens
		
		# Process current message prompt first to know how much space it needs
		self.prompt = self.prepare_prompt(portfolio, security)
		
		# Extract PDF text and replace file references if available
		try:
			from PyPDF2 import PdfReader
			self.prompt = self.extract_pdf_text()
		except ImportError:
			pass
		
		current_prompt_tokens = len(encoding.encode(self.prompt))
		available_tokens -= current_prompt_tokens
		
		# Add previous messages while staying within token limit
		used_tokens = 0
		for message in chat_messages:  # Already ordered by most recent first
			user_tokens = len(encoding.encode(message.prompt))
			assistant_tokens = len(encoding.encode(message.response))
			message_tokens = user_tokens + assistant_tokens
			
			if used_tokens + message_tokens > available_tokens:
				break  # Stop adding messages if we exceed token limit
				
			# Insert at position 1 to maintain chronological order (after system message)
			messages.insert(1, {"role": "user", "content": message.prompt})
			messages.insert(2, {"role": "assistant", "content": message.response})
			used_tokens += message_tokens
		
		# Add current message
		messages.append({"role": "user", "content": self.prompt})

		response = client.chat.completions.create(
			model=self.model,
			messages=messages,
			stream=False,
			temperature=0.2
		)

		self.response = response.choices[0].message.content if response.choices else "No response from OpenAI"
		self.response_html = safe_markdown_to_html(self.response)
		self.tokens = response.usage.to_json()

	def prepare_prompt(self, portfolio, security):
		"""Prepare the prompt with variable replacements"""
		prompt = self.prompt
		
		# Replace ((variable)) with portfolio fields
		if portfolio:
			prompt = re.sub(r'\(\((\w+)\)\)', lambda match: replace_variables(match, portfolio), prompt)
			
			# Handle holdings processing (existing code)
			holdings = frappe.get_all(
				"CF Portfolio Holding",
				filters={"portfolio": portfolio.name},
				fields=["name", "security"]
			)
			
			if holdings:
				holdings_pattern = r'\*\*\*HOLDINGS\*\*\*(.*?)\*\*\*HOLDINGS\*\*\*'
				holdings_matches = re.findall(holdings_pattern, prompt, re.DOTALL)
				
				if holdings_matches:
					all_holding_sections = []
					
					for holding_info in holdings:
						holding_doc = frappe.get_doc("CF Portfolio Holding", holding_info.name)
						security_doc = frappe.get_doc("CF Security", holding_info.security)
						
						holding_sections = []
						for holdings_content in holdings_matches:
							holding_prompt = holdings_content
							
							holding_prompt = re.sub(r'\{\{([\w\.]+)\}\}', lambda match: replace_variables(match, security_doc), holding_prompt)
							holding_prompt = re.sub(r'\[\[([\w\.]+)\]\]', lambda match: replace_variables(match, holding_doc), holding_prompt)
							
							holding_sections.append(holding_prompt)
						
						all_holding_sections.append("***HOLDINGS***" + "***HOLDINGS******HOLDINGS***".join(holding_sections) + "***HOLDINGS***")
					
					parts = re.split(r'\*\*\*HOLDINGS\*\*\*.*?\*\*\*HOLDINGS\*\*\*', prompt, flags=re.DOTALL)
					
					final_parts = []
					final_parts.append(parts[0])
					
					for holding_section in all_holding_sections:
						clean_holding_section = holding_section.replace("***HOLDINGS***", "")
						final_parts.append(clean_holding_section)
					
					if len(parts) > 1:
						final_parts.append(parts[-1])
					
					prompt = "\n\n".join(final_parts)
		
		elif security:
			prompt = re.sub(r'\{\{([\w\.]+)\}\}', lambda match: replace_variables(match, security), prompt)
		
		return prompt

	def extract_pdf_text(self):
		"""Extract text from specific PDF files referenced in the prompt"""
		try:
			from PyPDF2 import PdfReader
			import os
			import html
		except ImportError:
			return self.prompt
		
		prompt = self.prompt
		
		# First, decode any HTML entities
		prompt = html.unescape(prompt)
		
		# Find all PDF file references in both formats:
		# <<filename.pdf>> and &lt;&lt;filename.pdf&gt;&gt;
		pdf_references = []
		
		# Pattern for normal angle brackets
		normal_pattern = r'<<([^>]+\.pdf)>>'
		pdf_references.extend(re.findall(normal_pattern, prompt, re.IGNORECASE))
		
		# Pattern for HTML encoded angle brackets
		encoded_pattern = r'&lt;&lt;([^&]+\.pdf)&gt;&gt;'
		pdf_references.extend(re.findall(encoded_pattern, prompt, re.IGNORECASE))
		
		if not pdf_references:
			return prompt
		
		# Get all file attachments for current chat message
		files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "CF Chat Message",
				"attached_to_name": self.name,
				"file_url": ["like", "%.pdf"]
			},
			fields=["file_url", "file_name"]
		)
		
		# Create a mapping of file names to file info
		file_mapping = {}
		for file_info in files:
			file_mapping[file_info.file_name.lower()] = file_info
		
		# Replace each PDF reference with its content
		for pdf_filename in pdf_references:
			pdf_key = pdf_filename.lower()
			
			if pdf_key in file_mapping:
				file_info = file_mapping[pdf_key]
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
								# Replace the reference with the file content
								replacement = f"--- Content of {file_info.file_name} ---\n{text_content.strip()}"
								
								# Replace both normal and encoded versions
								prompt = prompt.replace(f"<<{pdf_filename}>>", replacement)
								prompt = prompt.replace(f"&lt;&lt;{pdf_filename}&gt;&gt;", replacement)
							else:
								# Replace with message indicating no text found
								no_text_msg = f"[No readable text found in {file_info.file_name}]"
								prompt = prompt.replace(f"<<{pdf_filename}>>", no_text_msg)
								prompt = prompt.replace(f"&lt;&lt;{pdf_filename}&gt;&gt;", no_text_msg)
				
				except Exception as e:
					frappe.log_error(f"Error extracting PDF text from {file_info.file_name}: {str(e)}")
					# Replace with error message
					error_msg = f"[Error reading {file_info.file_name}]"
					prompt = prompt.replace(f"<<{pdf_filename}>>", error_msg)
					prompt = prompt.replace(f"&lt;&lt;{pdf_filename}&gt;&gt;", error_msg)
			else:
				# File not found, replace with message
				not_found_msg = f"[File {pdf_filename} not found in attachments]"
				prompt = prompt.replace(f"<<{pdf_filename}>>", not_found_msg)
				prompt = prompt.replace(f"&lt;&lt;{pdf_filename}&gt;&gt;", not_found_msg)
		
		return prompt