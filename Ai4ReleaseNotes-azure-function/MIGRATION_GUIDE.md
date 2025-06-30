# Flask to Azure Functions Migration Guide

This document provides guidance on how this application was migrated from a Flask web application to an Azure Functions application using the v2 programming model with blueprints.

## Key Components of the Migration

### 1. Project Structure

**Flask Structure**:
```
run.py (main entry point)
src/
  api/
    api_server.py (Flask routes and app creation)
    extension_routes.py (additional routes)
  config/
  jira/
  utils/
```

**Azure Functions Structure**:
```
function_app.py (main entry point)
function_blueprints/
  release_notes_blueprint.py
  healthcheck_blueprint.py
  test_blueprint.py
  diagnostics_blueprint.py
src/
  config/
  jira/
  utils/
```

### 2. Entry Point Changes

**Flask Entry Point (run.py)**:
```python
app = create_app()
app.run(debug=True, host="0.0.0.0")
```

**Azure Functions Entry Point (function_app.py)**:
```python
app = func.FunctionApp()
app.register_blueprint(release_notes_bp)
app.register_blueprint(healthcheck_bp)
app.register_blueprint(test_bp)
app.register_blueprint(diagnostics_bp)
```

### 3. Route Definition Changes

**Flask Route**:
```python
@app.route('/release-notes/<proj>/<fixver>/<issuetype>', methods=['PUT'])
def release_notes_handler(proj: str, fixver: str, issuetype: str) -> Any:
    # Function implementation
```

**Azure Functions Route**:
```python
@release_notes_bp.route(route="release-notes/{proj}/{fixver}/{issuetype}", methods=["PUT"])
async def release_notes_handler(req: func.HttpRequest) -> func.HttpResponse:
    proj = req.route_params.get('proj')
    fixver = req.route_params.get('fixver')
    issuetype = req.route_params.get('issuetype')
    # Function implementation
```

### 4. Response Format Changes

**Flask Response**:
```python
return jsonify({"status": "success"}), 200
```

**Azure Functions Response**:
```python
return func.HttpResponse(
    body=json.dumps({"status": "success"}),
    mimetype="application/json",
    status_code=200
)
```

### 5. Configuration Changes

**Flask Configuration**: 
- Uses .env files directly
- Flask-specific configuration in app creation

**Azure Functions Configuration**:
- Uses local.settings.json for local development
- Environment variables in Azure portal/deployment
- No Flask-specific configurations

### 6. Blueprint Usage

**Flask Blueprint**:
```python
from flask import Blueprint
app = Blueprint('blueprint_name', __name__)
```

**Azure Functions Blueprint**:
```python
import azure.functions as func
blueprint_name_bp = func.Blueprint()
```

## Benefits of the Migration

1. **Serverless Architecture**: Pay only for what you use, with automatic scaling
2. **Modular Code Structure**: Better organization using Azure Functions blueprints
3. **Integration with Azure Ecosystem**: Easier integration with other Azure services
4. **Simplified Deployment**: Automated deployment through Azure Functions tooling

## Next Steps for Development

1. **Testing**: Thoroughly test all endpoints in the Azure Functions environment
2. **Authentication**: Implement Azure AD or other authentication mechanisms
3. **Monitoring**: Set up Azure Application Insights for monitoring
4. **CI/CD**: Configure GitHub Actions or Azure DevOps pipelines for continuous deployment

## Further Improvements

1. **Input Validation**: Add more robust input validation using Azure Functions input bindings
2. **Output Bindings**: Use Azure Functions output bindings to store results in Azure Storage
3. **Durable Functions**: For long-running processes, consider using Durable Functions
4. **API Management**: Consider using Azure API Management for more advanced API functionality
