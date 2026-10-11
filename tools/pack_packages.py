# -*- coding: utf-8 -*-
"""Encrypt the local packages/ dir into packages.enc (committed to the public
repo). Key comes from PACKAGES_KEY: the environment, else
%LOCALAPPDATA%\\my-aios\\secrets\\pisgat-liam-sign.env (outside OneDrive since 11/10/2026),
else the legacy repo-local .env. It must also be set on the Render service.
Run after adding/changing any package. A missing key is an error; --new-key rotates deliberately."""
import io
import os
import tarfile

from cryptography.fernet import Fernet

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SECRETS_ENV = os.path.join(os.environ.get("LOCALAPPDATA", ""), "my-aios", "secrets", "pisgat-liam-sign.env")


def env_candidates():
    """Where PACKAGES_KEY may live (11/10/2026: moved out of OneDrive into the secrets folder)."""
    out = [os.environ.get("PISGAT_SIGN_ENV_FILE"), SECRETS_ENV, os.path.join(REPO, ".env")]
    return [p for p in out if p]


def load_key(allow_new=False):
    key = os.environ.get("PACKAGES_KEY")
    for env_path in env_candidates():
        if key or not os.path.exists(env_path):
            continue
        for line in open(env_path, encoding="utf-8-sig"):
            if line.strip().startswith("PACKAGES_KEY="):
                key = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        if not allow_new:
            raise SystemExit("PACKAGES_KEY not found (env / " + SECRETS_ENV + "). Refusing to generate a new "
                             "key silently: Render would no longer decrypt packages.enc. "
                             "Run with --new-key only for a deliberate rotation.")
        key = Fernet.generate_key().decode()
        os.makedirs(os.path.dirname(SECRETS_ENV), exist_ok=True)
        with open(SECRETS_ENV, "a", encoding="utf-8") as f:
            f.write(f"\nPACKAGES_KEY={key}\n")
        print("generated new PACKAGES_KEY -> saved to the secrets folder (set it on Render too!)")
    return key


def main():
    import sys
    key = load_key(allow_new="--new-key" in sys.argv)
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
