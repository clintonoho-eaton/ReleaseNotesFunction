#!/usr/bin/env python
"""
Test script to verify parent ID loading logic and identify any discrepancies.
"""
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add the project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
print(f"Project root: {project_root}")

# Configure logging - output to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler("parent_id_test.log")  # File output
    ]
)

# Log Python version and path
logging.info(f"Python version: {sys.version}")
logging.info(f"Python executable: {sys.executable}")

# Load environment variables - try multiple approaches to ensure we get it loaded
# First try the root path
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
logging.info(f"Checking for .env at: {root_path}")

if os.path.exists(root_path):
    logging.info(f".env file exists at {root_path}")
    loaded = load_dotenv(dotenv_path=root_path, override=True)
    logging.info(f"Loaded environment from {root_path}: {loaded}")
else:
    logging.warning(f".env file NOT found at {root_path}")
    # Try current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(current_dir, '.env')
    logging.info(f"Trying current directory: {env_path}")
    if os.path.exists(env_path):
        loaded = load_dotenv(dotenv_path=env_path, override=True)
        logging.info(f"Loaded environment from {env_path}: {loaded}")
    else:
        logging.warning(f".env file NOT found in current directory")

# Check environment variables (all the ones we might need)
env_vars = [
    'CONFLUENCE_PARENT_ID',
    'CONFLUENCE_PARENT_PAGE_ID',
    'CONFLUENCE_SPACE',
    'CONFLUENCE_SPACE_KEY',
    'ATLASSIAN_URL'
]

for var in env_vars:
    value = os.environ.get(var)
    logging.info(f"From environment: {var} = {value}")

# Special focus on parent ID since that's what we're testing
env_parent_id = os.environ.get('CONFLUENCE_PARENT_ID')
logging.info(f"From environment: CONFLUENCE_PARENT_ID = {env_parent_id}")

# Import required modules for configuration testing
from src.config.app_config import Config

# Get config from app_config - using the proper method instead of get_config()
config_obj = Config()
# Using a simple dummy JQL and issue type to get a config
enricher_config = config_obj.get_enricher_config("project = TEST", "Bug")
config_parent_id = enricher_config.get('confluence_parent_id')
config_parent_page_id = enricher_config.get('confluence_parent_page_id')
logging.info(f"From enricher_config: confluence_parent_id = {config_parent_id}")
logging.info(f"From enricher_config: confluence_parent_page_id = {config_parent_page_id}")

# Simulate JiraEnricher logic
# Before our change:
before_change = enricher_config.get('confluence_parent_id') or enricher_config.get('confluence_parent_page_id')
logging.info(f"Before our change: parent_id = {before_change}")

# After our change:
after_change = os.environ.get('CONFLUENCE_PARENT_ID') or enricher_config.get('confluence_parent_id') or enricher_config.get('confluence_parent_page_id')
logging.info(f"After our change: parent_id = {after_change}")

# Summary
logging.info("=== Summary ===")
if env_parent_id == after_change:
    logging.info("✅ Our change is correctly using the environment variable")
else:
    logging.error("❌ Our change is NOT using the environment variable correctly")

if before_change != after_change:
    logging.info(f"🔄 The parent ID has changed: {before_change} -> {after_change}")
else:
    logging.info("⚠️ The parent ID has NOT changed - both methods give the same result")

# Check if the conflicting parent IDs are found
if before_change == "626655486":
    logging.info("🔍 The previous logic was using the incorrect parent ID (626655486)")
elif before_change:
    logging.info(f"🔍 The previous logic was using this parent ID: {before_change}")

if after_change == "623280329":
    logging.info("✅ The new logic is using the correct parent ID (623280329) from .env file")
elif after_change:
    logging.info(f"The new logic is using this parent ID: {after_change}")
else:
    logging.info("❌ No parent ID was found with either method")
