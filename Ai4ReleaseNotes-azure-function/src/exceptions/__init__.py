"""
Exceptions package for Ai4ReleaseNotes application.

This package contains custom exceptions used throughout the application.
"""

from src.exceptions.api_exceptions import (
    HttpUnauthorizedError,
    ConfigurationError,
    ApiError,
    JsonParsingError,
    JiraFetchError,
)

__all__ = [
    "HttpUnauthorizedError",
    "ConfigurationError",
    "ApiError",
    "JsonParsingError",
    "JiraFetchError",
]
