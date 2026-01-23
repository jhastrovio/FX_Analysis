#!/usr/bin/env python3
"""
DEPRECATED: Use bin/check_model_count.py instead.

This shim file exists for backward compatibility during transition.
It will be removed in a future version.
"""
import sys
import warnings

warnings.warn(
    "check_model_count.py is deprecated. Use 'python bin/check_model_count.py' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from bin module
if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "bin/check_model_count.py"] + sys.argv[1:])
    sys.exit(result.returncode)
