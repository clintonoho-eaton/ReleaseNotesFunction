"""Configuration management for the Jira Enrichment application."""

import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from src.exceptions.api_exceptions import ConfigurationError

class Config:
    """Configuration manager for the application."""
    
    # Default configuration values
    # Maximum number of Jira issues to process - adjust this value as needed
    DEFAULT_MAX_RESULTS = 2
    
    # Required environment variables for the application
    REQUIRED_ENV_VARS = [
        'AZURE_OPENAI_KEY',
        'AZURE_OPENAI_CHAT_COMPLETIONS_API_VERSION',
        'AZURE_OPENAI_GPT_DEPLOYMENT',
        'AZURE_OPENAI_ENDPOINT',
        'ATLASSIAN_URL',
        'ATLASSIAN_USERNAME',
        'ATLASSIAN_API_KEY',
    ]
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        # Try multiple potential locations for the .env file
        loaded = False
        
        # First try: Project root (two levels up from config dir)
        root_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        loaded = load_dotenv(dotenv_path=root_path, override=True)
        
        if loaded:
            logging.info(f"Successfully loaded environment from {root_path}")
        else:
            # Second try: One level up (src directory)
            src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
            loaded = load_dotenv(dotenv_path=src_path, override=True)
            
            if loaded:
                logging.info(f"Successfully loaded environment from {src_path}")
            else:
                # Third try: Current working directory
                cwd_path = os.path.join(os.getcwd(), '.env')
                loaded = load_dotenv(dotenv_path=cwd_path, override=True)
                
                if loaded:
                    logging.info(f"Successfully loaded environment from {cwd_path}")
                else:
                    # Last try: Just .env (relative to current directory)
                    fallback_path = '.env'
                    loaded = load_dotenv(dotenv_path=fallback_path, override=True)
                    
                    if loaded:
                        logging.info(f"Successfully loaded environment from fallback path {fallback_path}")
                    else:
                        logging.warning("Could not find .env file in any location. Using environment variables only.")
                        logging.info(f"Expected .env file locations (in order of preference):")
                        logging.info(f"  1. {root_path}")
                        logging.info(f"  2. {src_path}")
                        logging.info(f"  3. {cwd_path}")
                        logging.info(f"  4. {os.path.abspath(fallback_path)}")
                        logging.info(f"Please create a .env file based on .env.example in one of these locations.")
        
        # Validate required environment variables
        self._validate_env_vars()
    
    def _validate_env_vars(self) -> None:
        """Validate that all required environment variables are set."""
        missing_vars = [var for var in self.REQUIRED_ENV_VARS if not os.getenv(var)]
        if missing_vars:
            msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logging.error(msg)
            raise ConfigurationError(msg)
    
    def is_production(self) -> bool:
        """Check if the application is running in production mode."""
        return os.getenv("ENVIRONMENT", "development").lower() == "production"
    
    def get_enricher_config(self, jql: str, issuetype: str) -> Dict[str, Any]:
        """
        Get configuration for the JiraEnricher.
        
        Args:
            jql: JQL query to fetch issues
            issuetype: Type of issue to analyze
            
        Returns:
            Dictionary with configuration values
        """
        return self._get_base_config(jql, issuetype)
    
    def get_enricher_config_with_options(self, jql: str, issuetype: str, **options) -> Dict[str, Any]:
        """
        Get configuration for the JiraEnricher with additional options.
        
        Args:
            jql: JQL query to fetch issues
            issuetype: Type of issue to analyze
            options: Additional configuration options
            
        Returns:
            Dictionary with configuration values
        """
        config = self._get_base_config(jql, issuetype)
        # Override with custom options
        for key, value in options.items():
            config[key] = value
        return config
    
    def _get_base_config(self, jql: str, issuetype: str) -> Dict[str, Any]:
        """
        Get base configuration for the JiraEnricher.
        
        Args:
            jql: JQL query to fetch issues
            issuetype: Type of issue to analyze
            
        Returns:
            Dictionary with base configuration values
        """
        # Base configuration settings
        config = {
            "jql": jql,
            "issue_type": issuetype,
            "max_results": int(os.getenv("MAX_RESULTS", self.DEFAULT_MAX_RESULTS)),
            
            # Jira configuration
            "jira_username": os.getenv("ATLASSIAN_USERNAME"),
            "jira_api_key": os.getenv("ATLASSIAN_API_KEY"),
            "jira_url": os.getenv("ATLASSIAN_URL"),
            
            # Azure OpenAI configuration
            "azure_openai_key": os.getenv("AZURE_OPENAI_KEY"),
            "azure_openai_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "azure_openai_chat_completions_api_version": os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_API_VERSION"),
            "azure_openai_gpt_deployment": os.getenv("AZURE_OPENAI_GPT_DEPLOYMENT"),
            
            # Output settings
            "create_local_files": os.getenv("CREATE_LOCAL_FILES", "True").lower() == "true",
            "ssl_verify": os.getenv("SSL_VERIFY", "False").lower() == "true",
            
            # Confluence settings if available
            "create_confluence_pages": os.getenv("CREATE_CONFLUENCE_PAGES", "False").lower() == "true",
            "confluence_space_key": os.getenv("CONFLUENCE_SPACE_KEY") or os.getenv("CONFLUENCE_SPACE"),
            "confluence_space": os.getenv("CONFLUENCE_SPACE") or os.getenv("CONFLUENCE_SPACE_KEY"),  # Add both naming variants
            "confluence_parent_page_id": os.getenv("CONFLUENCE_PARENT_PAGE_ID") or os.getenv("CONFLUENCE_PARENT_ID"),
            "confluence_parent_id": os.getenv("CONFLUENCE_PARENT_ID") or os.getenv("CONFLUENCE_PARENT_PAGE_ID"),  # Add both naming variants
            "confluence_base_url": os.getenv("CONFLUENCE_BASE_URL") or os.getenv("ATLASSIAN_URL"),
            "confluence_url": os.getenv("CONFLUENCE_URL") or os.getenv("ATLASSIAN_URL"),
        }
        
        return config
