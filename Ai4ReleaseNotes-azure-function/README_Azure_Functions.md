# Jira Issues Enrichment with AI using Azure Functions

This application enriches Jira issues by analyzing them using a large language model provided by Azure OpenAI. It fetches issues from Jira, processes them with the AI to extract relevant information, and then updates the issues with the analysis results.

## Features

- Fetch Jira issues based on a JQL query.
- Analyze issues using Azure OpenAI's language model.
- Enrich issues with AI-generated insights.
- Supports different output formats like JSON, Markdown, and Excel.
- Customizable logging.
- Implemented as Azure Functions using the v2 programming model with blueprints for modularity.

## Prerequisites

Before you begin, ensure you have met the following requirements:
- Python 3.9+ installed.
- `pip` package manager.
- Access to a Jira instance with an API token.
- An Azure OpenAI key for accessing the language model.
- Azure Functions Core Tools installed (for local development).
- Azure CLI installed (for deployment to Azure).

## Installation

To set up the environment for the application, follow these steps:

1. Clone the repository:

2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Configuration

1. Rename the `.env.example` file to `.env` for local development outside of Azure Functions, or create a `local.settings.json` file for local Azure Functions development.
2. Fill in the environment variables with your Azure and Jira credentials, and other configurations.

### Environment Variables

Key environment variables include:

```
AZURE_OPENAI_KEY=<your-azure-openai-key>
AZURE_OPENAI_ENDPOINT=<your-azure-openai-endpoint>
AZURE_OPENAI_CHAT_COMPLETIONS_API_VERSION=<api-version>
AZURE_OPENAI_GPT_DEPLOYMENT=<deployment-name>
ATLASSIAN_URL=<your-jira-url>
ATLASSIAN_USERNAME=<your-jira-username>
ATLASSIAN_API_KEY=<your-jira-api-token>
```

## Usage

### Local Development

To run the Azure Functions app locally, use the Azure Functions Core Tools:

```bash
func start
```

This will start the Functions host and make all the HTTP endpoints available locally.

### Azure Functions Endpoints

The application provides the following HTTP endpoints:

1. Process release notes with default settings:
   ```
   PUT /api/release-notes/{project}/{fixversion}/{issuetype}
   ```
   Example: `PUT /api/release-notes/MYPROJ/1.0/Bug`

2. Process release notes with custom issue limits:
   ```
   PUT /api/release-notes/{project}/{fixversion}/{issuetype}/{max_results}
   ```
   Example: `PUT /api/release-notes/MYPROJ/1.0/Bug/5`

3. Get health status:
   ```
   GET /api/health
   ```

4. Test the Function App:
   ```
   GET /api/test
   ```

5. Diagnostics for troubleshooting:
   ```
   PUT /api/diagnostics/release-notes/{project}/{fixversion}/{issuetype}
   ```

## Azure Functions Blueprint Structure

The application uses Azure Functions v2 programming model with blueprints to organize the code in a modular way:

- `function_app.py` - Main entry point that registers all blueprints
- `function_blueprints/` - Directory containing all blueprint modules:
  - `release_notes_blueprint.py` - Blueprint for release notes endpoints
  - `healthcheck_blueprint.py` - Blueprint for health check endpoint
  - `test_blueprint.py` - Blueprint for test endpoint
  - `diagnostics_blueprint.py` - Blueprint for diagnostics endpoints

## Deployment to Azure

To deploy the function to Azure, use the Azure Functions Core Tools:

```bash
# Login to Azure
az login

# Create a resource group if needed
az group create --name MyResourceGroup --location eastus

# Create a storage account for the function
az storage account create --name mystorageaccount --location eastus --resource-group MyResourceGroup --sku Standard_LRS

# Create the function app
az functionapp create --resource-group MyResourceGroup --consumption-plan-location eastus --runtime python --runtime-version 3.9 --functions-version 4 --name my-function-app --storage-account mystorageaccount --os-type Linux

# Deploy the function app
func azure functionapp publish my-function-app
```

## Contributing

Contributions are welcome! Please feel free to submit a pull request or create an issue for any bugs or enhancements.

## License

TBD

## Contact

If you have any questions or feedback, please contact the project maintainers.

## Acknowledgements

- Thanks to Azure OpenAI for providing the AI language model.
- Thanks to LangChain for the Jira API Wrapper and other dependencies that make this project possible.
