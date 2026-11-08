"""Errors shared across layers."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """A provider failed; the orchestrator may try the next one."""


class ProviderUnavailable(ProviderError):
    """The circuit breaker is open for this provider."""


class TransientHTTPError(ProviderError):
    """A retryable HTTP response (429, 5xx)."""


class ParseError(ValueError):
    """A document could not be parsed into the domain model."""
