"""
Helper functions for file operations and data formatting/processing.
"""

import re
import datetime
import json
import os
import logging
from typing import List, Dict, Any

from src.models.jira_models import JiraIssueAnalysis, JiraBugAnalysis, JiraEpicAnalysis, JiraCompAnalysis


# Define a function to clean up a string
def clean_string(s):
    """
    Clean a string by removing URLs, line feed characters, and normalizing whitespace.
    
    Args:
        s: String to clean
        
    Returns:
        Cleaned string
    """
    if not s:
        logging.warning("No string to clean")
        return ""
        
    # Remove URLs
    s = re.sub(r'http\S+|www.\S+', '', s, flags=re.MULTILINE)
    
    # Remove line feed characters
    s = s.replace('\n', ' ')
    
    # Replace sequences of whitespace with a single space
    s = re.sub(r'\s+', ' ', s)
    
    return s.strip()


def cleanup_child(my_data):
    """
    Clean up a child issue, updating the summary and description.
    
    Args:
        my_data: Dictionary with issue data
        
    Returns:
        Cleaned issue data
    """
    # Clean up the fields
    if my_data.get('summary'):
        my_data['summary'] = clean_string(my_data['summary'])
        
    if my_data.get('description'):
        my_data['description'] = clean_string(my_data['description'])
        
    return my_data


def cleanup_issue(issue_data):
    """
    Clean up the issue data before processing.
    
    Args:
        issue_data: Dictionary with issue data
        
    Returns:
        Cleaned issue data
    """
    # Clean the main issue fields
    if issue_data.get('fields', {}).get('summary'):
        issue_data['fields']['summary'] = clean_string(issue_data['fields']['summary'])
        
    if issue_data.get('fields', {}).get('description'):
        issue_data['fields']['description'] = clean_string(issue_data['fields']['description'])
    
    # Clean child issues if they exist
    if issue_data.get('fields', {}).get('subtasks'):
        for i, subtask in enumerate(issue_data['fields']['subtasks']):
            issue_data['fields']['subtasks'][i] = cleanup_child(subtask)
    
    return issue_data


def normalize_issue_data(issue_data):
    """
    Normalize issue data to a standard format.
    
    Args:
        issue_data: Dictionary with issue data
        
    Returns:
        Normalized issue data
    """
    normalized = {}
    
    # Extract basic information
    normalized['key'] = issue_data.get('key', '')
    normalized['summary'] = issue_data.get('fields', {}).get('summary', '')
    normalized['description'] = issue_data.get('fields', {}).get('description', '')
    normalized['issue_type'] = issue_data.get('fields', {}).get('issuetype', {}).get('name', '')
    normalized['status'] = issue_data.get('fields', {}).get('status', {}).get('name', '')
    
    # Extract components
    normalized['components'] = []
    for component in issue_data.get('fields', {}).get('components', []):
        normalized['components'].append(component.get('name', ''))
    
    # Extract labels
    normalized['labels'] = issue_data.get('fields', {}).get('labels', [])
    
    # Extract fix versions
    normalized['fix_versions'] = []
    for version in issue_data.get('fields', {}).get('fixVersions', []):
        normalized['fix_versions'].append(version.get('name', ''))
    
    return normalized


def create_file_path(project, fix_version, issue_type, file_type="json"):
    """
    Create a file path for saving issue data.
    
    Args:
        project: Project key
        fix_version: Fix version
        issue_type: Issue type
        file_type: File type (json, md, xlsx)
        
    Returns:
        File path
    """
    # Get the root directory of the project
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Create directory for the project if it doesn't exist
    directory = os.path.join(root_dir, "output", project, fix_version)
    logging.info(f"Creating directory: {directory}")
    os.makedirs(directory, exist_ok=True)
    
    # Create timestamp for unique filenames
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create file path
    return f"{directory}/{issue_type}_{timestamp}.{file_type}"


