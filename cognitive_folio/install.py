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


def before_tests():
    """Prepare deterministic test fixtures used by upstream preload generators."""
    _ensure_fiscal_year_companies()


def _ensure_fiscal_year_companies():
    company = frappe.db.get_value("Company", {}, "name")
    if not company:
        return

    fiscal_year_names = frappe.get_all("Fiscal Year", pluck="name") or []
    for fiscal_year_name in fiscal_year_names:
        fiscal_year = frappe.get_doc("Fiscal Year", fiscal_year_name)
        if fiscal_year.get("companies"):
            continue
        fiscal_year.append("companies", {"company": company})
        fiscal_year.save(ignore_permissions=True)
