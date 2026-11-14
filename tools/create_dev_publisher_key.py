"""Create an Ed25519 keypair for a local development publisher.

Keep the private key outside the repository and never share it. The public key may
be registered by an authenticated Administrator in Feature Management.
"""
from __future__ import annotations

import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="Directory outside the source repository")
    args = parser.parse_args()
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    private_path = output / "ocr_automation_dev_ed25519.pem"
    public_path = output / "ocr_automation_dev_public_key.txt"
    if private_path.exists() or public_path.exists():
        parser.error("Key files already exist; choose another directory or back them up first.")
    key = Ed25519PrivateKey.generate()
    private_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    public_raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_path.write_text(base64.b64encode(public_raw).decode("ascii") + "\n", encoding="ascii")
    try:
        private_path.chmod(0o600)
    except OSError:
        pass
    print(f"Private key (KEEP SECRET): {private_path}")
    print(f"Public key (register in Feature Management): {public_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
