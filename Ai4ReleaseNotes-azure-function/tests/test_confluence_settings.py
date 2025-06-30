#!/usr/bin/env python
"""
Test script to verify Confluence page creation settings are working.
"""

import sys
import os
import logging
from pathlib import Path
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Test environment variable loading."""
    logging.info("Testing environment variable loading and Confluence settings")
    
    # Print current working directory
    logging.info(f"Current working directory: {os.getcwd()}")
    
    # Initialize Config
    try:
        logging.info("Initializing Config")
        config = Config()
        logging.info("Config initialized successfully")
        
        # Get a test config
        enricher_config = config.get_enricher_config("project = TEST", "Bug")
        
        # Check the Confluence settings
        logging.info(f"create_confluence_pages: {enricher_config.get('create_confluence_pages')}")
        logging.info(f"create_local_files: {enricher_config.get('create_local_files')}")
        logging.info(f"confluence_space: {enricher_config.get('confluence_space')}")
        logging.info(f"confluence_parent_id: {enricher_config.get('confluence_parent_id')}")
        
        # Return success or failure
        if enricher_config.get('create_confluence_pages'):
            logging.info("✅ Confluence page creation is enabled!")
            return True
        else:
            logging.warning("❌ Confluence page creation is not enabled!")
            return False
    
    except Exception as e:
        logging.error(f"Error during test: {str(e)}")
        import traceback
        logging.error(f"Detailed error: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
