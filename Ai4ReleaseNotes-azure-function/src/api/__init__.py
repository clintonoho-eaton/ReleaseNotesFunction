"""
API package for the Ai4ReleaseNotes application.

This package contains the API routes and server functionality.
"""

from src.api.extension_routes import app as extension_routes_app

__all__ = ["extension_routes_app"]
