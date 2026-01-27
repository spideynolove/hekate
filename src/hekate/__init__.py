"""Hekate: Autonomous Multi-Agent Development System

A platform for orchestrating AI coding agents across multiple providers
with intelligent routing, quality assurance, and cost optimization.
"""

__version__ = "1.0.0"

# Lazy imports to avoid requiring dependencies at package import time
def Supervisor(*args, **kwargs):
    from .supervisor import Supervisor as _Supervisor
    return _Supervisor(*args, **kwargs)

def main():
    from .supervisor import main as _main
    _main()

__all__ = ["Supervisor", "main"]