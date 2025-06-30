#!/usr/bin/env python
"""
Test script to verify Confluence parent page ID is working correctly.

This script will:
1. Connect to Confluence using provided credentials
2. Get the parent page using the provided page ID
3. Create a test child page under the parent page
4. Read the created test page to verify it exists
5. Delete the test page to clean up

This script reads configuration from a .env file in the project root,
current directory, or working directory.

Required variables in .env file:
- CONFLUENCE_URL or ATLASSIAN_URL: URL of your Confluence instance
- CONFLUENCE_USERNAME or ATLASSIAN_USERNAME: Your Confluence username
- CONFLUENCE_API_TOKEN or ATLASSIAN_API_KEY: Your Confluence API token
- CONFLUENCE_PARENT_ID: The ID of the parent page to test

Example .env file:
ATLASSIAN_URL=https://your-instance.atlassian.net
ATLASSIAN_USERNAME=your-email@example.com
ATLASSIAN_API_KEY=your-api-token
CONFLUENCE_PARENT_ID=12345
"""

import os
import sys
import logging
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add the current directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.jira.jira_client import JiraAPIWrapper

# Configure logging to see detailed output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Test Confluence parent page connection."""
    logging.info("Testing Confluence parent page connection")
    
    # Load .env file from multiple possible locations
    loaded = False
    
    # First try: Project root
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
    if os.path.exists(root_path):
        loaded = load_dotenv(dotenv_path=root_path, override=True)
        logging.info(f"Loaded environment from {root_path}")
    
    # Second try: Current directory
    if not loaded:
        current_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.env'))
        if os.path.exists(current_path):
            loaded = load_dotenv(dotenv_path=current_path, override=True)
            logging.info(f"Loaded environment from {current_path}")
    
    # Third try: Working directory
    if not loaded:
        cwd_path = os.path.abspath(os.path.join(os.getcwd(), '.env'))
        if os.path.exists(cwd_path):
            loaded = load_dotenv(dotenv_path=cwd_path, override=True)
            logging.info(f"Loaded environment from {cwd_path}")
    
    if not loaded:
        logging.warning("No .env file found. Using environment variables.")
    
    # Get Confluence settings from environment
    confluence_url = os.environ.get('CONFLUENCE_URL') or os.environ.get('ATLASSIAN_URL')
    confluence_username = os.environ.get('CONFLUENCE_USERNAME') or os.environ.get('ATLASSIAN_USERNAME') 
    confluence_api_token = os.environ.get('CONFLUENCE_API_TOKEN') or os.environ.get('ATLASSIAN_API_KEY')
    parent_id = os.environ.get('CONFLUENCE_PARENT_ID')
    
    # Check if essential variables are provided
    missing_vars = []
    if not confluence_url:
        missing_vars.append('CONFLUENCE_URL or ATLASSIAN_URL')
    if not confluence_username:
        missing_vars.append('CONFLUENCE_USERNAME or ATLASSIAN_USERNAME')
    if not confluence_api_token:
        missing_vars.append('CONFLUENCE_API_TOKEN or ATLASSIAN_API_KEY')
    if not parent_id:
        missing_vars.append('CONFLUENCE_PARENT_ID')
        
    if missing_vars:
        logging.error(f"Missing required environment variables for Confluence test: {', '.join(missing_vars)}")
        logging.error("Please set these variables in your .env file or environment and try again.")
        return False
    
    logging.info(f"Confluence URL: {confluence_url}")
    logging.info(f"Confluence Username: {confluence_username}")
    logging.info(f"Parent ID: {parent_id} (type: {type(parent_id)})")
    
    # Create JiraAPIWrapper with Confluence support
    client = JiraAPIWrapper(
        jira_instance_url=confluence_url,
        jira_username=confluence_username,
        jira_api_token=confluence_api_token,
        confluence_instance_url=confluence_url,
        confluence_username=confluence_username,
        confluence_api_token=confluence_api_token
    )
    
    try:
        # Initialize Confluence client
        if not client.initialize_confluence_client():
            logging.error("Failed to initialize Confluence client")
            return False
            
        # Test getting the parent page
        logging.info(f"Attempting to get parent page with ID: {parent_id}")
        parent_page = client.confluence.get_page_by_id(parent_id)
        
        if not parent_page:
            logging.error("❌ Failed to retrieve parent page (returned None)")
            return False
        
        logging.info(f"✅ Successfully retrieved parent page: Title='{parent_page.get('title')}', ID={parent_page.get('id')}")
        
        # Extract space key from parent page
        space_key = parent_page.get('space', {}).get('key')
        if not space_key:
            logging.error("❌ Failed to extract space key from parent page")
            return False
            
        # Create a test page under the parent
        test_page_title = f"Test Page - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        test_page_body = """
        <p>This is a test page created by the Confluence test script.</p>
        <p>This page can be safely deleted after testing.</p>
        """
        
        logging.info(f"Creating test page '{test_page_title}' in space '{space_key}' under parent ID {parent_id}")
        
        result = client.confluence.create_page(
            space=space_key,
            title=test_page_title,
            body=test_page_body,
            parent_id=parent_id
        )
        
        if not result or result.get('error'):
            error_msg = result.get('error') if result else "Unknown error"
            logging.error(f"❌ Failed to create test page: {error_msg}")
            return False
            
        test_page_id = result.get('id')
        logging.info(f"✅ Successfully created test page: Title='{test_page_title}', ID={test_page_id}")
        
        # Read the created test page to verify
        logging.info(f"Reading created test page with ID: {test_page_id}")
        created_page = client.confluence.get_page_by_id(test_page_id)
        
        if not created_page:
            logging.error("❌ Failed to read the created test page")
            return False
            
        logging.info(f"✅ Successfully read the created test page: Title='{created_page.get('title')}'")
        
        # Delete the test page
        logging.info(f"Deleting test page with ID: {test_page_id}")
        
        # Since there's no built-in delete_page method, we'll use a custom approach
        delete_url = f"{confluence_url}/wiki/rest/api/content/{test_page_id}"
        
        try:
            response = requests.delete(
                delete_url,
                auth=(confluence_username, confluence_api_token),
                verify=False  # Following the pattern used in other methods
            )
            
            if response.status_code in (200, 204):
                logging.info(f"✅ Successfully deleted test page: ID={test_page_id}")
            else:
                logging.warning(f"⚠️ Failed to delete test page: Status code {response.status_code}")
                logging.warning(f"Response text: {response.text}")
                # Not returning False as the main test has already succeeded
        except Exception as delete_error:
            logging.warning(f"⚠️ Error during page deletion: {str(delete_error)}")
            # Not returning False as the main test has already succeeded
            
        return True
    
    except Exception as e:
        logging.error(f"❌ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
