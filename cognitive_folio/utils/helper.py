import json

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
                    
                    # Navigate through the nested path
                    current_data = json_data
                    for part in nested_path:
                        if isinstance(current_data, dict):
                            # Handle object access
                            current_data = current_data.get(part)
                        elif isinstance(current_data, list):
                            # Handle array access by index
                            try:
                                index = int(part)
                                if 0 <= index < len(current_data):
                                    current_data = current_data[index]
                                else:
                                    current_data = None
                            except ValueError:
                                # If part is not a number, try to access as key in array elements
                                # This handles cases like array of objects
                                current_data = None
                                break
                        else:
                            current_data = None
                            break
                    
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
			