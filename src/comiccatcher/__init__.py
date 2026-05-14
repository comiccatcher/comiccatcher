# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import subprocess
from pathlib import Path

__version__ = "0.5.0"

def get_version_string() -> str:
    """Returns the base version, optionally appended with git build info."""
    
    info = None
    
    # 1. Try to load pre-compiled build info (present in packaged releases)
    try:
        from comiccatcher._build_info import __commit__
        if __commit__:
            info = __commit__
    except ImportError:
        pass
        
    # 2. Fallback to runtime dynamic git query (for local dev environments)
    if not info:
        try:
            # Search upwards for the .git directory starting from this file
            current = Path(__file__).resolve().parent
            repo_dir = None
            for _ in range(5):  # Don't go up more than 5 levels
                if (current / ".git").exists():
                    repo_dir = current
                    break
                if current.parent == current:
                    break
                current = current.parent

            if repo_dir:
                result = subprocess.run(
                    ["git", "describe", "--tags", "--always", "--dirty"],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=1
                )
                git_info = result.stdout.strip()
                if git_info:
                    info = git_info
        except Exception:
            pass
    
    if info:
        # Deduplicate if the info is just the version tag (e.g. "v0.5.0" matches "0.5.0")
        if info.lstrip('v') == __version__.lstrip('v'):
            return __version__
        return f"{__version__} ({info})"
    
    return __version__
