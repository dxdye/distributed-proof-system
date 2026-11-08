"""Ingest of a submission: fetch, build, analyse (component C1, functions F1/F2)."""

from dpc.ingest.fetch import FetchError, clone_at_commit, fetch_dependencies
from dpc.ingest.pipeline import IngestError, IngestResult, artifact_key, ingest
from dpc.ingest.submission import Submission

__all__ = [
    "FetchError",
    "IngestError",
    "IngestResult",
    "Submission",
    "artifact_key",
    "clone_at_commit",
    "fetch_dependencies",
    "ingest",
]
