import json
import re

def _handle_wildcard_pattern(data, path_parts):
    """
    Handle wildcard patterns like *.content.title to extract values from all array items
    Returns a comma-separated string of all matching values
    """
    if not path_parts:
        return str(data) if data is not None else ""
    
    current_part = path_parts[0]
    remaining_parts = path_parts[1:]
    
    if current_part == 'ARRAY':
        # Wildcard - process all items in the current data
        if isinstance(data, list):
            results = []
            for item in data:
                if remaining_parts:
                    # Continue processing the remaining path
                    result = _navigate_nested_path(item, remaining_parts)
                    if result is not None and result != "":
                        results.append(str(result))
                else:
                    # No more path parts, add the item itself
                    if item is not None:
                        results.append(str(item))
            return ", ".join(results)
        elif isinstance(data, dict):
            # If it's a dict, process all values
            results = []
            for value in data.values():
                if remaining_parts:
                    result = _navigate_nested_path(value, remaining_parts)
                    if result is not None and result != "":
                        results.append(str(result))
                else:
                    if value is not None:
                        results.append(str(value))
            return ", ".join(results)
        else:
            return ""
    else:
        # Regular path part
        return _navigate_nested_path(data, path_parts)

def _navigate_nested_path(data, path_parts):
    """
    Navigate through a nested path without wildcards
    """
    current_data = data
    for part in path_parts:
        if isinstance(current_data, dict):
            current_data = current_data.get(part)
        elif isinstance(current_data, list):
            try:
                index = int(part)
                if 0 <= index < len(current_data):
                    current_data = current_data[index]
                else:
                    current_data = None
            except ValueError:
                current_data = None
                break
        else:
            current_data = None
            break
    
    return current_data

def replace_variables(match, doc):
    variable_name = match.group(1)
    try:
        # Handle nested JSON variables like {{field_name.key}} or {{field_name.0.key}} for arrays
        if '.' in variable_name:
            parts = variable_name.split('.')
            field_name = parts[0]
            nested_path = parts[1:]  # Remaining path parts
            
            field_value = getattr(doc, field_name, None)
            if field_value:
                try:
                    # Try to parse as JSON
                    json_data = json.loads(field_value)
                    
                    # Check if we have a wildcard pattern
                    if 'ARRAY' in nested_path:
                        return _handle_wildcard_pattern(json_data, nested_path)
                    
                    # Navigate through the nested path using the helper function
                    current_data = _navigate_nested_path(json_data, nested_path)
                    
                    if current_data is not None:
                        return str(current_data)
                    else:
                        return ""
                except json.JSONDecodeError:
                    # If not valid JSON, return empty string
                    return ""
            else:
                return ""
        else:
            # Handle regular doc field variables
            field_value = getattr(doc, variable_name, None)
            if field_value is not None:
                return str(field_value)
            else:
                return ""
    except (AttributeError, IndexError, ValueError):
        return match.group(0)

def clear_string(content_string: str) -> dict:
    """
    Convert a string to a JSON object.
    If the string is not valid JSON, return an empty dictionary.
    """
    # Parse the JSON from the content string, removing any Markdown formatting
    if content_string.startswith('```') and '```' in content_string[3:]:
        # Extract content between the first and last backtick markers
        content_string = content_string.split('```', 2)[1]
        # Remove the language identifier if present (e.g., 'json\n')
        if '\n' in content_string:
            content_string = content_string.split('\n', 1)[1]
        # Remove trailing backticks if any remain
        if '```' in content_string:
            content_string = content_string.split('```')[0]

    # Replace problematic control characters and normalize whitespace
    content_string = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content_string)
    
    # Fix JSON formatting issues - improved approach for handling newlines in strings
    # First, properly escape newlines that appear within JSON string values
    lines = content_string.split('\n')
    fixed_content = []
    current_line = ""
    in_string = False
    escape_next = False
    
    for line in lines:
        i = 0
        while i < len(line):
            char = line[i]
            
            if escape_next:
                current_line += char
                escape_next = False
            elif char == '\\':
                current_line += char
                escape_next = True
            elif char == '"' and not escape_next:
                current_line += char
                in_string = not in_string
            else:
                current_line += char
            
            i += 1
        
        # If we're at the end of a line and inside a string, escape the newline
        if in_string and line != lines[-1]:  # Not the last line
            current_line += '\\n'
        else:
            # We're not in a string or this is the last line
            fixed_content.append(current_line)
            current_line = ""
    
    # Add any remaining content
    if current_line:
        fixed_content.append(current_line)
    
    content_string = '\n'.join(fixed_content)
    
    # Additional cleanup for HTML entities and special characters
    content_string = content_string.replace('&nbsp;', ' ')
    content_string = content_string.replace('\t', '    ')
    
    return content_string
