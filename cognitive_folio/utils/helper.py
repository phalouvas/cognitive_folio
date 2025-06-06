import json

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
