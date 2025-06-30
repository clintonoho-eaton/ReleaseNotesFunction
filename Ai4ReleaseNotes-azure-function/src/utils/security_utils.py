"""
SSL configuration module for disabling certificate verification.

This module contains functions to disable SSL verification globally.
Warning: Only use in development or internal environments.
"""

import ssl
import urllib3
import requests


def disable_ssl_verification():
    """
    Disable SSL verification globally for the application.
    """
    # Disable SSL verification warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Create a custom global unverified context for SSL
    ssl._create_default_https_context = ssl._create_unverified_context
    
    # Monkey patch requests to disable certificate verification
    _patch_requests_session()
    

def _patch_requests_session():
    """
    Monkey patch requests.Session to disable certificate verification.
    """
    old_merge_environment_settings = requests.Session.merge_environment_settings
    
    def merge_environment_settings(self, url, proxies, stream, verify, cert):
        settings = old_merge_environment_settings(self, url, proxies, stream, verify, cert)
        settings['verify'] = False
        return settings
        
    requests.Session.merge_environment_settings = merge_environment_settings
