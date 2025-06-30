"""
Main entry point for the Azure Function app using the v2 programming model.
This file registers all function blueprints from different modules.
"""

import os
import sys
import logging
from dotenv import load_dotenv

import azure.functions as func

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Load environment variables from .env file in project root if available
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

# Import centralized security configuration
from src.utils.security_utils import disable_ssl_verification

# Import blueprints
from function_blueprints.release_notes_blueprint import release_notes_bp
from function_blueprints.healthcheck_blueprint import healthcheck_bp
from function_blueprints.test_blueprint import test_bp
from function_blueprints.diagnostics_blueprint import diagnostics_bp

# Configure logging
def configure_app_logging():
    """Configure application logging with more detailed information."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Determine log level from environment or config
    from src.config.app_config import Config
    is_production = Config().is_production()
    log_level = logging.INFO if is_production else logging.DEBUG
    
    # Configure the root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(),  # Ensure logs go to stderr/stdout
            logging.FileHandler("app.log")  # Also save logs to a file
        ]
    )
    
    # Set levels for other modules
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("semantic_kernel").setLevel(logging.INFO)
    logging.getLogger("azure.functions").setLevel(logging.INFO)
    
    # Configure jira logger 
    jira_logger = logging.getLogger("jira")
    jira_logger.setLevel(log_level)
    
    # Log the configured level
    logging.info(f"Logging configured. Level: {'INFO' if is_production else 'DEBUG'}")
    logging.info("Loggers configured for: azure.functions, urllib3, semantic_kernel, jira")

# Configure logging when module is loaded
configure_app_logging()

# Configure SSL
disable_ssl_verification()

# Create the function app
app = func.FunctionApp()

# Register blueprints
app.register_blueprint(release_notes_bp)
app.register_blueprint(healthcheck_bp)  
app.register_blueprint(test_bp)
app.register_blueprint(diagnostics_bp)

logging.info("Azure Function app initialized with all blueprints registered")


@app.route(route="AigeneratedreleaseNotes", auth_level=func.AuthLevel.FUNCTION)
def AigeneratedreleaseNotes(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )