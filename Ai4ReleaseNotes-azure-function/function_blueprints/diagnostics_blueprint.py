"""
Blueprint for diagnostic function.
"""

import logging
import time
import json
import re
import asyncio

import azure.functions as func

from src.exceptions.api_exceptions import HttpUnauthorizedError, JiraFetchError
from src.jira.jira_enricher import JiraEnricher
from src.config.app_config import Config

# Create blueprint
diagnostics_bp = func.Blueprint()

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

# Process with timeout function
async def process_with_timeout(config, timeout_seconds=60):
    """Process with timeout for diagnostics."""
    logger = logging.getLogger('azure.functions')
    
    try:
        # Create enricher
        enricher = JiraEnricher(config)
        
        # Create a task with timeout
        result = await asyncio.wait_for(
            enricher.fetch_and_analyze_issues(),
            timeout=timeout_seconds
        )
        
        return result
        
    except asyncio.TimeoutError:
        logger.error(f"Operation timed out after {timeout_seconds} seconds")
        raise TimeoutError(f"Processing timed out after {timeout_seconds} seconds.")
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}", exc_info=True)
        raise

@diagnostics_bp.route(route="diagnostics/release-notes/{proj}/{fixver}/{issuetype}", methods=["PUT"])
async def release_notes_diagnostics(req: func.HttpRequest) -> func.HttpResponse:
    """
    Diagnostic endpoint to test release notes processing with step-by-step feedback.
    """
    logger = logging.getLogger('azure.functions')
    
    # Get route parameters
    proj = req.route_params.get('proj')
    fixver = req.route_params.get('fixver')
    issuetype = req.route_params.get('issuetype')
    
    logger.info(f"Diagnostic request: /diagnostics/release-notes/{proj}/{fixver}/{issuetype}")
    
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
            return func.HttpResponse(
                body=json.dumps(results),
                mimetype="application/json",
                status_code=400
            )
        add_step("input_validation", "success")
    except Exception as e:
        add_step("input_validation", "error", str(e))
        results["status"] = "error"
        return func.HttpResponse(
            body=json.dumps(results),
            mimetype="application/json",
            status_code=500
        )
        
    # Step 2: Construct JQL and get configuration
    try:
        add_step("jql_construction", "running")
        jql = f"project = {proj} AND fixversion = {fixver} AND issuetype = {issuetype}"
        add_step("jql_construction", "success", data={"jql": jql})
        
        config_object = Config()
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
        return func.HttpResponse(
            body=json.dumps(results),
            mimetype="application/json",
            status_code=500
        )
        
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
        return func.HttpResponse(
            body=json.dumps(results),
            mimetype="application/json",
            status_code=500
        )
        
    # Step 4: Process issues with timeout
    try:
        add_step("process_issues", "running")
        # For diagnostics, we'll run with reduced timeout
        await process_with_timeout(config, 60)  # 60 second timeout for diagnostics
        add_step("process_issues", "success")
    except HttpUnauthorizedError:
        add_step("process_issues", "failed", "Unauthorized access to Jira API")
        results["status"] = "failed"
        return func.HttpResponse(
            body=json.dumps(results),
            mimetype="application/json",
            status_code=401
        )
    except TimeoutError as e:
        add_step("process_issues", "timeout", str(e))
        results["status"] = "timeout"
        return func.HttpResponse(
            body=json.dumps(results),
            mimetype="application/json",
            status_code=504  # Gateway Timeout
        )
    except JiraFetchError as e:
        add_step("process_issues", "failed", f"Jira API error: {str(e)}")
        results["status"] = "failed"
        return func.HttpResponse(
            body=json.dumps(results),
            mimetype="application/json",
            status_code=502  # Bad Gateway
        )
    except Exception as e:
        add_step("process_issues", "error", str(e))
        results["status"] = "error"
        return func.HttpResponse(
            body=json.dumps(results),
            mimetype="application/json",
            status_code=500
        )
    
    # Final status
    results["status"] = "success"
    return func.HttpResponse(
        body=json.dumps(results),
        mimetype="application/json",
        status_code=200
    )
