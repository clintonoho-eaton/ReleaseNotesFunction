"""
Flask routes for the Ai4ReleaseNotes API.

This module defines additional API routes for the application.
"""

import logging
import asyncio
from typing import Any, Dict, Tuple, Union

from flask import Flask, jsonify

from src.exceptions.api_exceptions import HttpUnauthorizedError, JiraFetchError
from src.jira.jira_enricher import JiraEnricher
from src.config.app_config import Config

# Initialize configuration
app_config = Config()

# Create Flask app
app = Flask(__name__)

@app.route(
    '/release-notes/<proj>/<fixver>/<issuetype>', methods=['PUT']
)
def release_notes_handler(
    proj: str, fixver: str, issuetype: str
) -> Tuple[Dict[str, Any], int]:
    """
    HTTP handler to trigger fetching, analyzing, and publishing release notes.
    Uses default max_results from configuration.
    
    Args:
        proj: Project key
        fixver: Fix version
        issuetype: Issue type
        
    Returns:
        JSON response
    """
    logging.info(f"Extension route: Received request: /release-notes/{proj}/{fixver}/{issuetype}")
    
    jql = f"project = {proj} AND fixversion = {fixver} AND issuetype = {issuetype}"
    logging.info(f"Constructed JQL: {jql}")
    
    # Get configuration from Config class
    config = app_config.get_enricher_config(jql, issuetype)
    
    try:
        # Use asyncio to run the enricher
        result = asyncio.run(process_with_timeout(config))
        
        # Check if there were any warnings or info messages to include
        warnings = []
        info_msgs = []
        
        # Check log handlers for recent messages
        for handler in logging.getLogger().handlers:
            if hasattr(handler, 'recent_records'):
                for record in handler.recent_records:
                    if record.levelno == logging.WARNING:
                        warnings.append(record.getMessage())
                    elif record.levelno == logging.INFO and 'success' in record.getMessage().lower():
                        info_msgs.append(record.getMessage())
        
        # Build response with detailed information
        response = {
            "status": "success",
            "project": proj,
            "fixVersion": fixver,
            "issueType": issuetype,
            "processingTime": result.get('processing_time', 0) if isinstance(result, dict) else 0
        }
        
        # Include any warnings if they exist
        if warnings:
            response["warnings"] = warnings[-3:]  # Include up to 3 most recent warnings
        
        # Include relevant success information
        if info_msgs:
            response["details"] = info_msgs[-3:]  # Include up to 3 most recent success messages
        elif isinstance(result, dict) and result.get('details'):
            response["details"] = result.get('details')
        else:
            response["details"] = f"Successfully processed request for {proj}/{fixver}/{issuetype}"
            
        return jsonify(response), 200
    except HttpUnauthorizedError:
        logging.error("Unauthorized access to Jira API")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    except JiraFetchError as e:
        logging.error(f"Jira fetch error: {str(e)}")
        return jsonify({"status": "error", "message": f"Jira API error: {str(e)}"}), 502
    except Exception as e:
        logging.error(f"Error processing release notes: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500

# Process with timeout function
async def process_with_timeout(config, timeout_seconds=300):
    """
    Process with timeout to prevent hanging processes.
    
    Args:
        config: Enricher configuration
        timeout_seconds: Timeout in seconds
        
    Returns:
        Result of the enricher
        
    Raises:
        TimeoutError: If the process takes too long
    """
    try:
        # Create enricher
        enricher = JiraEnricher(config)
        
        # Create a task with timeout
        result = await asyncio.wait_for(
            enricher.fetch_and_analyze_issues(),
            timeout=timeout_seconds
        )
        
        # Include processing time if not present in result
        if isinstance(result, dict) and 'processing_time' not in result:
            result['processing_time'] = 0  # Default value
            
        return result
        
    except asyncio.TimeoutError:
        logging.error(f"Operation timed out after {timeout_seconds} seconds")
        raise TimeoutError(f"Processing timed out after {timeout_seconds} seconds. Please try with fewer issues.")
        
    except Exception as e:
        logging.error(f"Error during processing: {str(e)}", exc_info=True)
        raise
