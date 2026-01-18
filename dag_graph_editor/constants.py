"""
Constants and configuration values for DAG Graph Editor.
"""

# Available node shapes
SHAPES = [
    "circle",
    "rect", 
    "rounded-rect",
    "diamond",
    "hexagon",
    "triangle",
    "projektnode"
]

# Node dimensions (pixels)
NODE_WIDTH = 110
NODE_HEIGHT = 64

# Shorthand aliases for backwards compatibility
NODE_W = NODE_WIDTH
NODE_H = NODE_HEIGHT

# Default colors
DEFAULT_NODE_COLOR = "#78AAFF"  # Light blue
SELECTION_COLOR = "#2878FF"    # Bright blue
CRITICAL_PATH_COLOR = "#C82828"  # Red

# Edge styling
EDGE_COLOR = "#787878"  # Gray
EDGE_WIDTH = 1.5

# PM dependency types
PM_DEPENDENCY_TYPES = ["FS", "SS", "FF", "SF"]
