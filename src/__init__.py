"""Minimal package metadata for mysql-data-factory."""

__version__ = "1.0.0"
__author__ = "WJC"
__email__ = "wang.jc.jp@gmail.com"

# Keep package import lightweight so scripts can import src.database
# without pulling in optional modules like faker-based generators.
__all__: list[str] = []
