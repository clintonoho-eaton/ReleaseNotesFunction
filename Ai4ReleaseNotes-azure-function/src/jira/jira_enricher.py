import re
import os
import json
import logging
import asyncio
import time
from typing import Any, Dict, Optional, Union

import semantic_kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from src.jira.jira_client import JiraAPIWrapper
from src.models.jira_models import JiraIssueAnalysis, JiraBugAnalysis, JiraEpicAnalysis
from src.utils.file_utils import normalize_issue_data, create_file_path, save_issues_to_file, format_issue
from src.exceptions.api_exceptions import HttpUnauthorizedError, JiraFetchError



class JiraEnricher:
    """
    Enrich Jira issues by fetching them via Jira API, analyzing with Azure OpenAI, and saving results.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize kernel and services."""
        self.config = config
        self.kernel = semantic_kernel.Kernel()
        
        try:
            logging.info("Initializing Azure OpenAI service...")
            
            # Handle model-specific configuration adjustments
            self._adjust_config_for_model()
            
            # Validate required configuration
            azure_config_keys = [
                "azure_openai_key", 
                "azure_openai_gpt_deployment",
                "azure_openai_endpoint", 
                "azure_openai_chat_completions_api_version"
            ]
            
            for key in azure_config_keys:
                if not self.config.get(key):
                    raise ValueError(f"Missing required Azure OpenAI configuration: {key}")
            
            # Configure Azure OpenAI service
            service_params = {
                "service_id": "Chat",
                "api_key": self.config["azure_openai_key"],
                "deployment_name": self.config["azure_openai_gpt_deployment"],
                "endpoint": self.config["azure_openai_endpoint"],
                "api_version": self.config["azure_openai_chat_completions_api_version"]
            }
            
            # For o4-mini we need to ensure parameters are correctly set
            # but we don't need to include model_id as the deployment name is sufficient
            
            self.kernel.add_service(AzureChatCompletion(**service_params))
            logging.info("Azure OpenAI service initialized successfully")
            
        except Exception as e:
            logging.error(f"Failed to initialize Azure OpenAI service: {str(e)}")
            raise RuntimeError(f"Azure OpenAI initialization failed: {str(e)}")
        
        # Load plugins from semantic_kernel/ReleaseNotes directory
        try:
            logging.info("Loading ReleaseNotes plugins...")
            release_notes_plugin = self.kernel.add_plugin(parent_directory='./plugins/semantic_kernel', plugin_name='ReleaseNotes')
            
            # Verify plugin functions exist
            if "Bug" not in release_notes_plugin:
                raise ValueError("Bug function not found in ReleaseNotes plugin")
            if "Issue" not in release_notes_plugin:
                raise ValueError("Issue function not found in ReleaseNotes plugin") 
            if "Epic" not in release_notes_plugin:
                raise ValueError("Epic function not found in ReleaseNotes plugin")
                
            self.bugFunction = release_notes_plugin["Bug"]
            self.issueFunction = release_notes_plugin["Issue"]
            self.epicFunction = release_notes_plugin["Epic"]
            logging.info("ReleaseNotes plugins loaded successfully")
            
        except Exception as e:
            logging.error(f"Failed to load ReleaseNotes plugins: {str(e)}")
            raise RuntimeError(f"Plugin initialization failed: {str(e)}")

    def _adjust_config_for_model(self) -> None:
        """Adjust configuration parameters based on the specific model being used."""
        deployment = self.config.get("azure_openai_gpt_deployment", "")
        logging.info(f"Adjusting configuration for model: {deployment}")
        
        # Handle o4-mini model specific requirements
        if deployment == "o4-mini":
            # Ensure the correct API version
            if self.config.get("azure_openai_chat_completions_api_version") != "2024-12-01-preview":
                logging.warning("Setting correct API version for o4-mini model")
                self.config["azure_openai_chat_completions_api_version"] = "2024-12-01-preview"
            
            # Log the configuration for debugging
            logging.info(f"Using API version: {self.config.get('azure_openai_chat_completions_api_version')}")
            
            # For o4-mini, we need to use max_completion_tokens instead of max_tokens
            # This is handled in config.json for plugins and in the analyze_issue_with_ai method
            logging.info("Note: Using max_completion_tokens instead of max_tokens for o4-mini")
            
            # Check for any max_tokens in the config and convert them
            if 'max_tokens' in self.config:
                logging.warning("Converting max_tokens to max_completion_tokens in config")
                self.config['max_completion_tokens'] = self.config.pop('max_tokens')
            
            # For o4-mini, adjust temperature parameter - this model only supports default (1.0)
            if 'temperature' in self.config and self.config['temperature'] != 1.0:
                logging.warning("Setting temperature to 1.0 for o4-mini compatibility")
                self.config['temperature'] = 1.0
                
            logging.info("Note: o4-mini only supports default temperature (1.0)")

    async def analyze_issue_with_ai(
        self,
        issue_data: Dict[str, Any],
        is_type: str = "",
    ) -> Optional[Union[JiraIssueAnalysis, JiraEpicAnalysis, JiraBugAnalysis]]:
        """
        Call Azure OpenAI to analyze a Jira issue and return typed analysis.

        Retries on transient errors with exponential backoff.
        """
        inp = json.dumps(issue_data)
        schema_cls = {
            'bug': JiraBugAnalysis,
            'epic': JiraEpicAnalysis,
        }.get(is_type.lower(), JiraIssueAnalysis)

        func = {
            'bug': self.bugFunction,
            'epic': self.epicFunction,
        }.get(is_type.lower(), self.issueFunction)

        # Increased max attempts for better resilience
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            try:
                logging.info("Calling Azure OpenAI for issue type '%s' (attempt %d/%d)...", 
                             is_type, attempt + 1, max_attempts)
                start = time.time()
                
                # Create an instance of the model class with the issue data
                model_instance = schema_cls(**issue_data)
                output_schema = model_instance.model_dump()
                
                # Add more debug information
                logging.debug("Invoking model with schema: %s", 
                             type(output_schema).__name__)
                
                # Invoke the model with a timeout to prevent hanging
                try:
                    # Create a more explicit prompt that enforces JSON output
                    prompt_additions = {
                        "json_only": True,
                        "response_format": {"type": "json_object"},
                        "format_instructions": "Respond with a valid JSON object only, with no additional text."
                    }
                    
                    # Add the correct token parameter based on the model
                    # o4-mini requires max_completion_tokens instead of max_tokens
                    if self.config["azure_openai_gpt_deployment"] == "o4-mini":
                        if "max_tokens" in prompt_additions:
                            logging.warning("Converting max_tokens to max_completion_tokens for o4-mini model")
                            prompt_additions["max_completion_tokens"] = prompt_additions.pop("max_tokens")
                        else:
                            prompt_additions["max_completion_tokens"] = 1000  # Set a reasonable default
                            
                        # o4-mini only supports default temperature (1.0)
                        if "temperature" in prompt_additions and prompt_additions["temperature"] != 1.0:
                            logging.warning("Setting temperature to 1.0 for o4-mini model")
                            prompt_additions["temperature"] = 1.0
                    
                    result = await asyncio.wait_for(
                        self.kernel.invoke(
                            func,
                            issue_type=is_type.lower(),
                            issue_info=inp,
                            output_schema=json.dumps(output_schema),  # Convert to JSON string
                            **prompt_additions  # Add explicit JSON formatting instructions
                        ), 
                        timeout=60  # 60 second timeout
                    )
                except asyncio.TimeoutError:
                    logging.error("Azure OpenAI call timed out after 60 seconds")
                    attempt += 1
                    backoff = 2 ** attempt
                    await asyncio.sleep(backoff)
                    continue
                except Exception as e:
                    # Check for specific API parameter errors
                    error_msg = str(e)
                    if "unsupported_parameter" in error_msg or "unsupported_value" in error_msg:
                        logging.error(f"Model parameter error: {error_msg}")
                        if "temperature" in error_msg:
                            logging.warning("Adjusting temperature parameter")
                            # Force temperature to 1.0 for o4-mini compatibility
                            prompt_additions["temperature"] = 1.0
                        elif "max_tokens" in error_msg:
                            logging.warning("Converting max_tokens to max_completion_tokens")
                            if "max_tokens" in prompt_additions:
                                prompt_additions["max_completion_tokens"] = prompt_additions.pop("max_tokens")
                            else:
                                prompt_additions["max_completion_tokens"] = 1000
                        
                        # Remove any unsupported parameters mentioned in the error
                        for param in ["top_p", "presence_penalty", "frequency_penalty"]:
                            if param in error_msg and param in prompt_additions:
                                logging.warning(f"Removing unsupported parameter: {param}")
                                prompt_additions.pop(param)
                        
                        # Other parameter adjustments can be added here
                        attempt += 1
                        continue
                    else:
                        # Re-raise unexpected errors
                        logging.error(f"Unexpected error in Azure OpenAI call: {error_msg}")
                        raise
                
                # Verify result structure
                if not result or not hasattr(result, 'value') or not result.value:
                    logging.error("Azure OpenAI returned empty or invalid result structure")
                    raise ValueError("Invalid result structure from Azure OpenAI")
                
                # Access the function result
                result_str = result.value[0].content
                # Log the raw response
                logging.debug("Raw response from Azure OpenAI: %s", result_str[:500])  # Log first 500 chars
                
                # Log the raw response for debugging
                logging.debug("Raw response before extraction: %s", result_str[:500])
                
                # Extract JSON from response - handle case where model outputs text before the JSON
                json_content = self._extract_json_from_text(result_str)
                if not json_content:
                    logging.error("Failed to extract valid JSON from the response")
                    raise ValueError("No valid JSON found in the response")
                
                try:
                    # Parse the extracted JSON
                    analysis = schema_cls.model_validate_json(json_content)
                    logging.info(
                        "Azure OpenAI call SUCCEEDED in %.2fs", time.time() - start
                    )
                    return analysis
                except json.JSONDecodeError as json_err:
                    logging.error("JSON parsing error: %s", json_err)
                    logging.error("Invalid JSON result: %s", json_content[:200])
                    raise ValueError(f"Invalid JSON response from Azure OpenAI: {json_err}")
                except Exception as validation_err:
                    logging.error("Model validation error: %s", validation_err)
                    raise ValueError(f"Model validation error: {validation_err}")

            except HttpUnauthorizedError:
                logging.error("Azure OpenAI returned 401 Unauthorized - API key may be invalid")
                raise  # Re-raise authentication errors
                
            except ValueError as ve:
                logging.error("Value error in OpenAI processing: %s", ve)
                # Try the next attempt
                
            except Exception as e:
                code = getattr(e, 'status_code', None)
                if code == 401 or '401' in str(e):
                    logging.error("Azure OpenAI returned 401 Unauthorized")
                    raise HttpUnauthorizedError from e

                logging.warning(
                    "Azure OpenAI call FAILED on attempt %d/%d: %s", 
                    attempt + 1, max_attempts, e
                )
                
                # Try to get more error details
                if hasattr(e, 'response'):
                    try:
                        logging.error("Response details: %s", e.response.text)
                    except:
                        pass
                
                if hasattr(e, 'llm_output'):
                    try:
                        normalized = normalize_issue_data(e.llm_output)
                        return schema_cls(**normalized)
                    except Exception as norm_err:
                        logging.error("Error normalizing LLM output: %s", norm_err)

            # Exponential backoff
            attempt += 1
            if attempt < max_attempts:
                backoff = 2 ** attempt
                logging.info("Retrying after %ds...", backoff)
                await asyncio.sleep(backoff)

        logging.error("Azure OpenAI call ultimately failed after %d attempts.", max_attempts)
        return None

    async def add_ai_analysis_to_issue(self, issue: Dict[str, Any]) -> bool:
        """
        Enrich a single issue dict in-place with AI analysis and additional metadata.
        
        Returns:
            bool: True if enrichment was successful, False otherwise
        """
        keys = ['key', 'summary', 'description', 'priority', 'components', 'comments', 'imgURLs']
        if issue.get('issuetype', '').lower() == 'epic':
            keys += ['children', 'parent']
        snippet = {k: issue.get(k) for k in keys}
        logging.debug("Issue snippet: %s", json.dumps(snippet)[:200])

        result = await self.analyze_issue_with_ai(snippet, is_type=issue.get('issuetype', ''))
        if not result:
            logging.error("No AI result for %s, skipping.", issue.get('key'))
            # Mark issue as not enriched
            issue['ai_enriched'] = False
            return False

        # Add AI fields to the issue
        for field in result.model_fields:
            issue[field] = getattr(result, field)

        # Clean up ticket number if matches pattern
        if re.match(r"IP-\d+", issue.get('ticket_number', '')):
            issue['ticket_number'] = ''

        issue['browsable_url'] = f"{self.config['jira_url']}/browse/{issue['key']}"
        # Mark issue as successfully enriched
        issue['ai_enriched'] = True
        logging.info("Enriched issue %s successfully.", issue['key'])
        return True

    def _has_meaningful_content(self, issue: Dict[str, Any]) -> bool:
        """
        Check if an issue has meaningful content from the AI enrichment.
        
        Args:
            issue: The issue dictionary
            
        Returns:
            bool: True if the issue has meaningful AI-generated content
        """
        # Check issue type and validate required fields
        issue_type = issue.get('issuetype', '').lower()
        
        # Check for empty or default values in key fields
        if issue_type == 'bug':
            # For bugs, check technical and executive summaries
            tech_summary = issue.get('technical_summary', '')
            exec_summary = issue.get('executive_summary', '')
            cause = issue.get('cause', '')
            fix = issue.get('fix', '')
            
            # Require at least technical summary and either cause or fix
            return bool(tech_summary.strip() and (cause.strip() or fix.strip()))
            
        elif issue_type == 'epic':
            # For epics, check both summaries
            tech_summary = issue.get('technical_summary', '')
            exec_summary = issue.get('executive_summary', '')
            
            # Require at least one summary
            return bool(tech_summary.strip() or exec_summary.strip())
            
        else:
            # For other types, check confidence and reasoning
            reasoning = issue.get('reasoning', '')
            categories = issue.get('inferredCategories', [])
            
            # Require reasoning and at least one category
            return bool(reasoning.strip() and categories)

    async def fetch_and_analyze_issues(self) -> Dict[str, Any]:
        """
        Fetch issues from Jira, enrich them concurrently, and persist results.
        
        Returns:
            Dict[str, Any]: A dictionary with status information, processing time,
            details, and any warning messages.
        """
        start_time = time.time()
        
        # Initialize result tracking
        result = {
            "status": "success",
            "processing_time": 0,
            "details": [],
            "warnings": []
        }
        
        logging.info(f"Starting fetch_and_analyze_issues for JQL: {self.config.get('jql')}")
        logging.info(f"Using max_results: {self.config.get('max_results')}")
        logging.info(f"Issue type: {self.config.get('jira_issue_type')}")
        
        # Create a simple JiraAPIWrapper instance
        # SSL verification is already disabled globally at the app level
        try:
            jira_wrapper = JiraAPIWrapper(
                jira_username=self.config['jira_username'],
                jira_api_token=self.config['jira_api_key'],
                jira_instance_url=self.config['jira_url']
            )
            
            logging.info("JiraAPIWrapper created successfully")
            logging.info("Using SSL-disabled connections for Jira and Confluence API calls")
        except Exception as e:
            logging.error(f"Error creating JiraAPIWrapper: {str(e)}")
            raise JiraFetchError(f"Error creating JiraAPIWrapper: {str(e)}")
        
        try:
            logging.info(f"Executing search with JQL: {self.config['jql']} and max_results: {self.config['max_results']}")
            issues_raw = jira_wrapper.search(self.config['jql'], max_results=self.config['max_results'])
            logging.info(f"Search completed successfully. Raw result size: {len(str(issues_raw))}")
            
            parsed = jira_wrapper.parse_issues(issues_raw)
            logging.info(f"Issues parsed successfully")
            
            # Check if any issues were found
            if not parsed:
                logging.warning(f"No issues found for JQL: {self.config['jql']}")
                logging.warning(f"JQL configuration: max_results={self.config['max_results']}, issue_type={self.config.get('jira_issue_type')}")
                return  # Return early if no issues were found
                
            logging.info(f"Found {len(parsed)} issues for JQL: {self.config['jql']}")
            # Log the keys of the found issues for debugging
            issue_keys = [issue.get('key', 'Unknown') for issue in parsed]
            logging.info(f"Issue keys: {', '.join(issue_keys)}")
            
        except Exception as e:
            logging.error(f"Error fetching or parsing issues: {str(e)}", exc_info=True)  # Include stack trace
            raise JiraFetchError(f"Error fetching or parsing issues: {str(e)}")

        # Optionally save raw data in DEBUG mode
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            path = create_file_path('jql', self.config['jql'])
            # Use default issue type if not specified in config
            jira_issue_type = self.config.get('jira_issue_type', 'Issue')
            save_issues_to_file(parsed, path, 'json', jira_issue_type)

        # Enrich issues and collect results
        enrichment_results = await asyncio.gather(*(self.add_ai_analysis_to_issue(issue) for issue in parsed))
        
        # Count successful enrichments
        successful_enrichments = sum(1 for result in enrichment_results if result)
        logging.info(f"Successfully enriched {successful_enrichments} out of {len(parsed)} issues")
        
        if successful_enrichments == 0:
            logging.error("No issues were successfully enriched with AI content. Check Azure OpenAI connectivity.")

        # Persist enriched data based on configuration
        create_local_files = self.config.get('create_local_files', True)
        create_confluence_pages = self.config.get('create_confluence_pages', False)
        
        # Create local files if configured
        if create_local_files:
            # Check if file_path exists in config, use a default if not
            file_path = self.config.get('file_path')
            if file_path is None:
                import os
                # Use default output directory based on issue type
                file_path = os.path.join('output', 'UNKNOWN', self.config.get('release_version', 'unknown'))
                logging.warning(f"No file_path specified in config, using default: {file_path}")
                # Make sure directory exists
                os.makedirs(file_path, exist_ok=True)
            
            enriched_path = create_file_path(
                file_path, 'ai_enriched_jql', self.config['jql']
            )
            logging.info(f"Creating local files in {enriched_path}")
            
            # Check if file_types_to_save exists in config, use defaults if not
            file_types_to_save = self.config.get('file_types_to_save', ['json'])
            
            # Check if jira_issue_type exists in config, use a default if not
            jira_issue_type = self.config.get('jira_issue_type', 'Issue')
            if jira_issue_type is None or jira_issue_type == '':
                jira_issue_type = 'Issue'
                logging.warning(f"No jira_issue_type specified in config, using default: {jira_issue_type}")
            
            if 'xlsx' in file_types_to_save:
                save_issues_to_file(parsed, enriched_path, 'xlsx', jira_issue_type)
                logging.info(f"Saved Excel file for {jira_issue_type} issues")
                
            if 'json' in file_types_to_save:
                save_issues_to_file(parsed, enriched_path, 'json', jira_issue_type)
                logging.info(f"Saved JSON file for {jira_issue_type} issues")
                
            if 'md' in file_types_to_save:
                save_issues_to_file(parsed, enriched_path, 'md', jira_issue_type)
                logging.info(f"Saved Markdown file for {jira_issue_type} issues")
        
        # Create Confluence pages if configured
        if create_confluence_pages:
            # Initialize counters for Confluence page creation
            confluence_success = 0
            confluence_skipped = 0
            confluence_errors = []
            confluence_duplicates = 0
            
            # Try to get parent page ID from various configuration options
            # Force using the value from the .env file
            parent_id = os.environ.get('CONFLUENCE_PARENT_ID') or self.config.get('confluence_parent_id') or self.config.get('confluence_parent_page_id')
            logging.info(f"Using Confluence parent page ID: {parent_id} (from environment or config)")
            
            # Get Confluence space key
            confluence_space = self.config.get('confluence_space') or self.config.get('confluence_space_key')
            
            # Also check if Confluence URL is available
            confluence_url = self.config.get('confluence_url') or self.config.get('confluence_base_url')
            
            missing_configs = []
            if not confluence_space:
                missing_configs.append("confluence_space or confluence_space_key")
            if not parent_id:
                missing_configs.append("confluence_parent_id or confluence_parent_page_id")
            if not confluence_url:
                missing_configs.append("confluence_url or confluence_base_url")
            
            if missing_configs:
                missing_str = ", ".join(missing_configs)
                logging.error(f"Missing required configuration: {missing_str}. Confluence page creation aborted.")
                create_confluence_pages = False
            else:
                logging.info(f"Using Confluence space: {confluence_space}, parent ID: {parent_id}")
                
            if create_confluence_pages:
                logging.info("Processing issues for Confluence page creation...")
            for issue in parsed:
                # Only create Confluence pages for issues that were successfully enriched with AI content
                if issue.get('ai_enriched', False):
                    # Additional check to ensure we have meaningful content
                    has_content = self._has_meaningful_content(issue)
                    if has_content:
                        # Generate properly formatted Confluence content
                        try:
                            # Extract AI analysis data from the issue to pass to format_issue
                            analysis_data = {}
                            # Copy AI enriched fields to analysis_data
                            for field in ['executive_summary', 'technical_summary', 'reasoning', 
                                         'cause', 'fix', 'impact', 'inferredCategories', 
                                         'confidence', 'ticket_number']:
                                if field in issue:
                                    analysis_data[field] = issue[field]
                            
                            # Call format_issue with both required arguments
                            body = format_issue(issue, analysis_data)
                            
                            # Validate that the body has actual content
                            if not body or len(body.strip()) < 50:
                                logging.error(f"Generated body content for {issue['key']} is empty or too short. Skipping page creation.")
                                confluence_skipped += 1
                                continue
                            
                            # Create the page title with fix version first, then issue key and summary
                            # Get the first fix version (if available)
                            fix_version = issue.get('fixVersions', [''])[0] if issue.get('fixVersions') else ''
                            
                            # Format title with fix version first
                            if fix_version:
                                title = f"{fix_version} - {issue['key']} - {issue.get('summary', 'Release Notes')}"
                            else:
                                title = f"{issue['key']} - {issue.get('summary', 'Release Notes')}"
                                
                            # Truncate if too long
                            if len(title) > 100:  # Avoid excessively long page titles
                                if fix_version:
                                    title = f"{fix_version} - {issue['key']} Release Notes"
                                else:
                                    title = f"{issue['key']} Release Notes"
                            
                            logging.info(f"Creating Confluence page for {issue['key']}")
                            
                            # Log body length for debugging
                            body_length = len(body) if body else 0
                            logging.info(f"Body content length: {body_length} characters")
                            
                            # Create the page using the already verified space and parent parameters
                            # Log the page creation parameters for debugging
                            logging.info(f"Creating page \"{confluence_space}\" -> \"{title}\"")
                            
                            # Log the exact parent_id that will be used with an obvious marker
                            logging.info(f"###PARENT_ID_DEBUG### Using parent_id: {parent_id} for Confluence page creation")
                            logging.info(f"###PARENT_ID_SOURCE### From env: {os.environ.get('CONFLUENCE_PARENT_ID')}, from config: {self.config.get('confluence_parent_id')}")
                            
                            # FORCE parent_id to always be the environment variable value
                            final_parent_id = os.environ.get('CONFLUENCE_PARENT_ID')
                            if final_parent_id != parent_id:
                                logging.warning(f"###PARENT_ID_OVERRIDE### Overriding parent_id from {parent_id} to {final_parent_id} (from env)")
                                parent_id = final_parent_id
                            
                            page_data = {
                                "space": confluence_space,
                                "title": title,
                                "body": body,
                                "parent_id": parent_id,
                                "type": "page"
                                # Note: Labels will be added after page creation if needed
                            }
                            
                            # Additional debug logging to confirm the data being sent
                            logging.debug(f"Confluence page data - space: {confluence_space}, parent_id: {parent_id}, title: {title[:50]}...")
                            
                            # Log first 200 chars of body for debugging (only in debug level)
                            if body and len(body) > 0:
                                preview = body[:200] + "..." if len(body) > 200 else body
                                logging.debug(f"Body content preview: {preview}")
                            
                            # Initialize error tracking variables
                            confluence_error = False
                            error_message = ""
                            
                            try:
                                # Call the page_create method
                                response = jira_wrapper.page_create(json.dumps(page_data))
                                
                                # Check if the response indicates an error
                                if isinstance(response, dict) and response.get('error'):
                                    error_msg = response.get('error')
                                    logging.error(f"Error creating Confluence page: {error_msg}")
                                    # Instead of raising an exception, we'll set a flag and continue
                                    confluence_error = True
                                    error_message = error_msg
                                    
                                    # Check if it's a duplicate page error
                                    if "already exists" in error_msg.lower():
                                        confluence_duplicates += 1
                                        # Record this as a warning rather than an error
                                        logging.warning(f"Duplicate page detected: {error_msg}")
                                        confluence_errors.append(f"Page '{title}' already exists in space '{confluence_space}'")
                                    else:
                                        # Add to error list for non-duplicate errors
                                        confluence_errors.append(error_msg)
                                else:
                                    confluence_error = False
                            except Exception as access_error:
                                confluence_error = True
                                if "permission" in str(access_error).lower():
                                    error_message = f"Permission error accessing Confluence space '{confluence_space}'"
                                    logging.error(f"{error_message}: {access_error}")
                                elif "Not Found" in str(access_error) or "404" in str(access_error):
                                    error_message = f"Space '{confluence_space}' not found. Check if the space key is correct."
                                    logging.error(error_message)
                                elif "parent_id" in str(access_error).lower():
                                    error_message = f"Invalid parent page ID: '{parent_id}'. Check if the parent page ID is correct."
                                    logging.error(error_message)
                                else:
                                    # Log the error with more context but don't raise an exception
                                    error_message = f"Confluence error: {str(access_error)}"
                                    logging.error(f"Error creating Confluence page: {access_error}")
                            
                            # If there was an error in the try block, skip the rest of the processing
                            if confluence_error:
                                continue
                            
                            # Check response for success
                            if not confluence_error and isinstance(response, dict) and (response.get('id') or response.get('success')):
                                confluence_success += 1
                                page_id = response.get('id', '')
                                
                                # # Try to add labels separately using our custom method
                                # try:
                                #     # Add labels one by one
                                #     labels = [
                                #         "release-notes",
                                #         issue['key'].split('-')[0],  # Project key
                                #         issue.get('issuetype', '').lower()
                                #     ]
                                #     for label in labels:
                                #         success = jira_wrapper.add_label(page_id, label)
                                #         if not success:
                                #             logging.warning(f"Failed to add label '{label}' to page {page_id}")
                                # except Exception as e:
                                #     logging.warning(f"Could not add labels to page: {str(e)}")
                                
                                # Construct the proper Confluence page URL
                                confluence_base_url = self.config.get('confluence_base_url', '')
                                # If we got a URL directly in the response, use that instead
                                if response.get('url'):
                                    page_url = response.get('url')
                                else:
                                    page_url = f"{confluence_base_url}{page_id}"
                                logging.info(f"Successfully created page: {page_url}")
                            elif not confluence_error:
                                logging.warning(f"Received unexpected response when creating page: {response}")
                                
                        except Exception as e:
                            logging.error(f"Error creating Confluence page for {issue['key']}: {str(e)}")
                            # Log the full exception for troubleshooting
                            import traceback
                            logging.debug(f"Full exception details: {traceback.format_exc()}")
                    else:
                        confluence_skipped += 1
                        logging.warning(f"Skipping Confluence page creation for {issue['key']} due to insufficient AI content")
                else:
                    confluence_skipped += 1
            
            # Track Confluence results in our status
            confluence_status = f"Created {confluence_success} Confluence pages, skipped {confluence_skipped} pages"
            logging.info(confluence_status)
            result["details"].append(confluence_status)
            
            # Track any errors with Confluence pages
            if confluence_errors:
                for error_msg in confluence_errors:
                    result["warnings"].append(f"Confluence error: {error_msg}")
            
            if confluence_success == 0 and confluence_skipped > 0:
                warning_msg = "No Confluence pages were created. Check AI enrichment quality."
                logging.warning(warning_msg)
                result["warnings"].append(warning_msg)
                
            # If there were duplicate page errors, include that information
            if confluence_duplicates > 0:
                duplicate_msg = f"Found {confluence_duplicates} existing pages with the same titles"
                logging.info(duplicate_msg)
                result["details"].append(duplicate_msg)
                
        elif self.config.get('file_types_to_save') and 'conf' in self.config.get('file_types_to_save', []) and not create_confluence_pages:
            # Check the specific reason why Confluence pages weren't created
            if not self.config.get('confluence_space') and not self.config.get('confluence_space_key'):
                warning_msg = "Skipping Confluence page creation (missing required configuration: confluence_space or confluence_space_key)"
                logging.warning(warning_msg)
                result["warnings"].append(warning_msg)
            elif not self.config.get('confluence_parent_id') and not self.config.get('confluence_parent_page_id'):
                warning_msg = "Skipping Confluence page creation (missing required configuration: confluence_parent_id or confluence_parent_page_id)"
                logging.warning(warning_msg)
                result["warnings"].append(warning_msg)
            else:
                info_msg = "Skipping Confluence page creation (CREATE_CONFLUENCE_PAGES is not enabled)"
                logging.info(info_msg)
                result["details"].append(info_msg)

        # Add details about successful processing
        jql_info = f"Processing completed successfully in {time.time() - start_time:.2f} seconds for JQL: {self.config.get('jql')}"
        logging.info(jql_info)
        result["details"].append(jql_info)

        # Update result with final processing time
        result["processing_time"] = time.time() - start_time
        
        return result

    def _extract_json_from_text(self, text: str) -> str:
        """
        Extract JSON from text that may contain explanatory text before or after the JSON block.
        
        Args:
            text: The text potentially containing JSON
            
        Returns:
            str: The extracted JSON string or empty string if no valid JSON found
        """
        # First try to extract JSON from markdown code blocks
        json_pattern = r'```(?:json)?\s*([\s\S]*?)```'
        matches = re.findall(json_pattern, text)
        
        # If found in code blocks, validate each match
        for match in matches:
            cleaned_json = match.strip()
            try:
                # Validate it's proper JSON
                json.loads(cleaned_json)
                return cleaned_json
            except json.JSONDecodeError:
                continue  # Try next match

        # If no valid JSON found in code blocks, try to find JSON between curly braces
        # This is more aggressive but needed as a fallback
        try:
            # Find the first { and the last } that could form a complete JSON object
            start_idx = text.find('{')
            if start_idx >= 0:
                # Count braces to find matching closing brace
                brace_count = 0
                in_string = False
                escape_next = False
                
                for i in range(start_idx, len(text)):
                    char = text[i]
                    
                    # Handle string literals properly
                    if char == '"' and not escape_next:
                        in_string = not in_string
                    elif char == '\\' and in_string and not escape_next:
                        escape_next = True
                        continue
                    
                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                # Found a potential complete JSON object
                                potential_json = text[start_idx:i+1]
                                try:
                                    # Validate it's proper JSON
                                    json.loads(potential_json)
                                    return potential_json
                                except json.JSONDecodeError:
                                    # Keep looking for another complete JSON object
                                    pass
                    
                    escape_next = False
        except Exception as e:
            logging.error(f"Error while trying to extract JSON by braces: {e}")

        # Last resort: try to clean up the text and see if it's valid JSON
        cleaned_text = text.strip()
        if cleaned_text.startswith('{') and cleaned_text.endswith('}'):
            try:
                json.loads(cleaned_text)
                return cleaned_text
            except json.JSONDecodeError:
                pass
                
        logging.error("Could not extract valid JSON from text")
        # Log a sample of what we received to help diagnose issues
        logging.debug("Text sample: %s", text[:200])
        return ""