# Example script showing how to process multiple issue types with different limits
import sys
import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Add parent directory to path so we can import from our modules
sys.path.append(str(Path(__file__).parent.parent))

from config import Config
from src.api.api_server import JiraEnricher

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def process_issue_type(
    project: str, 
    fixversion: str, 
    issuetype: str, 
    max_results: int,
    disable_ssl_verify: bool = False
) -> None:
    """
    Process a specific issue type with custom max_results limit.
    
    Args:
        project: Jira project key
        fixversion: Fix version to filter by
        issuetype: Issue type to process
        max_results: Maximum number of issues to process
        disable_ssl_verify: Whether to disable SSL certificate verification for Atlassian APIs
    """
    # Create JQL query for the issues
    jql = f"project = {project} AND fixversion = {fixversion} AND issuetype = {issuetype}"
    
    # Initialize our configuration with custom max_results
    config = Config()
    enricher_config = config.get_enricher_config_with_options(jql, issuetype, max_results=max_results)
    
    # Override SSL verification if needed
    if disable_ssl_verify:
        enricher_config['ssl_verify'] = False
        # Suppress SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    logging.info(f"Processing {max_results} {issuetype}s for {project} {fixversion}")
    
    # Run the enricher
    try:
        await JiraEnricher(enricher_config).fetch_and_analyze_issues()
        logging.info(f"Completed processing {issuetype}s")
        return True
    except Exception as e:
        logging.error(f"Error processing {issuetype}s: {str(e)}")
        # Log more details for troubleshooting
        import traceback
        logging.debug(f"Full exception details: {traceback.format_exc()}")
        return False

async def main():
    """
    Run the JiraEnricher with different issue types and custom limits.
    
    Usage: python process_multiple_types.py <project> <fixversion> [--disable-ssl-verify]
    Example: python process_multiple_types.py "MyProject" "1.0"
    Example with SSL verification disabled: python process_multiple_types.py "MyProject" "1.0" --disable-ssl-verify
    """
    # Check for the --disable-ssl-verify flag
    disable_ssl_verify = "--disable-ssl-verify" in sys.argv
    
    # Remove the flag from sys.argv if present for argument counting
    args = [arg for arg in sys.argv if arg != "--disable-ssl-verify"]
    
    if len(args) != 3:
        print("Usage: python process_multiple_types.py <project> <fixversion> [--disable-ssl-verify]")
        sys.exit(1)
        
    project = args[1]
    fixversion = args[2]
    
    if disable_ssl_verify:
        logging.warning("SSL verification is disabled. This is not recommended for production environments.")
    
    # Define issue types and their limits
    issue_type_limits = [
        ("Bug", 10),      # Process up to 10 bugs
        ("Epic", 3),      # Process up to 3 epics
        ("Story", 5)      # Process up to 5 user stories
    ]
    
    results = []
    
    # Process each issue type sequentially
    for issuetype, max_results in issue_type_limits:
        success = await process_issue_type(
            project, 
            fixversion, 
            issuetype, 
            max_results, 
            disable_ssl_verify=disable_ssl_verify
        )
        results.append((issuetype, success))
    
    # Report results
    logging.info("--- Processing Results ---")
    for issuetype, success in results:
        status = "✓ Success" if success else "✗ Failed"
        logging.info(f"{issuetype}: {status}")

if __name__ == "__main__":
    asyncio.run(main())