def save_issues_to_file(issues, project, fix_version, issue_type, file_type="json"):
    """
    Save issues to a file.
    
    Args:
        issues: List of issues to save
        project: Project key
        fix_version: Fix version
        issue_type: Issue type
        file_type: File type (json, md, xlsx)
        
    Returns:
        File path
    """
    logging.info(f"Saving {len(issues)} issues for {project}/{fix_version}/{issue_type}")
    file_path = create_file_path(project, fix_version, issue_type, file_type)
    logging.info(f"Will save to: {file_path}")
    
    if not issues:
        logging.warning("No issues to save!")
        return None
    
    if file_type == "json":
        with open(file_path, 'w') as f:
            json.dump(issues, f, indent=2)
    elif file_type == "md":
        with open(file_path, 'w') as f:
            for issue in issues:
                f.write(f"# {issue.get('key')} - {issue.get('summary')}\n\n")
                f.write(f"**Status:** {issue.get('status')}\n\n")
                f.write(f"**Description:**\n{issue.get('description')}\n\n")
                f.write("---\n\n")
    
    logging.info(f"Saved {len(issues)} issues to {file_path}")
    return file_path


def format_issue(issue_data, analysis_data):
    """
    Format issue data with analysis for Confluence page content.
    
    Args:
        issue_data: Raw issue data
        analysis_data: Analysis data from LLM
        
    Returns:
        Formatted HTML content for Confluence
    """
    # Create HTML content for Confluence page
    html_content = []
    
    # Add issue header
    key = issue_data.get('key', '')
    summary = issue_data.get('fields', {}).get('summary', '') or issue_data.get('summary', '')
    issue_type = issue_data.get('fields', {}).get('issuetype', {}).get('name', '') or issue_data.get('issue_type', '')
    
    # Add header with issue information
    html_content.append(f"<h1>{key} - {summary}</h1>")
    html_content.append(f"<p><strong>Type:</strong> {issue_type}</p>")
    
    # Add Jira link
    jira_base_url = os.environ.get('JIRA_URL', 'https://jira.example.com')
    if jira_base_url and key:
        html_content.append(f'<p><a href="{jira_base_url}/browse/{key}">View in Jira</a></p>')
    
    html_content.append("<hr/>")
    
    # Add executive summary if available
    if analysis_data.get('executive_summary'):
        html_content.append("<h2>Executive Summary</h2>")
        html_content.append(f"<p>{analysis_data.get('executive_summary')}</p>")
    
    # Add technical summary if available
    if analysis_data.get('technical_summary'):
        html_content.append("<h2>Technical Summary</h2>")
        html_content.append(f"<p>{analysis_data.get('technical_summary')}</p>")
    
    # For bug issues, add specific fields
    if issue_type.lower() == 'bug':
        # Add cause if available
        if analysis_data.get('cause'):
            html_content.append("<h2>Cause</h2>")
            html_content.append(f"<p>{analysis_data.get('cause')}</p>")
        
        # Add fix if available
        if analysis_data.get('fix'):
            html_content.append("<h2>Fix</h2>")
            html_content.append(f"<p>{analysis_data.get('fix')}</p>")
        
        # Add impact if available
        if analysis_data.get('impact'):
            html_content.append("<h2>Impact</h2>")
            html_content.append(f"<p>{analysis_data.get('impact')}</p>")
    
    # If it's a feature/improvement/epic, add reasoning
    if analysis_data.get('reasoning'):
        html_content.append("<h2>Details</h2>")
        html_content.append(f"<p>{analysis_data.get('reasoning')}</p>")
    
    # Add categories if available
    if analysis_data.get('inferredCategories'):
        html_content.append("<h2>Categories</h2>")
        categories = analysis_data.get('inferredCategories', [])
        if isinstance(categories, str):
            # If it's a string, convert to list by splitting
            categories = [cat.strip() for cat in categories.split(',')]
        
        if categories:
            html_content.append("<ul>")
            for category in categories:
                html_content.append(f"<li>{category}</li>")
            html_content.append("</ul>")
    
    # Add confidence score if available
    if analysis_data.get('confidence'):
        html_content.append("<h2>Confidence</h2>")
        html_content.append(f"<p>AI Confidence Score: {analysis_data.get('confidence')}</p>")
    
    # Add footer
    html_content.append("<hr/>")
    html_content.append("<p><em>This page was automatically generated by AI4ReleaseNotes.</em></p>")
    
    # Join all HTML content with new lines
    return "\n".join(html_content)
