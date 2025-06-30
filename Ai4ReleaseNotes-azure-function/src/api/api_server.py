# api_server.py
"""
Flask application for generating release notes from JIRA tickets.
This module provides REST API endpoints for processing different types of JIRA issues.
"""

# Standard library imports
import os
import re
import json
import logging
import asyncio
import time
from typing import Any, List, Tuple

# Third-party imports
from flask import Flask, jsonify
from dotenv import load_dotenv

# Load environment variables at module level
load_dotenv()

# Import centralized security configuration
from src.utils.security_utils import disable_ssl_verification

# Local imports
from src.jira.jira_client import JiraAPIWrapper

from src.utils.file_utils import (
    cleanup_issue,
    normalize_issue_data,
    create_file_path,
    save_issues_to_file,
    cleanup_child,
    format_issue,
)

from src.config.app_config import Config
from src.jira.jira_enricher import JiraEnricher

# Import all exceptions
from src.exceptions.api_exceptions import HttpUnauthorizedError, JiraFetchError

# Configure logging function
def configure_app_logging():
    """Configure application logging with more detailed information."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Determine log level from environment or config
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
    
    # Create Flask app logger
    flask_logger = logging.getLogger('flask.app')
    flask_logger.setLevel(log_level)
    
    # Set levels for other modules
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("semantic_kernel").setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    
    # Configure jira logger to use same handlers as flask.app
    jira_logger = logging.getLogger("jira")
    jira_logger.setLevel(log_level)
    jira_logger.handlers = flask_logger.handlers  # Share the same handlers
    
    # Log the configured level
    logging.info(f"Logging configured. Level: {'INFO' if is_production else 'DEBUG'}")
    logging.info("Loggers configured for: flask.app, urllib3, semantic_kernel, jira")
        
# Simple in-memory cache
cache = {}
CACHE_TIMEOUT = 300  # 5 minutes - cache responses to reduce load on Jira and OpenAI APIs

# Process with timeout function
async def process_with_timeout(config, timeout_seconds=300):
    """Process with timeout to prevent hanging processes."""
    logger = logging.getLogger('flask.app')
    start_time = time.time()
    
    try:
        # Log the start of processing
        logger.info(f"Starting JQL processing: {config.get('jql', 'None')}")
        logger.debug(f"Max results configured: {config.get('max_results', 'Not specified')}")
        logger.debug(f"Timeout set to: {timeout_seconds} seconds")
        
        # Force reload environment variables to ensure we have the latest values
        load_dotenv(override=True)            # Log environment variables for debugging
        logger.info(f"Environment check - CONFLUENCE_PARENT_ID: {os.environ.get('CONFLUENCE_PARENT_ID')}")
        logger.debug("Checking environment variables:")
        logger.debug(f"AZURE_OPENAI_CHAT_COMPLETIONS_API_VERSION = {os.environ.get('AZURE_OPENAI_CHAT_COMPLETIONS_API_VERSION')}")
        logger.debug(f"AZURE_OPENAI_GPT_DEPLOYMENT = {os.environ.get('AZURE_OPENAI_GPT_DEPLOYMENT')}")
        
        # Log key configuration settings at debug level
        for key in ['jira_url', 'azure_openai_endpoint', 'create_local_files', 'create_confluence_pages']:
            if key in config:
                logger.debug(f"Config[{key}] = {config[key]}")
        
        # Check and log OpenAI configuration
        logger.debug("Checking OpenAI configuration:")
        logger.debug(f"Azure OpenAI API version: {config.get('azure_openai_chat_completions_api_version')}")
        logger.debug(f"Azure OpenAI deployment: {config.get('azure_openai_gpt_deployment')}")
        logger.debug(f"Azure OpenAI endpoint: {config.get('azure_openai_endpoint')}")
        
        # Ensure correct API version for o4-mini model
        if config.get('azure_openai_gpt_deployment') == 'o4-mini' and config.get('azure_openai_chat_completions_api_version') != '2024-12-01-preview':
            logger.warning("API version mismatch! Fixing API version for o4-mini model")
            config['azure_openai_chat_completions_api_version'] = '2024-12-01-preview'
        
        logger.info("Creating JiraEnricher instance")
        enricher = JiraEnricher(config)
        logger.info("JiraEnricher instance created successfully")
        
        # Create a task with timeout
        logger.info("Starting fetch_and_analyze_issues with timeout")
        logger.debug("About to call enricher.fetch_and_analyze_issues()")
        result = await asyncio.wait_for(
            enricher.fetch_and_analyze_issues(),
            timeout=timeout_seconds
        )
        logger.info("fetch_and_analyze_issues completed successfully")
        
        # Log the completion of processing
        elapsed_time = time.time() - start_time
        logger.info(f"Processing completed successfully in {elapsed_time:.2f} seconds for JQL: {config.get('jql', 'None')}")
        return result
        
    except asyncio.TimeoutError:
        elapsed_time = time.time() - start_time
        logger.error(f"Operation timed out after {timeout_seconds} seconds (elapsed: {elapsed_time:.2f}s)")
        raise TimeoutError(f"Processing timed out after {timeout_seconds} seconds. Please try with fewer issues.")
        
    except HttpUnauthorizedError as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Authentication error during processing (elapsed: {elapsed_time:.2f}s): {str(e)}", exc_info=True)
        raise
        
    except JiraFetchError as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Jira fetch error during processing (elapsed: {elapsed_time:.2f}s): {str(e)}", exc_info=True)
        raise
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error during processing (elapsed: {elapsed_time:.2f}s): {str(e)}", exc_info=True)
        raise

# Input validation function
def validate_input(proj: str, fixver: str, issuetype: str) -> tuple:
    """Validate input parameters."""
    errors = []
    if not re.match(r'^[A-Za-z0-9_]+$', proj):
        errors.append("Invalid project key format")
    
    if not fixver:
        errors.append("Fix version cannot be empty")
        
    valid_issue_types = ['Bug', 'Issue', 'Epic', 'Comp']
    if issuetype not in valid_issue_types:
        errors.append(f"Issue type must be one of: {', '.join(valid_issue_types)}")
    
    if errors:
        return False, errors
    return True, []


# Create a function that creates and configures the Flask app
def create_app(config_object=None):
    """
    Application factory function that creates and configures the Flask app.
    
    Args:
        config_object: Configuration object to use. Defaults to None.
        
    Returns:
        Flask application instance.
    """
    # Initialize Flask app
    app = Flask(__name__)
    
    # Initialize configuration
    if config_object is None:
        config_object = Config()
    
    # Configure SSL
    disable_ssl_verification()
    
    # Configure logging
    configure_app_logging()
    
    # Import and register routes from extension_routes
    try:
        # Try multiple import paths for extension_routes
        try:
            # First try as a direct module
            from src.api.extension_routes import app as api_routes_app
            logging.info("Imported extension_routes from src.api.extension_routes")
        except ImportError:
            # Second try with relative import
            from extension_routes import app as api_routes_app
            logging.info("Imported extension_routes from extension_routes")
        # Register all routes from api_routes
        for rule in api_routes_app.url_map.iter_rules():
            endpoint = rule.endpoint
            # Skip built-in endpoints like 'static' to avoid conflicts
            if endpoint == 'static':
                logging.info(f"Skipping built-in endpoint: {endpoint}")
                continue
                
            view_func = api_routes_app.view_functions[endpoint]
            # Use a unique prefix for endpoints from api_routes to avoid conflicts
            new_endpoint = f"api_routes_{endpoint}"
            app.add_url_rule(rule.rule, endpoint=new_endpoint, view_func=view_func, methods=rule.methods)
            logging.info(f"Registered route: {rule.rule} with endpoint: {new_endpoint}")
            
        logging.info("Successfully registered routes from extension_routes module")
    except ImportError:
        logging.warning("Could not import extension_routes module. Using local route definitions.")
    
    ##### Main Route ####
    @app.route('/release-notes/<proj>/<fixver>/<issuetype>/<int:max_results>', methods=['PUT'])
    def release_notes_with_limit_handler(proj: str, fixver: str, issuetype: str, max_results: int) -> Any:
        """
        HTTP handler to trigger fetching, analyzing, and publishing release notes
        with a specific limit on the number of issues to process.
        """
        logger = logging.getLogger('flask.app')
        logger.info(f"Processing request: /release-notes/{proj}/{fixver}/{issuetype}/{max_results}")
        logger.debug(f"Request parameters - proj: {proj}, fixver: {fixver}, issuetype: {issuetype}, max_results: {max_results}")
        
        # Validate input parameters
        valid, errors = validate_input(proj, fixver, issuetype)
        if not valid:
            logger.error(f"Input validation failed: {errors}")
            return jsonify({"status": "error", "message": errors}), 400
        
        # Validate max_results
        if max_results <= 0 or max_results > 1000:
            logger.error(f"Invalid max_results value: {max_results}")
            return jsonify({"status": "error", "message": "max_results must be between 1 and 1000"}), 400
            
        jql = f"project = {proj} AND fixversion = {fixver} AND issuetype = {issuetype}"
        logger.debug(f"Constructed JQL: {jql}")
        
        # Get configuration with custom max_results
        config = config_object.get_enricher_config_with_options(jql, issuetype, max_results=max_results)
        
        # Log the configuration being used
        logger.debug(f"Processing {issuetype}s for project {proj} and fixversion {fixver} with max_results: {max_results}")
        logger.debug(f"Using max_results value: {config.get('max_results', 'Not specified')}")
        
        try:
            # Use timeout function to prevent hanging processes
            asyncio.run(process_with_timeout(config))
            logger.info(f"Successfully processed request for {proj}/{fixver}/{issuetype}")
            return jsonify({"status": "success"}), 200
            
        except HttpUnauthorizedError:
            logger.error("Unauthorized access to Jira API")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        except TimeoutError as e:
            logger.error(f"Request timed out: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 504  # Gateway Timeout
        except JiraFetchError as e:
            logger.error(f"Jira fetch error: {str(e)}")
            return jsonify({"status": "error", "message": f"Jira API error: {str(e)}"}), 502  # Bad Gateway
        except Exception as e:
            logger.error(f"Error processing release notes: {str(e)}", exc_info=True)  # Include stack trace
            return jsonify({"status": "error", "message": "Internal Server Error"}), 500
    
    # Define a test route that doesn't depend on any other services
    @app.route('/test', methods=['GET'])
    def test_route():
        """Simple test endpoint to verify Flask is working."""
        logging.info("Test route called successfully")
        return jsonify({
            "status": "ok",
            "message": "Flask app is running correctly",
            "timestamp": time.time(),
            "app_version": "1.0.0"
        })
    
    # Health check endpoint for monitoring
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint for monitoring."""
        # Check if we can connect to dependencies
        health = {
            "status": "healthy",
            "timestamp": time.time(),
            "dependencies": {
                "jira_api": "unknown",
                "azure_openai": "unknown"
            },
            "diagnostics": {
                "jira_api": {},
                "azure_openai": {}
            }
        }
        
        # Check Jira connectivity
        try:
            logging.info("Health check: Testing JIRA API connection")
            
            # Extract config
            enricher_config = config_object.get_enricher_config("project = TEST", "Bug")
            
            # Add diagnostic information
            health["diagnostics"]["jira_api"] = {
                "url": enricher_config.get("jira_url", "Not configured"),
                "username": enricher_config.get("jira_username", "Not configured"),
                "ssl_verify": enricher_config.get("ssl_verify", True),
                "request_time": time.time()
            }
            
            # Create wrapper and test connection
            jira = JiraAPIWrapper(
                jira_username=enricher_config.get('jira_username'),
                jira_api_token=enricher_config.get('jira_api_key'),
                jira_instance_url=enricher_config.get('jira_url')
            )
            
            connection_result = jira.test_connection()
            health["dependencies"]["jira_api"] = "healthy" if connection_result else "unhealthy"
            
            if not connection_result:
                health["status"] = "degraded"
                health["diagnostics"]["jira_api"]["error"] = "Empty response from JIRA API"
                logging.warning("Health check: Empty response from JIRA API")
                
        except Exception as e:
            health["dependencies"]["jira_api"] = "unhealthy"
            health["status"] = "degraded"
            health["diagnostics"]["jira_api"]["error"] = str(e)
            health["diagnostics"]["jira_api"]["error_type"] = type(e).__name__
            logging.error(f"Health check for Jira failed: {str(e)}", exc_info=True)
        
        health["diagnostics"]["jira_api"]["response_time"] = time.time()
        
        # Return health status
        return jsonify(health)
    
    # API routes - these serve as fallbacks if extension_routes.py is not loaded
    @app.route('/release-notes/<proj>/<fixver>/<issuetype>', methods=['PUT'])
    def release_notes_handler(proj: str, fixver: str, issuetype: str) -> Any:
        """
        HTTP handler to trigger fetching, analyzing, and publishing release notes.
        Uses default max_results from configuration.
        """
        logger = logging.getLogger('flask.app')
        logger.info(f"Received request: /release-notes/{proj}/{fixver}/{issuetype}")
        
        # Validate input parameters
        valid, errors = validate_input(proj, fixver, issuetype)
        if not valid:
            logger.error(f"Input validation failed: {errors}")
            return jsonify({"status": "error", "message": errors}), 400
        
        jql = f"project = {proj} AND fixversion = {fixver} AND issuetype = {issuetype}"
        logger.debug(f"Constructed JQL: {jql}")
        
        # Get configuration from Config class
        config = config_object.get_enricher_config(jql, issuetype)
        
        # Log the configuration being used
        logger.debug(f"Processing {issuetype}s for project {proj} and fixversion {fixver}")
        logger.debug(f"Using max_results value: {config.get('max_results', 'Not specified')}")
        
        try:
            # Use timeout function to prevent hanging processes
            asyncio.run(process_with_timeout(config))
            logger.info(f"Successfully processed request for {proj}/{fixver}/{issuetype}")
            return jsonify({"status": "success"}), 200
            
        except HttpUnauthorizedError:
            logger.error("Unauthorized access to Jira API")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        except TimeoutError as e:
            logger.error(f"Request timed out: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 504  # Gateway Timeout
        except JiraFetchError as e:
            logger.error(f"Jira fetch error: {str(e)}")
            return jsonify({"status": "error", "message": f"Jira API error: {str(e)}"}), 502  # Bad Gateway
        except Exception as e:
            logger.error(f"Error processing release notes: {str(e)}", exc_info=True)  # Include stack trace
            return jsonify({"status": "error", "message": "Internal Server Error"}), 500

    # Diagnostic route for release notes processing
    @app.route('/diagnostics/release-notes/<proj>/<fixver>/<issuetype>', methods=['PUT'])
    def release_notes_diagnostics(proj: str, fixver: str, issuetype: str) -> Any:
        """
        Diagnostic endpoint to test release notes processing with step-by-step feedback.
        """
        logging.info(f"Diagnostic request: /diagnostics/release-notes/{proj}/{fixver}/{issuetype}")
        
        # Results dictionary to track each step
        results = {
            "timestamp": time.time(),
            "steps": [],
            "status": "running",
            "project": proj,
            "fix_version": fixver,
            "issue_type": issuetype
        }
        
        # Add a step to the results
        def add_step(name, status, message=None, data=None):
            step = {
                "name": name,
                "status": status,
                "timestamp": time.time()
            }
            if message:
                step["message"] = message
            if data:
                step["data"] = data
            results["steps"].append(step)
            return step
            
        # Step 1: Validate input parameters
        try:
            add_step("input_validation", "running")
            valid, errors = validate_input(proj, fixver, issuetype)
            if not valid:
                add_step("input_validation", "failed", f"Invalid parameters: {errors}")
                results["status"] = "failed"
                return jsonify(results), 400
            add_step("input_validation", "success")
        except Exception as e:
            add_step("input_validation", "error", str(e))
            results["status"] = "error"
            return jsonify(results), 500
            
        # Step 2: Construct JQL and get configuration
        try:
            add_step("jql_construction", "running")
            jql = f"project = {proj} AND fixversion = {fixver} AND issuetype = {issuetype}"
            add_step("jql_construction", "success", data={"jql": jql})
            
            config = config_object.get_enricher_config(jql, issuetype)
            # Remove sensitive data from config for logging
            safe_config = {k: v for k, v in config.items() if not (
                k in ["azure_openai_key", "jira_api_key"] or 
                "key" in k.lower() or 
                "password" in k.lower() or 
                "token" in k.lower()
            )}
            add_step("config_loaded", "success", data={"config": safe_config})
        except Exception as e:
            add_step("config_loading", "error", str(e))
            results["status"] = "error"
            return jsonify(results), 500
            
        # Step 3: Create JiraEnricher
        try:
            add_step("jira_enricher_creation", "running")
            # Ensure correct API version for o4-mini model
            if config.get('azure_openai_gpt_deployment') == 'o4-mini' and config.get('azure_openai_chat_completions_api_version') != '2024-12-01-preview':
                add_step("api_version_check", "warning", "API version mismatch detected, fixing...")
                config['azure_openai_chat_completions_api_version'] = '2024-12-01-preview'
            
            enricher = JiraEnricher(config)
            add_step("jira_enricher_creation", "success")
        except Exception as e:
            add_step("jira_enricher_creation", "error", str(e))
            results["status"] = "error"
            return jsonify(results), 500
            
        # Step 4: Process issues with timeout
        try:
            add_step("process_issues", "running")
            # Start a background task for processing
            # For diagnostics, we'll run synchronously with reduced timeout
            asyncio.run(process_with_timeout(config, 60))  # 60 second timeout for diagnostics
            add_step("process_issues", "success")
        except HttpUnauthorizedError:
            add_step("process_issues", "failed", "Unauthorized access to Jira API")
            results["status"] = "failed"
            return jsonify(results), 401
        except TimeoutError as e:
            add_step("process_issues", "timeout", str(e))
            results["status"] = "timeout"
            return jsonify(results), 504  # Gateway Timeout
        except JiraFetchError as e:
            add_step("process_issues", "failed", f"Jira API error: {str(e)}")
            results["status"] = "failed"
            return jsonify(results), 502  # Bad Gateway
        except Exception as e:
            add_step("process_issues", "error", str(e))
            results["status"] = "error"
            return jsonify(results), 500
        
        # Final status
        results["status"] = "success"
        return jsonify(results), 200
    
    return app

# Initialize and run app if this is the main module
if __name__ == '__main__':
    print("DEBUG: Starting application setup")
    # Configure logging immediately for debugging
    configure_app_logging()
    logging.error("Starting application...")
    print("DEBUG: Logging configured")
    
    app_config = Config()
    logging.info("Config initialized")
    
    app = create_app(app_config)
    debug_mode = not app_config.is_production()
    
    # Log all registered routes for debugging
    logging.info("Registered routes:")
    for rule in app.url_map.iter_rules():
        logging.info(f"Route: {rule.rule} - Endpoint: {rule.endpoint} - Methods: {rule.methods}")
    
    # Double check if our specific routes exist
    test_route_exists = any(rule.rule == '/test' for rule in app.url_map.iter_rules())
    logging.info(f"Test route exists: {test_route_exists}")
    
    # Run the app with host 0.0.0.0 to make it accessible externally
    logging.info(f"Starting Flask app with debug={debug_mode}")
    app.run(debug=debug_mode, host="0.0.0.0")

