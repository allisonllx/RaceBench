"""Pipeline package — re-exports aggregation API."""
from pipeline.aggregate import summarize
from pipeline.text import summarize_text

__all__ = ["summarize", "summarize_text"]
