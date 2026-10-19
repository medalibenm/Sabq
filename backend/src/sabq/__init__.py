"""Sabq (سبق): news radar for newsrooms."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sabq")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0"
