import subprocess
import frappe

def after_install():
    """Run after app installation"""
    
    # Install dependencies
    install_dependencies()

def install_dependencies():
    # List of required Python dependencies with specific versions
    dependencies = [
        "yfinance",
        "openai"
    ]
    
    print("Starting Cognitive Folio dependency installation", "Cognitive Folio Setup")
    
    # Install each dependency
    for package in dependencies:
        try:
            # Show installation progress
            print(f"Installing {package}...", "Cognitive Folio Setup")
            
            # Install using bench pip 
            result = subprocess.run(
                ["bench", "pip", "install", "--quiet", package],
                check=False,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✓ {package} installed successfully", "Cognitive Folio Setup")
            else:
                print(
                    f"✗ Failed to install {package}: {result.stderr}",
                    "Cognitive Folio Setup Error"
                )
                
        except Exception as e:
            print(
                f"✗ Error installing {package}: {str(e)}", 
                "Cognitive Folio Setup Error"
            )
    
    print("Cognitive Folio dependency installation completed", "Cognitive Folio Setup")


def _add_tool_group_to_persona(persona: str, tool_group: str):
    """Add a tool group child record to a Persona."""
    try:
        child = frappe.get_doc({
            "doctype": "Persona Tool Group",
            "parent": persona,
            "parentfield": "tool_groups",
            "parenttype": "Persona",
            "tool_group": tool_group,
        })
        child.insert(ignore_if_duplicate=True)
    except Exception:
        pass  # Child record may already exist
