"""LLM client error types."""


class LLMError(Exception):
    """Base class for LLM client errors."""


class LLMUnavailableError(LLMError):
    """Raised when the provider is unreachable or rejects the request."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM request exceeds the configured timeout."""


class LLMParseError(LLMError):
    """Raised when structured output cannot be parsed into the target schema."""


class LLMConfigurationError(LLMError):
    """Raised when provider configuration is invalid or incomplete."""
