#!/usr/bin/env python3
import sys
import os
import subprocess
from pathlib import Path

def print_step(msg):
    print(f"--- {msg} ---")

def run_ruff():
    """Step 1: Static Analysis (Fastest)"""
    print_step("Running Static Analysis (Ruff)")
    
    # We run with a broad selection to show warnings, but we only check return code for CRITICALS
    # F821: Undefined name
    # E999: Syntax Error
    critical_cmd = [sys.executable, "-m", "ruff", "check", ".", "--select", "F821,E999"]
    all_cmd = [sys.executable, "-m", "ruff", "check", ".", "--select", "F401,F821,E999"]
    
    # 1. Get all warnings for the log
    subprocess.run(all_cmd, capture_output=True, text=True) # Just to populate cache or for silent check
    
    # 2. Run critical check
    result = subprocess.run(critical_cmd, capture_output=True, text=True)
    if result.returncode != 0 and result.stdout.strip():
        print("❌ CRITICAL ERRORS DETECTED:")
        print(result.stdout)
        return False
    
    # 3. If critical passed, show other warnings but don't fail
    warn_result = subprocess.run(all_cmd, capture_output=True, text=True)
    if warn_result.returncode != 0 and warn_result.stdout.strip():
        print("⚠️  Linting warnings (Optional fix):")
        # Just show the first 20 to keep it clean
        lines = warn_result.stdout.splitlines()
        for line in lines[:20]: print(line)
        if len(lines) > 20: print(f"... and {len(lines)-20} more.")
        
    return True

def run_import_test():
    """Step 2: Lightweight Import Test (Catch Dynamic Errors)"""
    print_step("Running Import Integrity Test")
    
    # We try to import every Python file in src/
    # This catches ModuleNotFoundError and AttributeError at class/module level.
    base_dir = Path("src")
    if not base_dir.exists():
        # Fallback for if script is run from inside scripts/
        base_dir = Path("../src")
        
    if not base_dir.exists():
        print("❌ Error: Could not find src directory.")
        return False

    sys.path.insert(0, str(base_dir.absolute()))
    
    python_files = list(base_dir.glob("**/*.py"))
    failed = []
    
    for py_file in python_files:
        if py_file.name == "__init__.py" or "pycache" in str(py_file):
            continue
            
        # Convert path to module string: src/comiccatcher/ui/views/settings.py -> comiccatcher.ui.views.settings
        # relative_to(base_dir) removes the 'src/' part
        module_path = str(py_file.relative_to(base_dir).with_suffix("")).replace(os.sep, ".")
        
        try:
            # We use a subprocess for each import to prevent one failure from stopping the script
            # Ensure the subprocess also has the correct PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{base_dir.absolute()}{os.pathsep}{env.get('PYTHONPATH', '')}"
            subprocess.check_output([sys.executable, "-c", f"import {module_path}"], stderr=subprocess.STDOUT, env=env)
        except subprocess.CalledProcessError as e:
            failed.append((module_path, e.output.decode().splitlines()[-1]))

    if failed:
        for mod, err in failed:
            print(f"❌ {mod}: {err}")
        return False
    return True

def main():
    # Ensure dependencies are present
    try:
        import ruff
    except ImportError:
        print("Installing ruff...")
        subprocess.run([sys.executable, "-m", "pip", "install", "ruff", "--quiet"])

    success = True
    if not run_ruff():
        success = False
        print("⚠️ Static analysis found potential issues.")
    
    if not run_import_test():
        success = False
        print("⚠️ Import integrity check failed.")

    if success:
        print("\n✅ INTEGRITY PASSED: No missing imports or undefined symbols detected.")
        sys.exit(0)
    else:
        print("\n❌ INTEGRITY FAILED: Please fix the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
