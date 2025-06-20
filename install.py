import subprocess
import sys

def install_dependencies():
    """Install required dependencies for the app."""
    print("Installing required Python packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Dependencies installed successfully.")
    except subprocess.CalledProcessError:
        print("Error installing dependencies. Please install them manually:")
        print("pip install -r requirements.txt")
        return False
    return True

if __name__ == "__main__":
    install_dependencies() 