"""
Entry point for the Flask application.
This file sets up the Python path and runs the application.
"""
import os
import sys
from dotenv import load_dotenv

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Load environment variables from .env file in project root
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

from src.api.api_server import create_app, configure_app_logging

if __name__ == '__main__':
    # Configure logging for the application
    configure_app_logging()
    
    # Create the Flask app
    app = create_app()
    
    # Run the app with debug mode
    app.run(debug=True, host="0.0.0.0")
