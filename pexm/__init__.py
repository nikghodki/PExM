"""PExM -- Predictive Experience Model.

Memory that lives in the weights, not in a database.

Two primitives:
  absorb(state, outcome) -> experience updates model weights
  generate(state) -> synthesized context from all accumulated knowledge
"""

from .core import ExperienceModel, MultiTimescaleStreams
