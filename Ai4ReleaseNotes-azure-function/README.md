# Jira Issues Enrichment with AI  
  
This Python script enriches Jira issues by analyzing them using a large language model provided by Azure OpenAI. It fetches issues from Jira, processes them with the AI to extract relevant information, and then updates the issues with the analysis results. See ```llm_prompts.py``` for the prompts.
  
## Features  
  
- Fetch Jira issues based on a JQL query.  
- Analyze issues using Azure OpenAI's language model.  
- Enrich issues with AI-generated insights.  
- Supports different output formats like JSON, Markdown, and Excel.  
- Customizable logging.  
  
## Prerequisites  
  
Before you begin, ensure you have met the following requirements:  
- Python 3.9+ installed.  
- `pip` package manager.  
- Access to a Jira instance with an API token.  
- An Azure OpenAI key for accessing the language model.  
  
## Installation  
  
To set up the environment for the script, follow these steps:  
  
1. Clone the repository:  

2. Install the required packages:

```bash  
pip install -r requirements.txt  
 ```

## Configuration
 
1. Rename the ```.env.example``` file to ```.env```.
Fill in the environment variables in the .env file with your Azure and Jira credentials, and other configurations.
Usage
 
## Usage
 
### Basic Usage

To execute the script with default settings, run:

```bash 
python run.py  
```

This will start a Flask server that provides HTTP endpoints for generating release notes.

### HTTP Endpoints

The application provides REST endpoints for generating release notes:

```
PUT /release-notes/<project>/<fixversion>/<issuetype>
```

Example:
```
PUT /release-notes/MYPROJ/1.0/Bug
```

### Custom Issue Limits

You can also specify a custom limit for the number of issues to process using the endpoint:

```
PUT /release-notes/<project>/<fixversion>/<issuetype>/<max_results>
```

Example:
```
PUT /release-notes/MYPROJ/1.0/Bug/5
```

This will process only 5 bugs from the project.

### SSL Verification

By default, SSL verification is enabled for security. However, in some environments (like development or testing), you may need to disable it. You can do this by setting the environment variable in your `.env` file:

```
ATLASSIAN_SSL_VERIFY=false
```

### Programmatic Usage

The application can also be used programmatically. Example scripts are provided in the `examples` directory:

#### Process with Custom Limit

```bash
python examples/run_with_custom_limit.py "MYPROJ" "1.0" "Bug" 5
```

#### Process Multiple Issue Types

```bash
python examples/process_multiple_types.py "MYPROJ" "1.0"
```

This will process different issue types with custom limits for each type.

#### Batch Process Release Notes

```bash
python examples/batch_process_release_notes.py "MYPROJ" "1.0"
```

This demonstrates an optimized approach to batch process multiple issue types using the new Config utility methods.

## Output
 
The script will output enriched Jira issues in the formats specified by file_types_to_save in the config. It can save the enriched issues in JSON, Markdown, and Excel formats.

## Contributing
 
Contributions are welcome! Please feel free to submit a pull request or create an issue for any bugs or enhancements.

## License
 
TBD

## Contact
 
If you have any questions or feedback, please contact the project maintainers.

## Acknowledgements
Thanks to Azure OpenAI for providing the AI language model.
Thanks to LangChain for the Jira API Wrapper and other dependencies that make this project possible.