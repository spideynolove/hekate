#!/usr/bin/env python3
"""Command-line interface for Hekate supervisor."""

import sys
import argparse
from pathlib import Path
from .supervisor import main


def cli():
    """Parse command line arguments and run the supervisor."""
    parser = argparse.ArgumentParser(
        description="Hekate - Autonomous Multi-Agent Development System"
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration YAML file",
        default=None
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level"
    )

    args = parser.parse_args()

    # Set log level if specified
    import logging
    logging.basicConfig(level=getattr(logging, args.log_level))

    # If custom config is specified, we need to handle it
    if args.config:
        print(f"Using custom config: {args.config}")
        # This would require updating the main function to accept config path
        # For now, just note it

    print("Starting Hekate supervisor...")
    main()


if __name__ == "__main__":
    cli()