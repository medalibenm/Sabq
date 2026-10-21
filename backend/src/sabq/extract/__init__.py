"""Config-driven extraction (plan M4). See `sabq.extract.config` for the config format."""

from sabq.extract.config import SourceConfig
from sabq.extract.extractor import (
    ExtractedItem,
    ExtractError,
    ListingResult,
    extract_listing,
    merge_listings,
)
from sabq.extract.urls import canonical_url_key

__all__ = [
    "ExtractError",
    "ExtractedItem",
    "ListingResult",
    "SourceConfig",
    "canonical_url_key",
    "extract_listing",
    "merge_listings",
]
