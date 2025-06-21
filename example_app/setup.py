import subprocess
import sys
import frappe

def before_install():
    """Run before app installation"""
    install_dependencies()

def after_install():
    """Run after app installation"""
    frappe.db.commit()
    frappe.msgprint("1D Cutting Optimizer installed successfully! Required Python packages have been installed.")

def install_dependencies():
    """Install required Python packages"""
    packages = ["reportlab>=4.0.0", "ortools>=9.0.0"]
    
    try:
        for package in packages:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        
        frappe.log_error("Successfully installed dependencies: " + ", ".join(packages), "Optimizer Setup")
        return True
    except Exception as e:
        frappe.log_error(f"Error installing dependencies: {str(e)}", "Optimizer Setup Error")
        return False 