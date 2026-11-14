"""Sign a feature package with an offline Ed25519 publisher private key.

Usage:
    python tools/sign_feature_package.py PACKAGE_DIR --publisher-id acme_ocr --private-key publisher_ed25519.pem

The private key is never copied into the package or application data directory.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.feature_manager.package_verifier import PackageVerifier
from app.feature_manager.publisher_trust import PublisherTrustManager


def sign_package(package_dir: Path, publisher_id: str, private_key_path: Path) -> Path:
    root = package_dir.resolve(strict=True)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("publisher_id") != publisher_id:
        raise ValueError("Manifest publisher_id does not match --publisher-id.")
    key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Publisher private key must be Ed25519 PEM.")
    public_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = "ed25519-" + hashlib.sha256(public_bytes).hexdigest()[:24]
    digest = PackageVerifier.digest_directory(root)
    payload = PublisherTrustManager.signature_payload(
        publisher_id=publisher_id,
        feature_id=manifest["feature_id"],
        version=manifest["version"],
        package_digest=digest,
    )
    signature = key.sign(payload)
    envelope = {
        "signature_schema_version": "1.0",
        "algorithm": "Ed25519",
        "publisher_id": publisher_id,
        "key_id": key_id,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    destination = root / "publisher_signature.json"
    temporary = root / ".publisher_signature.tmp"
    temporary.write_text(json.dumps(envelope, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a detached Ed25519 signature for an OCR Automation feature package.")
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--publisher-id", required=True)
    parser.add_argument("--private-key", required=True, type=Path)
    args = parser.parse_args()
    output = sign_package(args.package_dir, args.publisher_id, args.private_key)
    print(f"Signed package: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
