"""Custom exception classes for URL filtering functionality."""


class URLFilteringError(Exception):
    """Base exception for URL filtering operations."""


class CSVProcessingError(URLFilteringError):
    """Exception raised when CSV processing fails."""


class ValidationError(URLFilteringError):
    """Exception raised when data validation fails."""


class FirewallAPIError(URLFilteringError):
    """Exception raised when firewall API operations fail."""


class CategoryNotFoundError(URLFilteringError):
    """Exception raised when a category is not found."""


class RuleGroupError(URLFilteringError):
    """Exception raised when rule group operations fail."""


class PolicyError(URLFilteringError):
    """Exception raised when policy operations fail."""


class AnalyticsError(URLFilteringError):
    """Exception raised when analytics processing fails."""
