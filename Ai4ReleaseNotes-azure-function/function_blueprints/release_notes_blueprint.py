"""
Blueprint for release notes functions.
"""

import logging
import asyncio
import json
import re
from typing import Any, Dict

import azure.functions as func

from src.exceptions.api_exceptions import HttpUnauthorizedError, JiraFetchError
from src.jira.jira_enricher import JiraEnricher
from src.config.app_config import Config

# Create blueprint
release_notes_bp = func.Blueprint()

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
async def process_with_timeout(config, timeout_seconds=300):
    """Process with timeout to prevent hanging processes."""
    logger = logging.getLogger('azure.functions')
    logger.info(f"Starting JQL processing: {config.get('jql', 'None')}")
    
    try:
        # Log key configuration settings
        for key in ['jira_url', 'azure_openai_endpoint', 'create_local_files', 'create_confluence_pages']:
            if key in config:
                logger.debug(f"Config[{key}] = {config[key]}")
        
        # Ensure correct API version for o4-mini model
        if config.get('azure_openai_gpt_deployment') == 'o4-mini' and config.get('azure_openai_chat_completions_api_version') != '2024-12-01-preview':
            logger.warning("API version mismatch! Fixing API version for o4-mini model")
            config['azure_openai_chat_completions_api_version'] = '2024-12-01-preview'
        
        logger.info("Creating JiraEnricher instance")
        enricher = JiraEnricher(config)
        logger.info("JiraEnricher instance created successfully")
        
        # Create a task with timeout
        logger.info("Starting fetch_and_analyze_issues with timeout")
        result = await asyncio.wait_for(
            enricher.fetch_and_analyze_issues(),
            timeout=timeout_seconds
        )
        logger.info("fetch_and_analyze_issues completed successfully")
        
        return result
        
    except asyncio.TimeoutError:
        logger.error(f"Operation timed out after {timeout_seconds} seconds")
        raise TimeoutError(f"Processing timed out after {timeout_seconds} seconds. Please try with fewer issues.")
        
    except HttpUnauthorizedError as e:
        logger.error(f"Authentication error during processing: {str(e)}", exc_info=True)
        raise
        
    except JiraFetchError as e:
        logger.error(f"Jira fetch error during processing: {str(e)}", exc_info=True)
        raise
        
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}", exc_info=True)
        raise

