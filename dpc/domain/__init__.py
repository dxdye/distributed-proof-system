"""Domain core: pure functions of the review and trust model (concept §4–§13).

Everything here is deterministic given its inputs (randomness only through an
explicitly passed ``numpy.random.Generator``), so the simulation (M3) and the
production system run exactly the same code (docs/adr/0003).
"""
