"""
DEPRECATED: Use bin/streamlit_app.py instead.

This shim file exists for backward compatibility during transition.
It will be removed in a future version.
"""
import sys
import warnings

warnings.warn(
    "Streamlit.py is deprecated. Use 'streamlit run bin/streamlit_app.py' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Import and run the actual app
if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "streamlit", "run", "bin/streamlit_app.py"] + sys.argv[1:])
    sys.exit(result.returncode)