# Define route with route parameters
@release_notes_bp.route(route="release-notes/{proj}/{fixver}/{issuetype}", methods=["PUT"])
@release_notes_bp.function_name(name="release_notes_handler")
async def release_notes_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP handler to trigger fetching, analyzing, and publishing release notes.
    Uses default max_results from configuration.
    """
    logger = logging.getLogger('azure.functions')
    
    # Get route parameters
    proj = req.route_params.get('proj')
    fixver = req.route_params.get('fixver')
    issuetype = req.route_params.get('issuetype')
    
    logger.info(f"Received request: /release-notes/{proj}/{fixver}/{issuetype}")
    
    # Validate input parameters
    valid, errors = validate_input(proj, fixver, issuetype)
    if not valid:
        logger.error(f"Input validation failed: {errors}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": errors}),
            mimetype="application/json",
            status_code=400
        )
    
    jql = f"project = {proj} AND fixversion = {fixver} AND issuetype = {issuetype}"
    logger.debug(f"Constructed JQL: {jql}")
    
    # Get configuration from Config class
    config_object = Config()
    config = config_object.get_enricher_config(jql, issuetype)
    
    try:
        # Use timeout function to prevent hanging processes
        result = await process_with_timeout(config)
        logger.info(f"Successfully processed request for {proj}/{fixver}/{issuetype}")
        
        # Build response with detailed information
        response = {
            "status": "success",
            "project": proj,
            "fixVersion": fixver,
            "issueType": issuetype,
            "processingTime": result.get('processing_time', 0) if isinstance(result, dict) else 0
        }
        
        # Include relevant success information
        if isinstance(result, dict) and result.get('details'):
            response["details"] = result.get('details')
        else:
            response["details"] = f"Successfully processed request for {proj}/{fixver}/{issuetype}"
            
        return func.HttpResponse(
            body=json.dumps(response),
            mimetype="application/json",
            status_code=200
        )
        
    except HttpUnauthorizedError:
        logger.error("Unauthorized access to Jira API")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": "Unauthorized"}),
            mimetype="application/json",
            status_code=401
        )
    except TimeoutError as e:
        logger.error(f"Request timed out: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)}),
            mimetype="application/json",
            status_code=504  # Gateway Timeout
        )
    except JiraFetchError as e:
        logger.error(f"Jira fetch error: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": f"Jira API error: {str(e)}"}),
            mimetype="application/json",
            status_code=502  # Bad Gateway
        )
    except Exception as e:
        logger.error(f"Error processing release notes: {str(e)}", exc_info=True)  # Include stack trace
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": "Internal Server Error"}),
            mimetype="application/json",
            status_code=500
        )

# Route with max_results as a parameter
@release_notes_bp.route(route="release-notes/{proj}/{fixver}/{issuetype}/{max_results}", methods=["PUT"])
async def release_notes_with_limit_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP handler to trigger fetching, analyzing, and publishing release notes
    with a specific limit on the number of issues to process.
    """
    logger = logging.getLogger('azure.functions')
    
    # Get route parameters
    proj = req.route_params.get('proj')
    fixver = req.route_params.get('fixver')
    issuetype = req.route_params.get('issuetype')
    max_results_str = req.route_params.get('max_results', '10')
    
    try:
        max_results = int(max_results_str)
    except ValueError:
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": f"Invalid max_results value: {max_results_str}. Must be an integer."}),
            mimetype="application/json",
            status_code=400
        )
    
    logger.info(f"Processing request: /release-notes/{proj}/{fixver}/{issuetype}/{max_results}")
    logger.debug(f"Request parameters - proj: {proj}, fixver: {fixver}, issuetype: {issuetype}, max_results: {max_results}")
    
    # Validate input parameters
    valid, errors = validate_input(proj, fixver, issuetype)
    if not valid:
        logger.error(f"Input validation failed: {errors}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": errors}),
            mimetype="application/json",
            status_code=400
        )
    
    # Validate max_results
    if max_results <= 0 or max_results > 1000:
        logger.error(f"Invalid max_results value: {max_results}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": "max_results must be between 1 and 1000"}),
            mimetype="application/json",
            status_code=400
        )
    
    jql = f"project = {proj} AND fixversion = {fixver} AND issuetype = {issuetype}"
    logger.debug(f"Constructed JQL: {jql}")
    
    # Get configuration from Config class with custom max_results
    config_object = Config()
    config = config_object.get_enricher_config_with_options(jql, issuetype, max_results=max_results)
    
    try:
        # Use timeout function to prevent hanging processes
        result = await process_with_timeout(config)
        logger.info(f"Successfully processed request for {proj}/{fixver}/{issuetype} with max_results: {max_results}")
        
        return func.HttpResponse(
            body=json.dumps({"status": "success"}),
            mimetype="application/json",
            status_code=200
        )
        
    except HttpUnauthorizedError:
        logger.error("Unauthorized access to Jira API")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": "Unauthorized"}),
            mimetype="application/json",
            status_code=401
        )
    except TimeoutError as e:
        logger.error(f"Request timed out: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)}),
            mimetype="application/json",
            status_code=504  # Gateway Timeout
        )
    except JiraFetchError as e:
        logger.error(f"Jira fetch error: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": f"Jira API error: {str(e)}"}),
            mimetype="application/json",
            status_code=502  # Bad Gateway
        )
    except Exception as e:
        logger.error(f"Error processing release notes: {str(e)}", exc_info=True)  # Include stack trace
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": "Internal Server Error"}),
            mimetype="application/json",
            status_code=500
        )
