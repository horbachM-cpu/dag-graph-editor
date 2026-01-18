"""
DAG Graph Editor Package

A visual DAG (Directed Acyclic Graph) editor with Project Management capabilities.
"""

__version__ = "1.0.0"
__author__ = "Marcel"

from .model import GraphModel, GraphDocument
from .main import MainWindow

__all__ = ["GraphModel", "GraphDocument", "MainWindow", "__version__"]
