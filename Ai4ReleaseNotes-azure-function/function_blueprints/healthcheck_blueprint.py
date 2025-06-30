"""
Blueprint for health check function.
"""

import logging
import time
import json

import azure.functions as func

from src.jira.jira_client import JiraAPIWrapper
from src.config.app_config import Config

# Create blueprint
healthcheck_bp = func.Blueprint()

@healthcheck_bp.route(route="health", methods=["GET"])
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint for monitoring."""
    logger = logging.getLogger('azure.functions')
    
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
        logger.info("Health check: Testing JIRA API connection")
        
        # Extract config
        config_object = Config()
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
            logger.warning("Health check: Empty response from JIRA API")
            
    except Exception as e:
        health["dependencies"]["jira_api"] = "unhealthy"
        health["status"] = "degraded"
        health["diagnostics"]["jira_api"]["error"] = str(e)
        health["diagnostics"]["jira_api"]["error_type"] = type(e).__name__
        logger.error(f"Health check for Jira failed: {str(e)}", exc_info=True)
    
    health["diagnostics"]["jira_api"]["response_time"] = time.time()
    
    # Return health status
    return func.HttpResponse(
        body=json.dumps(health),
        mimetype="application/json",
        status_code=200
    )
