#!/usr/bin/env python3
"""
Backwards-compatible entry point: python3 render.py capture.json -o output.ext

Delegates to render/__main__.py. All rendering logic lives in the render/ package.
"""

from render.__main__ import main

if __name__ == "__main__":
    main()
