import subprocess
import frappe

def after_install():
    """Run after app installation"""
    
    # Install dependencies
    install_dependencies()
    
    # Seed ph_agent integration data
    seed_ph_agent_integration()

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


def seed_ph_agent_integration():
    """Seed Tool Registry entry and Personas for ph_agent integration."""
    
    # ------------------------------------------------------------------
    # 1. Seed cognitive_folio_query tool in Tool Registry
    # ------------------------------------------------------------------
    _seed_tool_registry()
    
    # ------------------------------------------------------------------
    # 2. Seed Financial Advisor persona
    # ------------------------------------------------------------------
    _seed_financial_advisor_persona()
    
    # ------------------------------------------------------------------
    # 3. Seed Portfolio Analyst persona
    # ------------------------------------------------------------------
    _seed_portfolio_analyst_persona()


def _seed_tool_registry():
    """Create the cognitive_folio_query tool in ph_agent's Tool Registry."""
    if not frappe.db.exists("DocType", "Tool Registry"):
        print("⚠ ph_agent not installed yet — skipping Tool Registry seeding", "Cognitive Folio Setup")
        return
    
    if frappe.db.exists("Tool Registry", "cognitive_folio_query"):
        print("✓ Tool 'cognitive_folio_query' already exists", "Cognitive Folio Setup")
        return
    
    try:
        doc = frappe.get_doc({
            "doctype": "Tool Registry",
            "tool_name": "cognitive_folio_query",
            "is_enabled": 1,
            "script_type": "Existing Function",
            "python_function": "cognitive_folio.ph_agent_bridge.cf_tools.cognitive_folio_query",
            "tool_group": "Financial",
            "description": (
                "Query Cognitive Folio financial data. Supports actions: "
                "get, list, search, create, update, delete. "
                "Accessible doctypes: CF Portfolio, CF Security, "
                "CF Portfolio Holding, CF Transaction, CF Dividend, "
                "CF AI Model, CF Asset Allocation, CF Settings."
            ),
            "requires_approval": 0,
        })
        doc.insert(ignore_if_duplicate=True)
        print("✓ Tool 'cognitive_folio_query' seeded successfully", "Cognitive Folio Setup")
    except Exception as e:
        print(f"✗ Failed to seed tool 'cognitive_folio_query': {e}", "Cognitive Folio Setup Error")


def _seed_financial_advisor_persona():
    """Create the Financial Advisor persona for portfolio analysis."""
    if not frappe.db.exists("DocType", "Persona"):
        print("⚠ ph_agent not installed yet — skipping Persona seeding", "Cognitive Folio Setup")
        return
    
    persona_name = "Financial Advisor"
    if frappe.db.exists("Persona", {"persona_name": persona_name}):
        print(f"✓ Persona '{persona_name}' already exists", "Cognitive Folio Setup")
        return
    
    try:
        doc = frappe.get_doc({
            "doctype": "Persona",
            "persona_name": persona_name,
            "icon": "💰",
            "color": "#4f72b8",
            "system_prompt": (
                "You are a Financial Advisor specialized in portfolio analysis "
                "and investment management. You have access to Cognitive Folio's "
                "financial data through the cognitive_folio_query tool.\n\n"
                "Your expertise includes:\n"
                "- Portfolio performance analysis and optimization\n"
                "- Security valuation and fundamental analysis\n"
                "- Asset allocation and diversification recommendations\n"
                "- Risk assessment and management\n"
                "- Dividend income analysis\n"
                "- Transaction history review\n\n"
                "Always provide data-driven insights. When discussing portfolio "
                "holdings, reference specific securities, allocation percentages, "
                "and performance metrics. Use the cognitive_folio_query tool to "
                "fetch real data rather than making assumptions."
            ),
            "is_default": 0,
            "enable_streaming": 1,
            "enable_suggestions": 1,
            "disable_tools": 0,
            "enable_tool_routing": 1,
        })
        doc.insert(ignore_if_duplicate=True)
        
        # Add tool groups
        _add_tool_group_to_persona(doc.name, "Financial")
        _add_tool_group_to_persona(doc.name, "General")
        _add_tool_group_to_persona(doc.name, "Web")
        
        print(f"✓ Persona '{persona_name}' seeded successfully", "Cognitive Folio Setup")
    except Exception as e:
        print(f"✗ Failed to seed persona '{persona_name}': {e}", "Cognitive Folio Setup Error")


def _seed_portfolio_analyst_persona():
    """Create the Portfolio Analyst persona focused on holdings/allocations."""
    if not frappe.db.exists("DocType", "Persona"):
        return
    
    persona_name = "Portfolio Analyst"
    if frappe.db.exists("Persona", {"persona_name": persona_name}):
        print(f"✓ Persona '{persona_name}' already exists", "Cognitive Folio Setup")
        return
    
    try:
        doc = frappe.get_doc({
            "doctype": "Persona",
            "persona_name": persona_name,
            "icon": "📊",
            "color": "#27ae60",
            "system_prompt": (
                "You are a Portfolio Analyst specialized in portfolio holdings "
                "analysis, asset allocation, and performance attribution. "
                "You have access to Cognitive Folio's financial data through "
                "the cognitive_folio_query tool.\n\n"
                "Your expertise includes:\n"
                "- Holdings analysis and position sizing\n"
                "- Asset allocation review and rebalancing suggestions\n"
                "- Sector and geographic exposure analysis\n"
                "- Performance attribution (price vs. dividend returns)\n"
                "- Concentration risk assessment\n"
                "- Cost basis and tax implications\n\n"
                "Focus on quantitative analysis. Present data in clear tables "
                "and highlight key metrics. Use the cognitive_folio_query tool "
                "to fetch real portfolio and holding data."
            ),
            "is_default": 0,
            "enable_streaming": 1,
            "enable_suggestions": 1,
            "disable_tools": 0,
            "enable_tool_routing": 1,
        })
        doc.insert(ignore_if_duplicate=True)
        
        # Add tool groups
        _add_tool_group_to_persona(doc.name, "Financial")
        _add_tool_group_to_persona(doc.name, "General")
        
        print(f"✓ Persona '{persona_name}' seeded successfully", "Cognitive Folio Setup")
    except Exception as e:
        print(f"✗ Failed to seed persona '{persona_name}': {e}", "Cognitive Folio Setup Error")


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
