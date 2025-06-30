# Example script showing how to use the enricher with a custom max_results limit
import sys
import os
import asyncio
import logging
from pathlib import Path

# Add parent directory to path so we can import from our modules
sys.path.append(str(Path(__file__).parent.parent))

from config import Config
from src.api.api_server import JiraEnricher

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    """
    Run the JiraEnricher with a custom max_results limit.
    
    Usage: python run_with_custom_limit.py <project> <fixversion> <issuetype> <max_results>
    Example: python run_with_custom_limit.py "MyProject" "1.0" "Bug" 5
    """
    if len(sys.argv) != 5:
        print("Usage: python run_with_custom_limit.py <project> <fixversion> <issuetype> <max_results>")
        sys.exit(1)
        
    project = sys.argv[1]
    fixversion = sys.argv[2]
    issuetype = sys.argv[3]
    
    try:
        max_results = int(sys.argv[4])
        if max_results <= 0:
            raise ValueError("max_results must be a positive integer")
    except ValueError as e:
        print(f"Error: {e}")
        print("max_results must be a positive integer")
        sys.exit(1)
    
    # Create JQL query for the issues
    jql = f"project = {project} AND fixversion = {fixversion} AND issuetype = {issuetype}"
    
    # Initialize our configuration with custom max_results
    config = Config()
    enricher_config = config.get_enricher_config_with_options(jql, issuetype, max_results=max_results)
    
    logging.info(f"Processing {issuetype}s for {project} {fixversion} with limit: {max_results}")
    
    # Run the enricher
    await JiraEnricher(enricher_config).fetch_and_analyze_issues()
    
    logging.info("Processing complete!")

if __name__ == "__main__":
    asyncio.run(main())
