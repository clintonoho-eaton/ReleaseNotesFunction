"""
Jira API wrapper for interacting with Jira.

This module provides utilities to interact with the Jira API.
"""

from typing import Any, Dict, List, Optional
import re
import os

from pydantic import BaseModel, model_validator
from langchain_core.utils import get_from_dict_or_env
import requests
import logging
import json
from urllib3.exceptions import InsecureRequestWarning
from src.exceptions.api_exceptions import HttpUnauthorizedError, JiraFetchError

# Suppress only the InsecureRequestWarning from urllib3
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class JiraAPIWrapper(BaseModel):
    """Wrapper for Jira API."""

    jira: Any = None  #: :meta private:
    confluence: Any = None
    jira_username: Optional[str] = None
    jira_api_token: Optional[str] = None
    jira_instance_url: Optional[str] = None
    confluence_username: Optional[str] = None
    confluence_api_token: Optional[str] = None
    confluence_instance_url: Optional[str] = None
    
    class CustomConfluenceClient:
        """Custom Confluence client implementation using REST API."""
        
        def __init__(self, wrapper, instance_url, username, api_token):
            """Initialize the Confluence client with the given credentials."""
            self.wrapper = wrapper
            self.instance_url = instance_url
            self.username = username
            self.api_token = api_token
            self.auth = (username, api_token)
        
        def get_space(self, space_key):
            """Get a Confluence space by key."""
            logging.debug(f"Getting Confluence space: {space_key}")
            
            # Get space URL
            space_url = f"{self.instance_url}/wiki/rest/api/space/{space_key}"
            
            # Make request with auth
            response = requests.get(space_url, auth=self.auth, verify=False)
            
            # Check response status
            if response.status_code == 200:
                # Parse JSON response
                result = response.json()
                logging.info(f"Found Confluence space: {result.get('name', space_key)}")
                return result
            elif response.status_code == 401:
                # Unauthorized
                error_msg = "Unauthorized access to Confluence API. Check your credentials."
                logging.error(error_msg)
                raise HttpUnauthorizedError(error_msg)
            elif response.status_code == 404:
                # Space not found
                error_msg = f"Confluence space not found: {space_key}"
                logging.error(error_msg)
                return None
            else:
                # Other error
                error_msg = f"Error fetching Confluence space: {response.status_code} - {response.text}"
                logging.error(error_msg)
                return None
                
        def get_page_by_id(self, page_id):
            """Get a Confluence page by ID."""
            logging.debug(f"Getting Confluence page by ID: {page_id} (type: {type(page_id)})")
            
            # Ensure page_id is properly formatted for the API request
            page_id_str = str(page_id).strip()  # Convert to string and trim whitespace
            logging.info(f"Using page_id_str: '{page_id_str}' for API request")
            
            # Get page URL
            page_url = f"{self.instance_url}/wiki/rest/api/content/{page_id_str}"
            
            # Make request with auth
            response = requests.get(page_url, auth=self.auth, verify=False)
            
            # Check response status
            if response.status_code == 200:
                # Parse JSON response
                result = response.json()
                logging.info(f"Found Confluence page: {result.get('title', 'Unknown')}")
                return result
            elif response.status_code == 401:
                # Unauthorized
                error_msg = "Unauthorized access to Confluence API. Check your credentials."
                logging.error(error_msg)
                raise HttpUnauthorizedError(error_msg)
            else:
                # Other error
                error_msg = f"Error fetching Confluence page: {response.status_code} - {response.text}"
                logging.error(error_msg)
                return None
                
        def get_page_by_title(self, space, title):
            """Get a Confluence page by title in a space."""
            logging.debug(f"Getting Confluence page by title: {title} in space {space}")
            
            # Get page URL
            page_url = f"{self.instance_url}/wiki/rest/api/content"
            
            # Prepare request parameters
            params = {
                "spaceKey": space,
                "title": title,
                "expand": "version"
            }
            
            # Make request with auth
            response = requests.get(page_url, params=params, auth=self.auth, verify=False)
            
            # Check response status
            if response.status_code == 200:
                # Parse JSON response
                result = response.json()
                pages = result.get('results', [])
                if pages:
                    logging.info(f"Found Confluence page: {title}")
                    return pages[0]
                else:
                    logging.info(f"No Confluence page found with title: {title}")
                    return None
            else:
                # Error
                error_msg = f"Error fetching Confluence page: {response.status_code} - {response.text}"
                logging.error(error_msg)
                return None
                
        def create_page(self, space, title, body, parent_id=None, representation="storage"):
            """Create a new Confluence page."""
            logging.debug(f"Creating Confluence page: {title} in space {space}")
            
            # Get page URL
            page_url = f"{self.instance_url}/wiki/rest/api/content"
            
            # Validate parameters
            if not space:
                error_msg = "Missing required parameter 'space'"
                logging.error(error_msg)
                return {"error": error_msg, "status": "failed"}
                
            if not title:
                error_msg = "Missing required parameter 'title'"
                logging.error(error_msg)
                return {"error": error_msg, "status": "failed"}
                
            if not body:
                error_msg = "Missing required parameter 'body'"
                logging.error(error_msg)
                return {"error": error_msg, "status": "failed"}
            
            # Prepare request data
            data = {
                "type": "page",
                "title": title,
                "space": {"key": space},
                "body": {
                    "storage": {
                        "value": body,
                        "representation": representation
                    }
                }
            }
            
            # Add parent ID if provided
            if parent_id:
                try:
                    # Try to convert to integer if it's a string
                    if isinstance(parent_id, str) and parent_id.isdigit():
                        parent_id_int = int(parent_id)
                        data["ancestors"] = [{"id": parent_id_int}]
                    else:
                        data["ancestors"] = [{"id": parent_id}]
                except (ValueError, TypeError):
                    logging.warning(f"Invalid parent_id format: {parent_id}, using as is")
                    data["ancestors"] = [{"id": parent_id}]
            
            # Make request with auth
            try:
                headers = {"Content-Type": "application/json"}
                response = requests.post(page_url, json=data, headers=headers, auth=self.auth, verify=False, timeout=30)
                
                # Check response status
                if response.status_code in (200, 201):
                    # Parse JSON response
                    result = response.json()
                    page_id = result.get('id', 'unknown')
                    logging.info(f"Created Confluence page: {title} with ID: {page_id}")
                    return result
                else:
                    # Error with file name in log
                    error_msg = f"Error creating Confluence page in CustomConfluenceClient.create_page(): {response.status_code} - {response.text}"
                    logging.error(error_msg)
                    
                    # Check for specific error codes
                    if response.status_code == 401:
                        return {"error": "Unauthorized: Invalid Confluence credentials", "status": "failed"}
                    elif response.status_code == 404:
                        return {"error": f"Space '{space}' not found", "status": "failed"}
                    elif response.status_code == 403:
                        return {"error": f"Permission denied for space '{space}'", "status": "failed"}
                    elif response.status_code == 400 and "title already exists" in response.text.lower():
                        error_detail = f"Page with title '{title}' already exists in space '{space}'"
                        logging.error(error_detail)
                        return {"error": error_detail, "status": "failed"}
                    else:
                        return {"error": error_msg, "status": "failed"}
            except requests.exceptions.RequestException as e:
                error_msg = f"Connection error creating Confluence page: {str(e)}"
                logging.error(error_msg)
                return {"error": error_msg, "status": "failed"}
                
        def update_page(self, page_id, title, body, version=None, representation="storage"):
            """Update an existing Confluence page."""
            logging.debug(f"Updating Confluence page: {page_id}")
            
            # Get page URL
            page_url = f"{self.instance_url}/wiki/rest/api/content/{page_id}"
            
            # If version is not provided, try to get it first
            if version is None:
                try:
                    page_info = self.get_page_by_id(page_id)
                    if page_info and 'version' in page_info:
                        version = page_info.get('version', {}).get('number', 0)
                        logging.info(f"Retrieved page version: {version}")
                    else:
                        logging.warning(f"Could not retrieve page version for {page_id}. Using version 1.")
                        version = 1
                except Exception as e:
                    logging.error(f"Error getting page version: {str(e)}. Using version 1.")
                    version = 1
            
            # Prepare request data
            data = {
                "version": {"number": int(version) + 1},
                "title": title,
                "type": "page",
                "body": {
                    "storage": {
                        "value": body,
                        "representation": representation
                    }
                }
            }
            
            # Make request with auth
            try:
                headers = {"Content-Type": "application/json"}
                response = requests.put(page_url, json=data, headers=headers, auth=self.auth, verify=False, timeout=30)
                
                # Check response status
                if response.status_code == 200:
                    # Parse JSON response
                    result = response.json()
                    logging.info(f"Updated Confluence page: {title}")
                    return result
                else:
                    # Error
                    error_msg = f"Error updating Confluence page: {response.status_code} - {response.text}"
                    logging.error(error_msg)
                    
                    # Check for specific error codes
                    if response.status_code == 401:
                        return {"error": "Unauthorized: Invalid Confluence credentials", "status": "failed"}
                    elif response.status_code == 404:
                        return {"error": f"Page with ID {page_id} not found", "status": "failed"}
                    elif response.status_code == 403:
                        return {"error": f"Permission denied for page {page_id}", "status": "failed"}
                    elif response.status_code == 409:
                        return {"error": f"Version conflict: Page has been modified by another user", "status": "failed"}
                    else:
                        return {"error": error_msg, "status": "failed"}
            except requests.exceptions.RequestException as e:
                error_msg = f"Connection error updating Confluence page: {str(e)}"
                logging.error(error_msg)
                return {"error": error_msg, "status": "failed"}
    
    @model_validator(mode='after')
    def validate_environment(self) -> 'JiraAPIWrapper':
        """Validate that api key and python package exists in environment."""
        jira_username = get_from_dict_or_env(
            dict(self), "jira_username", "ATLASSIAN_USERNAME", ""
        )
        jira_api_token = get_from_dict_or_env(
            dict(self), "jira_api_token", "ATLASSIAN_API_KEY", ""
        )
        jira_instance_url = get_from_dict_or_env(
            dict(self), "jira_instance_url", "ATLASSIAN_URL", ""
        )
        
        # Set the Confluence values if not explicitly provided
        confluence_username = get_from_dict_or_env(
            dict(self), "confluence_username", "CONFLUENCE_USERNAME", ""
        ) or jira_username
        
        confluence_api_token = get_from_dict_or_env(
            dict(self), "confluence_api_token", "CONFLUENCE_API_KEY", ""
        ) or jira_api_token
        
        confluence_instance_url = get_from_dict_or_env(
            dict(self), "confluence_instance_url", "CONFLUENCE_URL", ""
        )
        
        # If no Confluence URL is provided, use JIRA URL and check for /wiki endpoint
        if not confluence_instance_url and jira_instance_url:
            # If JIRA URL ends with /jira, replace with /wiki
            if jira_instance_url.endswith('/jira'):
                confluence_instance_url = jira_instance_url.replace('/jira', '/wiki')
            # For Atlassian cloud, they may be the same base URL
            elif 'atlassian.net' in jira_instance_url:
                confluence_instance_url = jira_instance_url
            # Otherwise, assume it's the same base URL
            else:
                confluence_instance_url = jira_instance_url
        
        object.__setattr__(self, "jira_username", jira_username)
        object.__setattr__(self, "jira_api_token", jira_api_token)
        object.__setattr__(self, "jira_instance_url", jira_instance_url)
        object.__setattr__(self, "confluence_username", confluence_username)
        object.__setattr__(self, "confluence_api_token", confluence_api_token)
        object.__setattr__(self, "confluence_instance_url", confluence_instance_url)
        
        return self
    
    class CustomJiraClient:
        """Custom JIRA client implementation using REST API."""
        
        def __init__(self, wrapper):
            self.wrapper = wrapper
            
        def jql(self, query, limit=10, startAt=0):
            """Execute a JQL query using the REST API."""
            logging.debug(f"Executing JQL query with CustomJiraClient: {query}")
            
            # Get JQL search URL
            search_url = f"{self.wrapper.jira_instance_url}/rest/api/2/search"
            
            # Prepare request parameters
            params = {
                "jql": query,
                "maxResults": limit,
                "startAt": startAt,
                # Fetch all fields by default
                "fields": "*all"
            }
            
            # Make request with auth
            auth = (self.wrapper.jira_username, self.wrapper.jira_api_token)
            response = requests.get(search_url, params=params, auth=auth, verify=False)
            
            # Check response status
            if response.status_code == 200:
                # Parse JSON response
                result = response.json()
                logging.info(f"Found {len(result.get('issues', []))} issues for JQL query")
                return result
            elif response.status_code == 401:
                # Unauthorized
                error_msg = "Unauthorized access to Jira API. Check your credentials."
                logging.error(error_msg)
                raise HttpUnauthorizedError(error_msg)
            else:
                # Other error
                error_msg = f"Error fetching issues: {response.status_code} - {response.text}"
                logging.error(error_msg)
                raise JiraFetchError(error_msg)
        
        def projects(self):
            """Get all projects using the REST API."""
            logging.debug("Getting projects with CustomJiraClient")
            
            # Get projects URL
            projects_url = f"{self.wrapper.jira_instance_url}/rest/api/2/project"
            
            # Make request with auth
            auth = (self.wrapper.jira_username, self.wrapper.jira_api_token)
            response = requests.get(projects_url, auth=auth, verify=False)
            
            # Check response status
            if response.status_code == 200:
                # Parse JSON response
                result = response.json()
                logging.info(f"Found {len(result)} projects")
                return result
            elif response.status_code == 401:
                # Unauthorized
                error_msg = "Unauthorized access to Jira API. Check your credentials."
                logging.error(error_msg)
                raise HttpUnauthorizedError(error_msg)
            else:
                # Other error
                error_msg = f"Error fetching projects: {response.status_code} - {response.text}"
                logging.error(error_msg)
                raise JiraFetchError(error_msg)
        
        def issue_create(self, fields):
            """Create an issue using the REST API."""
            logging.debug("Creating issue with CustomJiraClient")
            
            # Get issue create URL
            create_url = f"{self.wrapper.jira_instance_url}/rest/api/2/issue"
            
            # Prepare request body
            body = {
                "fields": fields
            }
            
            # Make request with auth
            auth = (self.wrapper.jira_username, self.wrapper.jira_api_token)
            response = requests.post(
                create_url, 
                json=body, 
                auth=auth, 
                verify=False, 
                headers={"Content-Type": "application/json"}
            )
            
            # Check response status
            if response.status_code in (200, 201):
                # Parse JSON response
                result = response.json()
                logging.info(f"Created issue: {result.get('key')}")
                return result
            elif response.status_code == 401:
                # Unauthorized
                error_msg = "Unauthorized access to Jira API. Check your credentials."
                logging.error(error_msg)
                raise HttpUnauthorizedError(error_msg)
            else:
                # Other error
                error_msg = f"Error creating issue: {response.status_code} - {response.text}"
                logging.error(error_msg)
                raise JiraFetchError(error_msg)
    
    def initialize_jira_client(self):
        """Initialize the JIRA client if it is not already initialized."""
        if self.jira is None:
            if not self.jira_instance_url or not self.jira_username or not self.jira_api_token:
                raise ValueError("JIRA credentials or instance URL are missing.")

            try:
                # Create a custom JIRA client using our REST API implementation
                self.jira = self.CustomJiraClient(self)
                logging.info("Custom JIRA client initialized successfully")
            except Exception as e:
                logging.error(f"Failed to initialize custom JIRA client: {str(e)}")
                raise
                
    def initialize_confluence_client(self):
        """Initialize the Confluence client if it is not already initialized.
        
        Returns:
            bool: True if initialization was successful, False if required config is missing
        
        Raises:
            Exception: If initialization fails with an unexpected error
        """
        if self.confluence is None:
            # For Confluence, we'll use the same credentials as JIRA by default if not explicitly provided
            confluence_username = self.confluence_username or self.jira_username
            confluence_api_token = self.confluence_api_token or self.jira_api_token
            
            # For the Confluence instance URL, we need to determine it from the JIRA URL if not provided
            confluence_instance_url = self.confluence_instance_url
            if not confluence_instance_url and self.jira_instance_url:
                # Typically, if JIRA URL is https://company.atlassian.net then Confluence is the same
                confluence_instance_url = self.jira_instance_url
                
            # Before trying to initialize, log what we're using
            logging.info(f"Initializing Confluence client with URL: {confluence_instance_url}")
            
            # Check if we have the minimum required configuration
            missing_configs = []
            if not confluence_instance_url:
                missing_configs.append("Confluence instance URL")
            if not confluence_username:
                missing_configs.append("Confluence username")
            if not confluence_api_token:
                missing_configs.append("Confluence API token")
                
            if missing_configs:
                missing_str = ", ".join(missing_configs)
                logging.error(f"Cannot initialize Confluence client. Missing required configuration: {missing_str}")
                self.confluence = None  # Ensure it's set to None in case of missing configs
                return False

            try:
                # Create a CustomConfluenceClient similar to our CustomJiraClient
                # This will implement the Confluence REST API methods we need
                self.confluence = self.CustomConfluenceClient(self, 
                                                            confluence_instance_url,
                                                            confluence_username,
                                                            confluence_api_token)
                logging.info("Custom Confluence client initialized successfully")
                return True
            except Exception as e:
                logging.error(f"Failed to initialize custom Confluence client: {str(e)}")
                self.confluence = None  # Ensure it's set to None in case of exception
                return False  # Return False instead of raising, to make the method more robust
        
        # Client already initialized
        return True

    def test_connection(self) -> bool:
        """Test connection to Jira API."""
        try:
            # Get JQL search URL
            search_url = f"{self.jira_instance_url}/rest/api/2/myself"
            
            # Make request with auth
            auth = (self.jira_username, self.jira_api_token)
            response = requests.get(search_url, auth=auth, verify=False)
            
            # Check response status
            if response.status_code == 200:
                # Success
                return True
            elif response.status_code == 401:
                # Unauthorized
                logging.error("Unauthorized access to Jira API. Check your credentials.")
                return False
            else:
                # Other error
                logging.error(f"Error connecting to Jira API: {response.status_code}")
                return False
        except Exception as e:
            logging.error(f"Error testing connection to Jira API: {str(e)}")
            return False
            
    def run_jql_search(self, jql: str, max_results: int = 10, 
                       fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Run a JQL search query against the Jira API.
        
        Args:
            jql: The JQL query to run
            max_results: Maximum number of results to return
            fields: List of fields to include in the response
            
        Returns:
            List of issues from the JQL search
        """
        try:
            logging.info(f"Running JQL search: {jql}")
            
            # Initialize JIRA client if needed
            self.initialize_jira_client()
            
            # Execute the JQL query using custom client
            result = self.jira.jql(query=jql, limit=max_results)
            
            # Return just the issues array
            if "issues" in result:
                return result.get("issues", [])
            return []
                
        except HttpUnauthorizedError:
            # Re-raise unauthorized errors
            raise
        except Exception as e:
            # Log and re-raise other errors
            logging.error(f"Error running JQL search: {str(e)}")
            raise JiraFetchError(f"Error running JQL search: {str(e)}")
            
    # parsing issues from jira issues
    def parse_issues(self, issues: Dict) -> List[dict]:
        import logging
        
        # Input validation
        if not issues or not isinstance(issues, dict) or "issues" not in issues:
            logging.error("Invalid input to parse_issues: missing 'issues' key or not a dictionary")
            return []
        
        # Log the number of issues to parse
        issue_count = len(issues["issues"])
        logging.info(f"Parsing {issue_count} issues from Jira response")
        
        if issue_count == 0:
            logging.warning("No issues found to parse")
            return []
        
        #remove references to users
        patterns_to_remove = [  
            r"\[~accountid:[^\]]+\]"
         ]  
        # collected parsed issues
        parsed = []  
        
        for issue_idx, issue in enumerate(issues["issues"]):
            try:
                key = issue["key"]  
                logging.debug(f"Parsing issue {key} ({issue_idx + 1}/{issue_count})")
                
                summary = issue["fields"]["summary"]  
                created = issue["fields"]["created"][0:10]  
                priority = issue["fields"]["priority"]["name"]  
                status = issue["fields"]["status"]["name"]  
                id = issue["id"]  
                description = issue["fields"].get("description", "")  
                issuetype = issue["fields"]["issuetype"]["name"]  

                wsjf = None
                if issuetype.lower() == "epic":
                    wsjf = issue["fields"].get("customfield_12918", None) #wsjf field
                reporter = issue["fields"]["reporter"]["displayName"]  
                
                imgURLs = []
                for attach in issue["fields"].get("attachment", [])  : #collect image urls
                    imgURLs.append(attach["content"])

                # collect parent id
                try:
                    parent = issue["fields"]["parent"][0:10] 
                except Exception:
                    parent = "None"

                labels = issue['fields'].get('labels', [])

                fixVersions = [version["name"] for version in issue["fields"].get("fixVersions", [])]  
                comments = []  

                # parse and collect comment details
                for comment in issue["fields"].get("comment", {}).get("comments", []):
                    comment_body = comment.get("body", "")  
                    # Remove the specified patterns from the comment body
                    for pattern in patterns_to_remove:  
                        comment_body = re.sub(pattern, '', comment_body) 
                    comments.append({  
                        "body": comment_body,  
                        "author": comment["author"]["displayName"],  
                        "created": comment["created"]  
                    })  

                components = [component["name"] for component in issue["fields"].get("components", [])] 

                try:  
                    assignee = issue["fields"]["assignee"]["displayName"]  
                except Exception:  
                    assignee = "None"  
        
                # inward issues link to the current issues. outwards issues are linked from the current issue
                rel_issues = {}  
                for related_issue in issue["fields"].get("issuelinks", []):  
                    if "inwardIssue" in related_issue.keys():  
                        rel_type = related_issue["type"]["inward"]  
                        rel_key = related_issue["inwardIssue"]["key"]  
                        rel_summary = related_issue["inwardIssue"]["fields"]["summary"]  
                    if "outwardIssue" in related_issue.keys():  
                        rel_type = related_issue["type"]["outward"]  
                        rel_key = related_issue["outwardIssue"]["key"]  
                        rel_summary = related_issue["outwardIssue"]["fields"]["summary"]  
                    rel_issues = {"type": rel_type, "key": rel_key, "summary": rel_summary}  

                # collect all parsed details
                parsed.append({  
                    "key": key,  
                    "summary": summary,  
                    "created": created,  
                    "assignee": assignee,  
                    "priority": priority,
                    "status": status,  
                    "description": description,  
                    "id": id,  
                    "issuetype": issuetype,  
                    "components": components,  
                    "comments": comments,  
                    "related_issues": rel_issues,  
                    "fixVersions": fixVersions, 
                    "reporter": reporter,  
                    "labels": labels,  
                    "wsjf": wsjf,  
                    "imgURLs": imgURLs,  
                    "parent": parent
                })
            except Exception as e:
                logging.error(f"Error parsing issue at index {issue_idx}: {str(e)}")
                # Continue with next issue instead of failing
        
        logging.info(f"Successfully parsed {len(parsed)} issues")
        return parsed 

    # parse child issues into simpler snapshots
    def parse_childs(self, childs: Dict) -> List[dict]:  
        parsed = []  
        for child in childs["issues"]:
            key = child["key"]
            summary = child["fields"]["summary"]
            description = child["fields"].get("description", "")
            parsed.append(
                {"key": key, "summary": summary, "description": description}
            )
        return parsed


    # parse projects
    def parse_projects(self, projects: List[dict]) -> List[dict]:
        parsed = []
        for project in projects:
            id = project["id"]
            key = project["key"]
            name = project["name"]
            type = project["projectTypeKey"]
            style = project["style"]
            parsed.append(
                {"id": id, "key": key, "name": name, "type": type, "style": style}
            )
        return parsed

    # execute jql and return up to the max results
    def search_new(self, query: str, max_results: int = 10) -> list:  
        all_issues = []  
        start_at = 0  
        
        # Initialize JIRA client if needed
        self.initialize_jira_client()
        
        while True:  
            #execute jql
            response = self.jira.jql(query, limit=max_results, startAt=start_at)  
            self.jira #unsure if necessary
            issues = response['issues']  
            total = response['total']  
            max_results = response['maxResults']  
    
            # Append the issues from the current batch to the all_issues list  
            all_issues.extend(issues)  
    
            # Calculate the next starting index for the query  
            start_at += max_results  
    
            # If the number of issues fetched so far is equal to or greater than the total, stop fetching  
            if start_at >= total:  
                break  
            
        return all_issues  

    # search which just executes the jql statement
    def search(self, query: str, max_results: int = 10) -> str:  
        try:
            import logging
            logging.info(f"Executing Jira JQL query: {query}")
            logging.info(f"Maximum results requested: {max_results}")
            
            # Initialize JIRA client if needed
            self.initialize_jira_client()
                
            logging.info(f"Jira API URL: {self.jira_instance_url}")
            
            # Detailed debug logging before the actual call
            logging.debug("About to call JIRA API with the following parameters:")
            logging.debug(f"- JQL Query: {query}")
            logging.debug(f"- Max Results: {max_results}")
            logging.debug(f"- Username: {self.jira_username}")
            logging.debug(f"- URL: {self.jira_instance_url}")
            
            # Execute the JQL query
            issues = self.jira.jql(query, limit=max_results)  
            
            # Log the number of issues found
            if issues and "issues" in issues:
                issue_count = len(issues["issues"])
                logging.info(f"Found {issue_count} issues matching query")
                
                # Additional validation for empty results
                if issue_count == 0:
                    logging.warning(f"No issues found for JQL query: {query}")
                else:
                    # Log the first few issue keys for debugging
                    issue_keys = [issue.get("key", "Unknown") for issue in issues["issues"][:5]]
                    logging.info(f"First few issue keys: {', '.join(issue_keys)}")
            else:
                logging.warning(f"Unexpected response format from Jira API for query: {query}")
                logging.debug(f"Response structure: {type(issues).__name__}")
                if issues:
                    logging.debug(f"Response keys: {list(issues.keys()) if isinstance(issues, dict) else 'Not a dictionary'}")
            
            return issues
        except Exception as e:
            import logging
            logging.error(f"JIRA search exception: {str(e)}", exc_info=True)  # Include complete stack trace
            logging.error(f"Error executing Jira JQL query: {str(e)}")
            
            from src.exceptions.api_exceptions import JiraFetchError, HttpUnauthorizedError
            if "401" in str(e):
                raise HttpUnauthorizedError(f"Unauthorized: {str(e)}")
            else:
                raise JiraFetchError(f"Failed to fetch Jira issues: {str(e)}")  

    # search which executes jql and attempts to parse all results then format as output
    def search_oldest(self, query: str) -> str:
        # Initialize JIRA client if needed
        self.initialize_jira_client()
        
        issues = self.jira.jql(query)
        parsed_issues = self.parse_issues(issues)
        parsed_issues_str = (
            "Found " + str(len(parsed_issues)) + " issues:\n" + str(parsed_issues)
        )
        return parsed_issues_str

    # search to pull jql projects and parse
    def project(self) -> str:
        # Initialize JIRA client if needed
        self.initialize_jira_client()
        
        projects = self.jira.projects()
        parsed_projects = self.parse_projects(projects)
        parsed_projects_str = (
            "Found " + str(len(parsed_projects)) + " projects:\n" + str(parsed_projects)
        )
        return parsed_projects_str

    # create Jira issue
    def issue_create(self, query: str) -> str:
        try:
            import json
            
            # Initialize JIRA client if needed
            self.initialize_jira_client()
        except ImportError:
            raise ImportError(
                "json is not installed. Please install it with `pip install json`"
            )
        params = json.loads(query)
        return self.jira.issue_create(fields=dict(params))

    # create confluence page
    def page_create(self, query: str) -> Dict[str, Any]: #includes update functionality
        try:
            import json
            import logging
            import inspect
            from datetime import datetime
            
            # Get caller information for better logging
            caller_frame = inspect.currentframe().f_back
            if caller_frame:
                caller_info = f"{caller_frame.f_code.co_filename}:{caller_frame.f_lineno}"
            else:
                caller_info = "unknown"
            logging.info(f"JiraAPIWrapper.page_create() called from {caller_info}")
        except ImportError:
            error_msg = "json or required libraries are not installed."
            return {"error": error_msg, "status": "failed"}
            
        # Initialize Confluence client if needed
        try:
            client_initialized = self.initialize_confluence_client()
            if not client_initialized:
                error_msg = "Cannot create Confluence page: missing required configuration"
                logging.error(error_msg)
                return {"error": error_msg, "status": "failed"}
        except Exception as e:
            # If Confluence client initialization fails with an exception
            error_msg = f"Cannot create Confluence page: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg, "status": "failed"}
            
        # Double-check that we have a valid Confluence client (should never happen if initialization returned True)
        if self.confluence is None:
            error_msg = "Confluence client is not initialized"
            logging.error(error_msg)
            return {"error": error_msg, "status": "failed"}
            
        try:
            params = json.loads(query)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON parameters: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg, "status": "failed"}
        
        # Log the parameters for troubleshooting, excluding body to keep log manageable
        debug_params = dict(params)
        if 'body' in debug_params:
            debug_params['body'] = f"[Content length: {len(debug_params['body'])} chars]"
        logging.debug(f"Confluence page params: {debug_params}")
        
        # Ensure we have the correct parameters format expected by the Confluence API
        space_key = params.get('space')
        title = params.get('title')
        body = params.get('body')
        parent_id = params.get('parent_id')
        
        # Validate required parameters
        missing_params = []
        if not space_key:
            missing_params.append("'space'")
        if not title:
            missing_params.append("'title'")
        if not body:
            missing_params.append("'body'")
            
        if missing_params:
            error_msg = f"Missing required parameter(s): {', '.join(missing_params)}"
            logging.error(error_msg)
            return {"error": error_msg, "status": "failed"}
        
        logging.info(f"Creating/updating page: '{title}' in space: '{space_key}' with parent_id: {parent_id}")
        logging.info(f"###CLIENT_PARENT_ID### Parent ID received in page_create: {parent_id}")
        
        try: #if new page
            # Construct parameters for the create_page method
            create_params = {
                "space": space_key,
                "title": title,
                "body": body
            }
            
            # Only add parent_id if it exists and is not None
            # The parent_id parameter needs to be passed as-is to the create_page method
            # which internally transforms it to the "ancestors" format for the REST API
            if parent_id:
                # FORCE OVERRIDE to the correct parent ID (temporary fix)
                env_parent_id = os.environ.get('CONFLUENCE_PARENT_ID')
                if env_parent_id and env_parent_id != parent_id:
                    logging.warning(f"###PARENT_ID_OVERRIDE### Overriding parent_id from {parent_id} to {env_parent_id} (from env)")
                    parent_id = env_parent_id
                
                logging.info(f"###FINAL_PARENT_ID### Using parent_id: {parent_id} (type: {type(parent_id)})")
                try:
                    # First check if it's already an integer string
                    if isinstance(parent_id, str) and parent_id.isdigit():
                        parent_id_int = int(parent_id)
                        create_params["parent_id"] = parent_id_int
                        logging.info(f"Converted parent_id to integer: {parent_id_int}")
                    else:
                        # If not a pure integer, use as is
                        create_params["parent_id"] = parent_id
                        logging.info(f"Using parent_id as is: {parent_id}")
                except ValueError:
                    logging.warning(f"Invalid parent_id format: '{parent_id}', must be an integer. Using without conversion.")
                    create_params["parent_id"] = parent_id
                
            # First verify that the space exists and is accessible
            try:
                space_info = self.confluence.get_space(space_key)
                if not space_info:
                    error_msg = f"Space '{space_key}' does not exist or is not accessible"
                    logging.error(error_msg)
                    return {"error": error_msg, "status": "failed"}
                logging.info(f"Verified access to Confluence space: {space_key}")
            except Exception as space_error:
                error_msg = f"Error accessing space '{space_key}': {str(space_error)}"
                logging.error(error_msg)
                if "permission" in str(space_error).lower():
                    return {"error": f"Permission error: You do not have access to space '{space_key}'", "status": "failed"}
                return {"error": error_msg, "status": "failed"}
                
            # If parent_id is specified, check it exists
            if parent_id:
                try:
                    logging.info(f"Attempting to verify parent page with ID: {parent_id}")
                    
                    # Try converting to integer if it's a string digit
                    parent_id_to_check = parent_id
                    if isinstance(parent_id, str) and parent_id.isdigit():
                        parent_id_to_check = int(parent_id)
                        logging.info(f"Converted parent_id to integer for verification: {parent_id_to_check}")
                    
                    parent_page = self.confluence.get_page_by_id(parent_id_to_check)
                    if not parent_page:
                        error_msg = f"Parent page with ID {parent_id} does not exist or is not accessible"
                        logging.error(error_msg)
                        return {"error": error_msg, "status": "failed"}
                    
                    # Log the parent page information for debugging
                    if isinstance(parent_page, dict):
                        parent_title = parent_page.get('title', 'Unknown')
                        parent_space = parent_page.get('space', {}).get('key', 'Unknown')
                        logging.info(f"Verified access to parent page: {parent_id}, Title: '{parent_title}', Space: '{parent_space}'")
                    else:
                        logging.info(f"Verified access to parent page: {parent_id}, but received unexpected format: {type(parent_page)}")
                except Exception as parent_error:
                    error_msg = f"Error accessing parent page {parent_id}: {str(parent_error)}"
                    logging.error(error_msg)
                    if "permission" in str(parent_error).lower():
                        return {"error": f"Permission error: You do not have access to parent page {parent_id}", "status": "failed"}
                    # Try one more time with the original format if conversion was attempted
                    if isinstance(parent_id, str) and parent_id.isdigit() and isinstance(parent_id_to_check, int):
                        try:
                            logging.info(f"Retrying with original string format: {parent_id}")
                            parent_page = self.confluence.get_page_by_id(parent_id)
                            if parent_page:
                                logging.info(f"Successfully verified parent page using string format: {parent_id}")
                                # Update the format for the create_params
                                create_params["parent_id"] = parent_id
                                return True
                        except Exception:
                            pass  # Continue with the error if this also fails
                    return {"error": error_msg, "status": "failed"}
                
            logging.info(f"Attempting to create new page with params: {create_params.keys()}")
            try:
                logging.info(f"Calling self.confluence.create_page() with params: space={space_key}, title={title}, parent_id={parent_id if parent_id else 'None'}")
                result = self.confluence.create_page(**create_params)
                logging.info(f"Create page successful: {result}")
                return result
            except Exception as create_error:
                logging.error(f"Error creating page in JiraAPIWrapper.page_create(): {str(create_error)}")
                # Check for duplicate title error
                if "title already exists" in str(create_error).lower():
                    error_detail = f"Page with title '{title}' already exists in space '{space_key}'"
                    logging.error(error_detail)
                    # Instead of returning error, try to find and update the existing page
                    logging.info(f"Attempting to find and update existing page with title '{title}'")
                return {"error": f"Error creating page: {str(create_error)}", "status": "failed"}
                
        except Exception as e: #if page exists or other error
            logging.error(f"Error in create_page: {type(e).__name__}: {str(e)}")
            
            # Check for specific error types
            error_msg = str(e).lower()
            if "permission" in error_msg:
                return {"error": f"Permission denied: {str(e)}", "status": "failed"}
            elif "already exists" in error_msg:
                logging.info(f"Page '{title}' already exists in space '{space_key}'. Attempting to update (JiraAPIWrapper.page_create()).")
                
            try:
                # Try to find if the page already exists
                logging.info(f"Checking if page '{title}' exists in space '{space_key}' to update it")
                try:
                    logging.info(f"Calling self.confluence.get_page_by_title() with space={space_key}, title={title}")
                    prevPage = self.confluence.get_page_by_title(space=space_key, title=title)
                    if prevPage:
                        logging.info(f"Found existing page with ID: {prevPage.get('id')} for title '{title}'")
                    else:
                        logging.warning(f"No page found with title '{title}' in space '{space_key}' even though creation failed with 'already exists'")
                except Exception as page_error:
                    logging.error(f"Error finding page '{title}' in JiraAPIWrapper.page_create(): {str(page_error)}")
                    return {"error": f"Error finding page '{title}': {str(page_error)}", "status": "failed"}
                
                # Check if the page was found
                if not prevPage:
                    logging.error(f"Can't find '{title}' page in space '{space_key}'!")
                    
                    # If we're here, the page doesn't exist but create_page failed for another reason
                    # Try to create the page with minimal parameters
                    logging.info("Retrying with minimal parameters (no parent_id)...")
                    try:
                        # Generate a unique title to avoid conflicts
                        unique_title = f"{title} - {datetime.now().strftime('%Y%m%d-%H%M%S')}"
                        logging.info(f"Using unique title for retry: '{unique_title}'")
                        
                        result = self.confluence.create_page(
                            space=space_key,
                            title=unique_title,
                            body=body
                        )
                        logging.info("Retry create page successful with unique title")
                        return result
                    except Exception as retry_error:
                        logging.error(f"Retry create page failed in JiraAPIWrapper.page_create(): {str(retry_error)}")
                        if "title already exists" in str(retry_error).lower():
                            return {"error": f"Cannot create page: title '{title}' already exists in space '{space_key}'", "status": "failed"}
                        return {"error": f"Retry create page failed: {str(retry_error)}", "status": "failed"}
                    
                # If we found the page, update it
                page_id = prevPage.get('id')
                if not page_id:
                    logging.error("Found page but no ID was returned")
                    return {"error": "Found page but no ID was returned", "status": "failed"}
                    
                logging.debug(f"Found existing page {page_id}, updating...")
                
                update_params = {
                    "page_id": page_id,
                    "title": title, 
                    "body": body
                }
                
                try:
                    logging.info(f"Calling self.confluence.update_page() with page_id={page_id}, title='{title}'")
                    result = self.confluence.update_page(**update_params)
                    logging.info(f"Update page successful for title '{title}': {result}")
                    return result
                except Exception as update_error:
                    logging.error(f"Error updating page '{title}' (ID: {page_id}) in JiraAPIWrapper.page_create(): {str(update_error)}")
                    # Try once more with adding a version increment manually
                    try:
                        logging.info(f"Retrying update with explicit version")
                        # Get latest version number from the page
                        current_page = self.confluence.get_page_by_id(page_id)
                        if current_page and 'version' in current_page:
                            version_number = current_page.get('version', {}).get('number', 0)
                            update_params['version'] = version_number
                            logging.info(f"Updating with explicit version: {version_number}")
                            result = self.confluence.update_page(**update_params)
                            logging.info(f"Update with explicit version successful")
                            return result
                    except Exception as retry_update_error:
                        logging.error(f"Retry update failed: {str(retry_update_error)}")
                    
                    return {"error": f"Error updating page: {str(update_error)}", "status": "failed"}
                    
            except Exception as nested_e:
                # Log the full chain of exceptions
                logging.error(f"Confluence error chain: {str(e)} -> {str(nested_e)}")
                return {"error": f"Multiple errors: {str(e)}; {str(nested_e)}", "status": "failed"}

    # execute alternative jql statemetns
    def other(self, query: str) -> str:
        try:
            import json
            
            # Initialize JIRA client if needed
            self.initialize_jira_client()
        except ImportError:
            raise ImportError(
                "json is not installed. Please install it with `pip install json`"
            )
        params = json.loads(query)
        jira_function = getattr(self.jira, params["function"])
        return jira_function(*params.get("args", []), **params.get("kwargs", {}))

    # run the jira wrapper
    def run(self, mode: str, query: str) -> str:
        if mode == "jql":
            return self.search(query)
        elif mode == "get_projects":
            return self.project()
        elif mode == "create_issue":
            return self.issue_create(query)
        elif mode == "other":
            return self.other(query)
        elif mode == "create_page":
            return self.page_create(query)
        else:
            raise ValueError(f"Got unexpected mode {mode}")
