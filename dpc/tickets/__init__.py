"""Tickets and reviews (interface I-3), class-A ticket generation (SR-05, SR-33)."""

from dpc.tickets.difficulty import StaticFeatures, static_difficulty, static_features
from dpc.tickets.generate import CoverageError, check_coverage, class_a_tickets
from dpc.tickets.model import AIAssistance, Evidence, PaperRef, Review, Ticket

__all__ = [
    "AIAssistance",
    "CoverageError",
    "Evidence",
    "PaperRef",
    "Review",
    "StaticFeatures",
    "Ticket",
    "check_coverage",
    "class_a_tickets",
    "static_difficulty",
    "static_features",
]
