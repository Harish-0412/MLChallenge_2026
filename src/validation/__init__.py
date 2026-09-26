"""Member B: validation splits, the official macro-F0.5 scorer and leakage checks (protocol ``val_v1``).

Nothing here reads a label to make a modelling decision: the split is a deterministic function of (seed, entity id, country, match-count
bucket), and the scorer is a pure function of truth and prediction sets.
"""
PROTOCOL_VERSION = 'val_v1'
