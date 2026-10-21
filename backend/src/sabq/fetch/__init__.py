"""Polite HTTP fetching (plan M3). See `sabq.fetch.client` for the rules."""

from sabq.fetch.client import (
    BackingOff,
    EgressUnavailable,
    Fetcher,
    FetchError,
    FetchResult,
    ResponseTooLarge,
    RobotsDisallowed,
    RobotsUnavailable,
)
from sabq.fetch.robots import RobotsRules

__all__ = [
    "BackingOff",
    "EgressUnavailable",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "ResponseTooLarge",
    "RobotsDisallowed",
    "RobotsRules",
    "RobotsUnavailable",
]
