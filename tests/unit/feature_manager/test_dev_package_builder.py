from __future__ import annotations

import base64
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.models import PublisherKeyRecord, PublisherRecord, PublisherStatus
from app.feature_manager.publisher_trust import PublisherTrustManager
from tools.build_feature_package import build_package


class _Repository:
    def __init__(self, publisher: PublisherRecord, key: PublisherKeyRecord) -> None:
        self.publisher = publisher
        self.key = key

    def get_publisher(self, publisher_id: str):
        return self.publisher if publisher_id == self.publisher.publisher_id else None

    def get_key(self, publisher_id: str, key_id: str):
        if publisher_id == self.key.publisher_id and key_id == self.key.key_id:
            return self.key
        return None


def test_dev_builder_creates_manifest_valid_signed_package(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    private_path = tmp_path / "publisher.pem"
    private_path.write_bytes(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_b64 = base64.b64encode(public_raw).decode("ascii")
    key_id = PublisherTrustManager._key_id(public_raw)
    now = datetime.now(UTC)
    publisher = PublisherRecord("ocr_automation_dev", "OCR Automation", PublisherStatus.ACTIVE, now, now)
    key = PublisherKeyRecord("ocr_automation_dev", key_id, public_b64, "active", now)

    archive = build_package(
        "tax_invoice", "ocr_automation_dev", private_path, tmp_path / "tax_invoice.zip"
    )

    with zipfile.ZipFile(archive) as bundle:
        assert "tax_invoice/manifest.json" in bundle.namelist()
        assert "tax_invoice/publisher_signature.json" in bundle.namelist()
        assert not any("/tests/" in name for name in bundle.namelist())
        manifest_data = json.loads(bundle.read("tax_invoice/manifest.json"))

    assert manifest_data["publisher_id"] == "ocr_automation_dev"
    root = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(root)
    package_root = root / "tax_invoice"
    manifest = ManifestLoader().load(package_root)
    assert manifest.feature_id == "tax_invoice"

    verifier = PublisherTrustManager(
        repository=_Repository(publisher, key), authorization=None
    )
    digest = verifier.verify_package("tax_invoice", package_root)
    assert digest.startswith("sha256:")
