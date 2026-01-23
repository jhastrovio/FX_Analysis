#!/usr/bin/env python
"""
Entry point for data consolidation.

Analytics-only: Consolidate individual FX-model return CSVs into a temporary analysis matrix.
"""
from lib.data_consolidate import app

if __name__ == "__main__":
    app()
