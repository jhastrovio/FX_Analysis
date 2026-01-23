#!/usr/bin/env python
"""
DEPRECATED: Use python -m lib.data_consolidate instead.

This shim file exists for backward compatibility during transition.
It will be removed in a future version.
"""
import sys
import warnings

warnings.warn(
    "Data_Consolidate.py is deprecated. Use 'python -m lib.data_consolidate' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from lib module
if __name__ == "__main__":
    from lib.data_consolidate import app
    app()
