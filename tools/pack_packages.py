# -*- coding: utf-8 -*-
"""Encrypt the local packages/ dir into packages.enc (committed to the public
repo). Key comes from PACKAGES_KEY in the repo-local .env (gitignored) and must
also be set on the Render service. Run after adding/changing any package."""
import io
import os
import tarfile

from cryptography.fernet import Fernet

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_key():
    key = os.environ.get("PACKAGES_KEY")
    env_path = os.path.join(REPO, ".env")
    if not key and os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8-sig"):
            if line.strip().startswith("PACKAGES_KEY="):
                key = line.strip().split("=", 1)[1]
    if not key:
        key = Fernet.generate_key().decode()
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"\nPACKAGES_KEY={key}\n")
        print("generated new PACKAGES_KEY -> saved to .env (set it on Render too!)")
    return key


def main():
    key = load_key()
    src = os.path.join(REPO, "packages")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in sorted(os.listdir(src)):
            tar.add(os.path.join(src, name), arcname=name)
    blob = Fernet(key.encode()).encrypt(buf.getvalue())
    out = os.path.join(REPO, "packages.enc")
    with open(out, "wb") as f:
        f.write(blob)
    print(f"packages.enc written ({len(blob)//1024}KB, {len(os.listdir(src))} package(s))")


if __name__ == "__main__":
    main()
