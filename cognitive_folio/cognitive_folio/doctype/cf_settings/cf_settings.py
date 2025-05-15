# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
from urllib.parse import urljoin
import json


class CFSettings(Document):
    @frappe.whitelist()
    def check_openwebui_connection(self):
        try:
            url = self.open_ai_url
            api_key = self.get_password('open_ai_api_key')
            
            # Validate required fields
            if not url:
                return {'success': False, 'error': 'Open AI URL is not configured'}
                
            if not api_key:
                return {'success': False, 'error': 'Open AI API Key is not configured'}
            
            # Ensure the URL ends with a slash for proper joining
            if not url.endswith('/'):
                url = url + '/'
            
            # Test connection by accessing the models endpoint
            api_url = urljoin(url, 'api/models')
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Parse the response to extract model data
                self.update_ai_models(response.text)
                
                # Save the document to persist the changes
                self.save()
                
                return {'success': True}
            else:
                return {
                    'success': False, 
                    'error': f'HTTP Error: {response.status_code} - {response.text}'
                }
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def update_ai_models(self, response_text):
        try:
            # Parse the JSON response
            response_data = json.loads(response_text)
            
            # Clear existing models
            self.ai_models = []
            
            # Add new models from response
            if 'data' in response_data and isinstance(response_data['data'], list):
                for model_data in response_data['data']:
                    # Create a new row for each model
                    model = {
                        'model_id': model_data.get('id', ''),
                        'model_name': model_data.get('name', ''),
                        'object_type': model_data.get('object', ''),
                        'owned_by': model_data.get('owned_by', '')
                    }
                    
                    # Store additional details as JSON
                    # Remove the fields we've already extracted to avoid duplication
                    additional_details = {k: v for k, v in model_data.items() 
                                         if k not in ['id', 'name', 'object', 'owned_by']}
                    
                    if additional_details:
                        model['additional_details'] = json.dumps(additional_details)
                    
                    self.append('ai_models', model)
            
            frappe.msgprint(f"Successfully updated {len(self.ai_models)} AI models")
            
        except Exception as e:
            frappe.log_error(f"Error updating AI models: {str(e)}", "CF Settings")
            raise