"""
Blueprint for test function.
"""

import logging
import time
import json

import azure.functions as func

# Create blueprint
test_bp = func.Blueprint()

@test_bp.route(route="test", methods=["GET"])
async def test_route(req: func.HttpRequest) -> func.HttpResponse:
    """Simple test endpoint to verify Azure Functions is working."""
    logging.info("Test route called successfully")
    
    return func.HttpResponse(
        body=json.dumps({
            "status": "ok",
            "message": "Azure Functions app is running correctly",
            "timestamp": time.time(),
            "app_version": "1.0.0"
        }),
        mimetype="application/json",
        status_code=200
    )
