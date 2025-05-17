import subprocess
import frappe
import sys
import os

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
