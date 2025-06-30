"""
Test script to verify the format_issue function generates proper HTML content for Confluence.
"""

import os
import sys
import logging
import json
import traceback

# Add the parent directory to sys.path to allow for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the format_issue function
from src.utils.file_utils import format_issue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_format_issue():
    """Test that format_issue correctly formats content for Confluence."""
    logging.info("Testing format_issue function")
    
    # Create sample issue data
    issue_data = {
        "key": "TEST-123",
        "fields": {
            "summary": "Test Issue Summary",
            "issuetype": {
                "name": "Bug"
            }
        }
    }
    
    # Create sample analysis data
    analysis_data = {
        "executive_summary": "This is an executive summary of the issue.",
        "technical_summary": "This is a technical summary of the issue.",
        "cause": "This is the cause of the issue.",
        "fix": "This is how the issue was fixed.",
        "impact": "This is the impact of the issue.",
        "inferredCategories": ["UI", "Performance"],
        "confidence": 0.85
    }
    
    # Format the issue
    result = format_issue(issue_data, analysis_data)
    
    # Test assertions
    assert result is not None, "Result should not be None"
    assert len(result) > 0, "Result should not be empty"
    assert "<h1>TEST-123" in result, "Result should include issue key in heading"
    assert "<h2>Executive Summary</h2>" in result, "Result should include executive summary heading"
    assert "<h2>Technical Summary</h2>" in result, "Result should include technical summary heading"
    assert "This is an executive summary of the issue." in result, "Executive summary content missing"
    
    logging.info("Test successful - format_issue generates proper HTML content for Confluence")
    
    # Print the result for manual inspection
    logging.info("\n=== Generated HTML Preview ===\n")
    logging.info(result[:500] + "..." if len(result) > 500 else result)
    logging.info("\n=== End of Preview ===\n")
    
    return True

if __name__ == "__main__":
    try:
        test_result = test_format_issue()
        sys.exit(0 if test_result else 1)
    except Exception as e:
        logging.error(f"Test failed with exception: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
