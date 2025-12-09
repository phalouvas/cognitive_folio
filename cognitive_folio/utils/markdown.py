import frappe
import re
import html
from frappe.utils import md_to_html, sanitize_html


def safe_markdown_to_html(text):
    """
    Safely convert markdown text to HTML with fallback handling.
    
    Args:
        text (str): Markdown text to convert
        
    Returns:
        str: HTML content
    """
    if not text:
        return ""
    
    try:
        # Sanitize text before markdown conversion
        sanitized_text = sanitize_markdown_content(text)

        # Convert using markdown renderer directly to avoid is_html short-circuit
        html_content = md_to_html(sanitized_text)

        # If conversion yielded output, sanitize it; else fallback
        if html_content and html_content.strip():
            return sanitize_html(html_content)
        else:
            return fallback_text_to_html(text)
            
    except Exception as e:
        # Log the error and use fallback
        frappe.log_error(
            title="Markdown Conversion Error",
            message=f"Failed to convert markdown: {str(e)}\nOriginal text length: {len(text)}"
        )
        return fallback_text_to_html(text)


def sanitize_markdown_content(text):
    """
    Sanitize markdown content to prevent parsing issues.
    
    Args:
        text (str): Raw markdown text
        
    Returns:
        str: Sanitized markdown text
    """
    if not text:
        return text
    
    # Replace patterns that could be mistaken for HTML tags
    # Handle < followed by numbers/percentages (e.g., <20%, <10%)
    text = re.sub(r'<(\d+[%\w]*)', r'&lt;\1', text)
    
    # Handle other problematic < patterns that aren't proper HTML tags
    # This regex looks for < followed by non-HTML tag patterns
    text = re.sub(r'<(?![a-zA-Z/!?\s])', '&lt;', text)
    
    # Handle other common problematic characters in tables
    text = text.replace('10%+', '10%&#43;')
    
    return text


def fallback_text_to_html(text):
    """
    Fallback method to convert plain text to HTML with basic formatting.
    
    Args:
        text (str): Plain text
        
    Returns:
        str: Basic HTML with preserved formatting
    """
    if not text:
        return ""
    
    # Escape HTML characters
    escaped_text = html.escape(text)
    
    # Convert line breaks to HTML breaks
    html_content = escaped_text.replace('\n', '<br>')
    
    # Convert basic markdown patterns manually
    # Bold text **text** -> <strong>text</strong>
    html_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_content)
    
    # Italic text *text* -> <em>text</em>
    html_content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html_content)
    
    # Headers ### -> <h3>
    html_content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
    html_content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
    html_content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)
    
    return html_content


def markdown_to_html_with_validation(text, validate_tables=True):
    """
    Convert markdown to HTML with optional table validation.
    
    Args:
        text (str): Markdown text
        validate_tables (bool): Whether to validate table syntax
        
    Returns:
        dict: {
            'html': str,
            'success': bool,
            'method': str,  # 'markdown' or 'fallback'
            'warnings': list
        }
    """
    warnings = []
    
    if not text:
        return {
            'html': '',
            'success': True,
            'method': 'markdown',
            'warnings': []
        }
    
    # Check for potential table issues if validation is enabled
    if validate_tables and '|' in text:
        table_issues = validate_markdown_tables(text)
        if table_issues:
            warnings.extend(table_issues)
    
    try:
        sanitized_text = sanitize_markdown_content(text)
        html_content = md_to_html(sanitized_text)

        if html_content and html_content.strip():
            return {
                'html': sanitize_html(html_content),
                'success': True,
                'method': 'markdown',
                'warnings': warnings
            }
        else:
            return {
                'html': fallback_text_to_html(text),
                'success': False,
                'method': 'fallback',
                'warnings': warnings + ['Markdown conversion returned empty or unchanged content']
            }
            
    except Exception as e:
        return {
            'html': fallback_text_to_html(text),
            'success': False,
            'method': 'fallback',
            'warnings': warnings + [f'Markdown conversion failed: {str(e)}']
        }


def validate_markdown_tables(text):
    """
    Validate markdown table syntax and return potential issues.
    
    Args:
        text (str): Markdown text containing tables
        
    Returns:
        list: List of validation warnings
    """
    warnings = []
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        if '|' in line:
            # Check for unescaped < symbols in table cells
            if '<' in line and not line.strip().startswith('<'):
                # Look for patterns like <20% that aren't HTML tags
                problematic_patterns = re.findall(r'<(?![a-zA-Z/!?\s])[^>]*', line)
                if problematic_patterns:
                    warnings.append(f'Line {i+1}: Potential HTML parsing issue with: {", ".join(problematic_patterns)}')
    
    return warnings