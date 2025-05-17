# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
from urllib.parse import urljoin
import json
from openai import OpenAI


class CFSettings(Document):
    @frappe.whitelist()
    def check_openwebui_connection(self):
        try:
            client = OpenAI(api_key=self.get_password('open_ai_api_key'), base_url=self.open_ai_url)
            response = client.models.list()
            self.update_ai_models(response.data)
            self.save()
            return {'success': True}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def update_ai_models(self, response_data):
        try:
            
            # Clear existing models
            self.ai_models = []
            
            # Add new models from response
            for model_data in response_data:
                # Create a new row for each model
                model = {
                    'model_id': model_data.id,
                    'object_type': model_data.object,
                    'owned_by': model_data.owned_by
                }
                
                self.append('ai_models', model)
            
            frappe.msgprint(f"Successfully updated {len(self.ai_models)} AI models")
            
        except Exception as e:
            frappe.log_error(f"Error updating AI models: {str(e)}", "CF Settings")
            raise