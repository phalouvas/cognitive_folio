# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
from urllib.parse import urljoin


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