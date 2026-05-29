#!/usr/bin/env python3
import os
import sys
import shutil
import hashlib
import gzip
import subprocess
import tarfile
from pathlib import Path
from datetime import datetime

# Named constants to avoid hardcoded magic values
REP_ORIGIN = "ComicCatcher"
REP_LABEL = "ComicCatcher"
REP_SUITE = "stable"
REP_CODENAME = "stable"
REP_ARCH = "amd64"
REP_COMPONENT = "main"
REP_DESC = "ComicCatcher APT Repository"

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# If running standalone in the cloned repo, use CWD as APT_DIR
if Path.cwd().name == "apt-repo" or (Path.cwd() / "pool").exists():
    APT_DIR = Path.cwd().resolve()
else:
    DIST_DIR = PROJECT_ROOT / "dist"
    APT_DIR = DIST_DIR / "apt"

POOL_DIR = APT_DIR / "pool/main/c/comiccatcher"
BINARY_DIR = APT_DIR / "dists/stable/main/binary-amd64"
RELEASE_DIR = APT_DIR / "dists/stable"

def log(msg):
    print(f"[*] {msg}")

def calculate_hashes(file_path):
    """Calculates MD5, SHA-1, and SHA-256 for a file."""
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha1.hexdigest(), sha256.hexdigest()

def extract_control_info(deb_path):
    """Natively extracts the control file content from a .deb package."""
    # Try using dpkg-deb if available
    try:
        res = subprocess.run(["dpkg-deb", "-f", str(deb_path)], capture_output=True, text=True, check=True)
        if res.stdout.strip():
            return res.stdout
    except Exception:
        pass

    # Fallback to native python ar and tarfile parsing
    try:
        with open(deb_path, "rb") as f:
            header = f.read(8)
            if header != b"!<arch>\n":
                raise ValueError("Not a valid ar archive")
            
            while True:
                member_header = f.read(60)
                if len(member_header) < 60:
                    break
                
                name = member_header[0:16].decode("ascii").strip()
                size = int(member_header[48:58].decode("ascii").strip())
                
                # Align size to even bytes
                data_size = size + (size % 2)
                data = f.read(data_size)[:size]
                
                if name.startswith("control.tar"):
                    import io
                    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
                        for member in tar.getmembers():
                            if member.name in ["./control", "control"]:
                                control_file = tar.extractfile(member)
                                if control_file:
                                    return control_file.read().decode("utf-8")
    except Exception as e:
        log(f"Error extracting control natively from {deb_path.name}: {e}")
        
    return ""

def update_repo(gpg_key_email=None):
    log("Creating static APT repository structure...")
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    BINARY_DIR.mkdir(parents=True, exist_ok=True)

    # Copy public GPG key if present
    src_key = PROJECT_ROOT / "packaging/public.gpg.key"
    if src_key.exists():
        shutil.copy(src_key, APT_DIR / "public.gpg.key")
        log("Copied public.gpg.key to repository root.")

    # 1. Copy any newly built .deb packages from parent's dist/ if running inside the build environment
    dist_dir = PROJECT_ROOT / "dist"
    if dist_dir.exists():
        for deb in dist_dir.glob("*.deb"):
            dest_path = POOL_DIR / deb.name
            if dest_path.resolve() != deb.resolve():
                shutil.copy(deb, dest_path)

    # Gather all built .deb packages inside the pool directory
    pool_debs = list(POOL_DIR.glob("*.deb"))
    if not pool_debs:
        log(f"No .deb packages found in pool directory: {POOL_DIR}")
        return

    packages_metadata = []
    for deb in pool_debs:
        # Calculate size and hashes
        size = deb.stat().st_size
        md5, sha1, sha256 = calculate_hashes(deb)
        
        # Extract metadata from control file
        control_data = extract_control_info(deb)
        if not control_data.strip():
            log(f"Warning: Failed to extract control data from {deb.name}")
            continue
        
        # Format entry for Packages file
        relative_path = f"pool/main/c/comiccatcher/{deb.name}"
        packages_metadata.append(
            f"{control_data.strip()}\n"
            f"Filename: {relative_path}\n"
            f"Size: {size}\n"
            f"MD5sum: {md5}\n"
            f"SHA1: {sha1}\n"
            f"SHA256: {sha256}"
        )

    # 2. Write the Packages & Packages.gz index
    packages_content = "\n\n".join(packages_metadata) + "\n"
    packages_file = BINARY_DIR / "Packages"
    packages_file.write_text(packages_content, encoding="utf-8")
    
    with gzip.open(BINARY_DIR / "Packages.gz", "wt", encoding="utf-8") as f:
        f.write(packages_content)
    log(f"Generated Packages and Packages.gz for {len(pool_debs)} package(s).")

    # 3. Create the Release descriptor
    # Calculate sizes and hashes of the indices relative to dists/stable/
    files_to_hash = [
        Path("main/binary-amd64/Packages"),
        Path("main/binary-amd64/Packages.gz")
    ]
    
    hash_lines_md5 = []
    hash_lines_sha1 = []
    hash_lines_sha256 = []
    
    for rel_path in files_to_hash:
        abs_path = RELEASE_DIR / rel_path
        if abs_path.exists():
            size = abs_path.stat().st_size
            md5, sha1, sha256 = calculate_hashes(abs_path)
            # Use forward slashes for Debian paths
            posix_path = str(rel_path).replace("\\", "/")
            hash_lines_md5.append(f" {md5} {size} {posix_path}")
            hash_lines_sha1.append(f" {sha1} {size} {posix_path}")
            hash_lines_sha256.append(f" {sha256} {size} {posix_path}")

    utc_now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S UTC")
    
    release_content = (
        f"Origin: {REP_ORIGIN}\n"
        f"Label: {REP_LABEL}\n"
        f"Suite: {REP_SUITE}\n"
        f"Codename: {REP_CODENAME}\n"
        f"Architectures: {REP_ARCH}\n"
        f"Components: {REP_COMPONENT}\n"
        f"Description: {REP_DESC}\n"
        f"Date: {utc_now}\n"
        f"MD5Sum:\n" + "\n".join(hash_lines_md5) + "\n"
        f"SHA1:\n" + "\n".join(hash_lines_sha1) + "\n"
        f"SHA256:\n" + "\n".join(hash_lines_sha256) + "\n"
    )
    
    release_file = RELEASE_DIR / "Release"
    release_file.write_text(release_content, encoding="utf-8")
    log("Generated Release manifest.")

    # 4. Cryptographically Sign the Repository if GPG email is supplied
    if gpg_key_email:
        log(f"Signing repository with GPG key: {gpg_key_email}...")
        # Create detached signature (Release.gpg)
        subprocess.run([
            "gpg", "--batch", "--yes", "--armor",
            "--local-user", gpg_key_email,
            "--detach-sign", "--output", str(RELEASE_DIR / "Release.gpg"),
            str(RELEASE_DIR / "Release")
        ], check=True)
        # Create inline signature (InRelease)
        subprocess.run([
            "gpg", "--batch", "--yes", "--armor",
            "--local-user", gpg_key_email,
            "--clearsign", "--output", str(RELEASE_DIR / "InRelease"),
            str(RELEASE_DIR / "Release")
        ], check=True)
        log("Repository signed successfully!")

if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else None
    update_repo(email)
