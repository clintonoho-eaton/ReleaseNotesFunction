"""
Data models for Jira issue analysis.

This module defines the data structures used for analyzing different types of Jira issues.
"""

from typing import List
from pydantic import BaseModel


class JiraIssueAnalysis(BaseModel):
    """Output model for any non-bug or non-epic Jira issue."""
    visibility: str = ""
    probabilityRanking: int = 0
    confidenceRange: str = ""
    inferredCategories: List[str] = []
    keywords: List[str] = []
    envrionments: List[str] = []  # Environments where the issue is relevant
    reasoning: str = ""


class JiraBugAnalysis(BaseModel):
    """Output model for a bug Jira issue."""
    ticket_number: str = ""
    visibility: str = ""
    executive_summary: str = ""
    technical_summary: str = ""
    cause: str = ""
    fix: str = ""
    reasoning: str = ""


class JiraEpicAnalysis(BaseModel):
    """Output model for an epic Jira issue."""
    executive_summary: str = ""
    technical_summary: str = ""
    inferredCategories: List[str] = []
    keywords: List[str] = []
    child_issues: List[str] = []  # References to the child issues


class JiraCompAnalysis(BaseModel):
    """Output model to compare Jira issues with GitHub commits."""
    consistency_score: float = 0 
    consistency_reasoning: str = ""
