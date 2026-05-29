"""
Spike Detection - Stub (trend spike detection).
Alias for spike_detector import compatibility.
"""

try:
    from spike_detector import SpikeDetector
except ImportError:
    SpikeDetector = None
