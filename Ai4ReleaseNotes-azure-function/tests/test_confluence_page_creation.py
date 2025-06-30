"""
Test script to manually verify Confluence page creation.

This script will create a sample page in Confluence to verify the API integration works correctly.
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime

# Add the parent directory to sys.path to allow for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the JiraAPIWrapper for Confluence page creation
from src.jira.jira_client import JiraAPIWrapper
from src.utils.file_utils import format_issue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_create_confluence_page():
    """Test creating a Confluence page with correctly formatted content."""
    logging.info("Testing Confluence page creation")
    
    # Initialize the JiraAPIWrapper
    wrapper = JiraAPIWrapper()
    
    # Check if the Confluence client is initialized correctly
    if not wrapper.initialize_confluence_client():
        logging.error("Failed to initialize Confluence client")
        return False
    
    # Create sample issue data
    issue_data = {
        "key": "TEST-123",
        "fields": {
            "summary": "Test Issue for Confluence Page Creation",
            "issuetype": {
                "name": "Bug"
            }
        }
    }
    
    # Create sample analysis data
    analysis_data = {
        "executive_summary": "This is an executive summary of the issue. It provides a high-level overview of what the issue is about.",
        "technical_summary": "This is a technical summary of the issue, providing more details about the technical aspects.",
        "cause": "The issue was caused by incorrect data formatting in the database.",
        "fix": "The fix involved updating the data validation logic and reformatting existing data.",
        "impact": "This issue affected approximately 10% of users, causing errors in report generation.",
        "inferredCategories": ["Data Integrity", "User Interface", "Performance"],
        "confidence": 0.85
    }
    
    # Format the issue for Confluence
    html_body = format_issue(issue_data, analysis_data)
    
    # Check if the content was generated correctly
    if not html_body or len(html_body) < 100:
        logging.error("Generated HTML content is too short or empty")
        return False
    
    logging.info(f"Generated HTML content length: {len(html_body)} characters")
    
    # Create unique title for the test page to avoid conflicts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = f"TEST-123 - Confluence Test Page {timestamp}"
    
    # Get Confluence configuration from environment variables
    confluence_space = os.environ.get("CONFLUENCE_SPACE") or os.environ.get("CONFLUENCE_SPACE_KEY")
    parent_id = os.environ.get("CONFLUENCE_PARENT_ID") or os.environ.get("CONFLUENCE_PARENT_PAGE_ID")
    
    if not confluence_space:
        logging.error("CONFLUENCE_SPACE environment variable is required")
        return False
    
    # Create a small preview of the HTML content for debugging
    preview_length = min(200, len(html_body))
    logging.info(f"HTML preview: {html_body[:preview_length]}...")
    
    # Prepare page data
    page_data = {
        "space": confluence_space,
        "title": title,
        "body": html_body
    }
    
    # Add parent_id if available
    if parent_id:
        page_data["parent_id"] = parent_id
    
    # Create the page
    logging.info(f"Creating test page '{title}' in space '{confluence_space}'")
    try:
        response = wrapper.page_create(json.dumps(page_data))
        
        if isinstance(response, dict) and response.get('error'):
            logging.error(f"Failed to create page: {response.get('error')}")
            return False
        
        # Check if the response indicates success
        if isinstance(response, dict) and (response.get('id') or response.get('success')):
            page_id = response.get('id', '')
            logging.info(f"Successfully created page with ID: {page_id}")
            
            # Construct the URL to the created page
            confluence_base_url = os.environ.get('CONFLUENCE_URL', '') or os.environ.get('ATLASSIAN_URL', '')
            if response.get('url'):
                page_url = response.get('url')
            elif confluence_base_url:
                page_url = f"{confluence_base_url}/wiki/pages/viewpage.action?pageId={page_id}"
            else:
                page_url = f"Page ID: {page_id}"
                
            logging.info(f"Page URL: {page_url}")
            return True
        else:
            logging.error(f"Unexpected response: {response}")
            return False
    except Exception as e:
        logging.error(f"Exception during page creation: {str(e)}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = test_create_confluence_page()
        sys.exit(0 if success else 1)
    except Exception as e:
        logging.error(f"Test failed with exception: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
