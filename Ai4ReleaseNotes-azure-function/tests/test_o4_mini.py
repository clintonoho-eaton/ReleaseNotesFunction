#!/usr/bin/env python
"""
Test script to verify o4-mini model compatibility.
This script tests the core functionality without actually calling Jira APIs.
"""

import sys
import os
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import local modules
from config import Config
from jira_enricher import JiraEnricher
from models import JiraIssue

# Mock Jira issue data for testing
def create_mock_jira_issue() -> Dict[str, Any]:
    """Create mock Jira issue data for testing."""
    return {
        "key": "TEST-123",
        "fields": {
            "summary": "Test issue for o4-mini compatibility",
            "description": "This is a test issue to verify that o4-mini model parameters work correctly.",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Done"},
            "resolution": {"name": "Fixed"},
            "priority": {"name": "Medium"},
            "assignee": {"displayName": "Test User"},
            "reporter": {"displayName": "Test Reporter"},
            "created": "2023-08-15T10:00:00.000+0000",
            "updated": "2023-08-16T11:00:00.000+0000",
            "fixVersions": [{"name": "1.0.0"}],
            "components": [{"name": "Test Component"}]
        }
    }

async def test_o4_mini_compatibility():
    """Test o4-mini model compatibility."""
    logging.info("Starting o4-mini compatibility test")
    
    # Get configuration
    config = Config().get_enricher_config("project = TEST", "Bug")
    
    # Explicitly set to o4-mini deployment
    config['azure_openai_gpt_deployment'] = 'o4-mini'
    logging.info(f"Using deployment: {config['azure_openai_gpt_deployment']}")
    logging.info(f"Using API version: {config['azure_openai_chat_completions_api_version']}")
    
    # Initialize JiraEnricher
    logging.info("Initializing JiraEnricher")
    enricher = JiraEnricher(config)
    logging.info("JiraEnricher initialization successful")
    
    # Create a mock Jira issue to test with
    mock_issue_data = create_mock_jira_issue()
    jira_issue = JiraIssue.from_dict(mock_issue_data)
    
    # Test analyzing a mock issue
    try:
        logging.info(f"Testing analyze_issue_with_ai method for issue {jira_issue.key}")
        
        # Set this to True to actually call Azure OpenAI API (requires valid credentials)
        # Set to False to just check initialization and parameter handling
        test_api_call = False
        
        if test_api_call:
            # Actual API call (uncomment if you want to test the full flow)
            result = await enricher.analyze_issue_with_ai(jira_issue)
            logging.info("Analysis successful!")
            logging.info(f"Result summary: {result[:100]}...")
        else:
            # Just verify the configuration adjustments
            logging.info("Checking configuration adjustments for o4-mini")
            enricher._adjust_config_for_model()
            logging.info("Configuration adjustment successful")
            
        logging.info("Test completed successfully!")
        return True
        
    except Exception as e:
        logging.error(f"Error during test: {str(e)}")
        import traceback
        logging.error(f"Detailed error: {traceback.format_exc()}")
        return False

async def main():
    """Main entry point."""
    success = await test_o4_mini_compatibility()
    
    if success:
        logging.info("✅ o4-mini compatibility test PASSED")
        sys.exit(0)
    else:
        logging.error("❌ o4-mini compatibility test FAILED")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
