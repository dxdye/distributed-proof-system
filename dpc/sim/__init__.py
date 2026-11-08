"""Agent-based simulation of the review process (milestone M3).

Uses exactly the domain core of the production system (`dpc.domain`) against a
known ground truth, to verify the decision rule and the trust model (SR-11,
SR-12) and to choose parameters (h, ρ, θ_PV, θ_PVV, δ_A, k_min) before the pilot.
"""

from dpc.sim.model import ReviewerType, SimConfig, SimResult, simulate

__all__ = ["ReviewerType", "SimConfig", "SimResult", "simulate"]
