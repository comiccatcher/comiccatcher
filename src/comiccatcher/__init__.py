# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import subprocess
from pathlib import Path

__version__ = "0.1.0a3"

def get_version_string() -> str:
    """Returns the base version, optionally appended with git build info."""
    
    # 1. Try to load pre-compiled build info (present in packaged releases)
    try:
        from comiccatcher._build_info import __commit__
        if __commit__:
            return f"{__version__} ({__commit__})"
    except ImportError:
        pass
        
    # 2. Fallback to runtime dynamic git query (for local dev environments)
    try:
        # Resolve the root directory of the repository
        repo_dir = Path(__file__).resolve().parent.parent.parent.parent
        git_dir = repo_dir / ".git"
        
        if git_dir.exists() and git_dir.is_dir():
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
                return f"{__version__} ({git_info})"
    except Exception:
        pass
    
    return __version__
