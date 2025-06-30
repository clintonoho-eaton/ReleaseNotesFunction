# Example script showing batch processing of release notes with optimized configuration
import sys
import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor

# Add parent directory to path so we can import from our modules
sys.path.append(str(Path(__file__).parent.parent))

from config import Config
from src.api.api_server import JiraEnricher

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def process_issue_types_batch(
    project: str, 
    fixversion: str, 
    issue_type_limits: List[Tuple[str, int]]
) -> None:
    """
    Process multiple issue types with their respective limits.
    
    Args:
        project: Jira project key
        fixversion: Fix version to filter by
        issue_type_limits: List of tuples containing (issue_type, max_results)
    """
    # Get configurations for all issue types at once
    config = Config()
    configs = config.get_multiple_issue_type_configs(project, fixversion, issue_type_limits)
    
    # Log the processing plan
    logging.info(f"Processing release notes for {project} {fixversion}")
    for i, (issue_type, limit) in enumerate(issue_type_limits):
        logging.info(f"  • {issue_type}: Up to {limit} issues")
    
    # Process each configuration
    results = []
    for i, (issue_type, limit) in enumerate(issue_type_limits):
        try:
            logging.info(f"Processing {issue_type}s ({i+1}/{len(issue_type_limits)})")
            await JiraEnricher(configs[i]).fetch_and_analyze_issues()
            results.append((issue_type, True))
            logging.info(f"✓ Successfully processed {issue_type}s")
        except Exception as e:
            logging.error(f"✗ Failed to process {issue_type}s: {str(e)}")
            results.append((issue_type, False))
    
    # Report summary
    logging.info("\n--- Processing Summary ---")
    success_count = sum(1 for _, success in results if success)
    logging.info(f"Successfully processed {success_count}/{len(issue_type_limits)} issue types")
    
    return results

async def main():
    """
    Batch processing of release notes for a project and fixversion.
    
    Usage: python batch_process_release_notes.py <project> <fixversion>
    Example: python batch_process_release_notes.py "MyProject" "1.0"
    """
    if len(sys.argv) != 3:
        print("Usage: python batch_process_release_notes.py <project> <fixversion>")
        sys.exit(1)
        
    project = sys.argv[1]
    fixversion = sys.argv[2]
    
    # Define issue types and their limits
    # Format: (issue_type, max_results)
    issue_type_limits = [
        ("Bug", 10),      # Process up to 10 bugs
        ("Story", 5),     # Process up to 5 user stories
        ("Epic", 2)       # Process up to 2 epics
    ]
    
    await process_issue_types_batch(project, fixversion, issue_type_limits)

if __name__ == "__main__":
    asyncio.run(main())
