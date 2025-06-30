"""
Custom exception classes for the Ai4ReleaseNotes application.
"""


class HttpUnauthorizedError(Exception):
    """Exception raised for HTTP 401 Unauthorized errors."""
    pass


class ConfigurationError(Exception):
    """Exception raised for configuration errors."""
    pass


class ApiError(Exception):
    """Exception raised for API errors."""
    pass


class JsonParsingError(Exception):
    """Exception raised for JSON parsing errors."""
    pass


class JiraFetchError(Exception):
    """Exception raised when there's an error fetching data from Jira API."""
    pass
