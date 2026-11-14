from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.exceptions import ApplicationError
from app.feature_manager.package_verifier import PackageVerifier
from app.feature_manager.publisher_trust import PublisherTrustManager
from app.persistence.repositories.publisher_trust_repository import SQLitePublisherTrustRepository


class AllowAuthorization:
    def require(self, actor_id, permission, resource=None):
        if actor_id != "admin" or permission != "publisher.manage":
            raise ApplicationError("AUTH_PERMISSION_DENIED", "Denied")


def create_key():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, base64.b64encode(public).decode("ascii")


def make_signed_package(root, private_key, publisher_id="acme_ocr", display_name="ACME OCR"):
    root.mkdir(parents=True)
    manifest = {
        "manifest_schema_version": "1.0", "feature_id": "invoice_reader",
        "display_name": "Invoice Reader", "version": "1.0.0", "description": "Test feature",
        "publisher": display_name, "publisher_id": publisher_id,
        "entry_point": "plugin:Feature", "minimum_core_version": "0.1.0",
        "api_contract_version": "2.7.0", "dependencies": {"features": [], "services": []},
        "permissions": [], "configuration_schema": "config_schema.json",
        "ui": {"navigation_label": "Invoice Reader", "icon": "file", "workspace": "ui:Workspace"},
        "data_schema_version": 1,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "config_schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (root / "plugin.py").write_text("class Feature: pass\n", encoding="utf-8")
    digest = PackageVerifier.digest_directory(root)
    payload = PublisherTrustManager.signature_payload(
        publisher_id=publisher_id, feature_id="invoice_reader",
        version="1.0.0", package_digest=digest,
    )
    signature = private_key.sign(payload)
    (root / "publisher_signature.json").write_text(json.dumps({
        "signature_schema_version": "1.0", "algorithm": "Ed25519",
        "publisher_id": publisher_id,
        "key_id": "ed25519-" + __import__("hashlib").sha256(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
            )
        ).hexdigest()[:24],
        "signature": base64.b64encode(signature).decode("ascii"),
    }), encoding="utf-8")
    return digest


def setup_trust(tmp_path):
    import sqlite3
    database = tmp_path / "trust.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            (Path(__file__).parents[3] / "app" / "persistence" / "migrations" / "0002_authentication.sql").read_text()
        )
    repo = SQLitePublisherTrustRepository(database)
    manager = PublisherTrustManager(repository=repo, authorization=AllowAuthorization())
    return repo, manager


def test_register_and_verify_ed25519_signed_package(tmp_path):
    repo, manager = setup_trust(tmp_path)
    private, public_b64 = create_key()
    manager.register_publisher("acme_ocr", "ACME OCR", public_b64, "admin")
    package = tmp_path / "package"
    expected_digest = make_signed_package(package, private)
    verifier = PackageVerifier(publisher_trust=manager)
    assert verifier.verify("invoice_reader", package) == expected_digest
    assert manager.list_publishers("admin")[0].status.value == "active"


def test_rejects_modified_package_after_signature(tmp_path):
    _, manager = setup_trust(tmp_path)
    private, public_b64 = create_key()
    manager.register_publisher("acme_ocr", "ACME OCR", public_b64, "admin")
    package = tmp_path / "package"
    make_signed_package(package, private)
    (package / "plugin.py").write_text("# changed after signing", encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        manager.verify_package("invoice_reader", package)
    assert error.value.code == "FEATURE_SIGNATURE_INVALID"


def test_rejects_untrusted_or_revoked_publisher(tmp_path):
    _, manager = setup_trust(tmp_path)
    private, _ = create_key()
    package = tmp_path / "package"
    make_signed_package(package, private)
    with pytest.raises(ApplicationError) as error:
        manager.verify_package("invoice_reader", package)
    assert error.value.code == "PUBLISHER_NOT_TRUSTED"

    _, public_b64 = create_key()
    manager.register_publisher("acme_ocr", "ACME OCR", public_b64, "admin")
    manager.revoke_publisher("acme_ocr", "admin")
    with pytest.raises(ApplicationError) as error:
        manager.verify_package("invoice_reader", package)
    assert error.value.code == "PUBLISHER_REVOKED"


def test_key_rotation_and_key_revocation(tmp_path):
    _, manager = setup_trust(tmp_path)
    old_private, old_public = create_key()
    manager.register_publisher("acme_ocr", "ACME OCR", old_public, "admin")
    new_private, new_public = create_key()
    new_key = manager.add_public_key("acme_ocr", new_public, "admin")
    package = tmp_path / "package"
    make_signed_package(package, new_private)
    assert manager.verify_package("invoice_reader", package)
    manager.revoke_key("acme_ocr", new_key.key_id, "admin")
    with pytest.raises(ApplicationError) as error:
        manager.verify_package("invoice_reader", package)
    assert error.value.code == "PUBLISHER_KEY_NOT_TRUSTED"


def test_publisher_management_requires_authorization(tmp_path):
    _, manager = setup_trust(tmp_path)
    _, public_b64 = create_key()
    with pytest.raises(ApplicationError):
        manager.register_publisher("acme_ocr", "ACME OCR", public_b64, "operator")


def test_rejects_signature_from_wrong_feature_id(tmp_path):
    _, manager = setup_trust(tmp_path)
    private, public_b64 = create_key()
    manager.register_publisher("acme_ocr", "ACME OCR", public_b64, "admin")
    package = tmp_path / "package"
    make_signed_package(package, private)
    with pytest.raises(ApplicationError) as error:
        manager.verify_package("other_feature", package)
    assert error.value.code == "FEATURE_SIGNATURE_INVALID"


def test_publisher_signing_utility_creates_verifiable_envelope(tmp_path):
    from tools.sign_feature_package import sign_package

    _, manager = setup_trust(tmp_path)
    private, public_b64 = create_key()
    manager.register_publisher("acme_ocr", "ACME OCR", public_b64, "admin")
    package = tmp_path / "package"
    package.mkdir()
    manifest = {
        "manifest_schema_version": "1.0", "feature_id": "invoice_reader",
        "display_name": "Invoice Reader", "version": "1.0.0", "description": "Test feature",
        "publisher": "ACME OCR", "publisher_id": "acme_ocr",
        "entry_point": "plugin:Feature", "minimum_core_version": "0.1.0",
        "api_contract_version": "2.8.0", "dependencies": {"features": [], "services": []},
        "permissions": [], "configuration_schema": "config_schema.json",
        "ui": {"navigation_label": "Invoice Reader", "icon": "file", "workspace": "ui:Workspace"},
        "data_schema_version": 1,
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "config_schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (package / "plugin.py").write_text("class Feature: pass\n", encoding="utf-8")
    key_path = tmp_path / "publisher.pem"
    key_path.write_bytes(private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    signature_path = sign_package(package, "acme_ocr", key_path)
    assert signature_path.is_file()
    assert manager.verify_package("invoice_reader", package).startswith("sha256:")


def test_signed_archive_passes_feature_installer_staging(tmp_path):
    import zipfile
    from app.feature_manager.installer import FeatureInstaller
    from app.feature_manager.manifest_loader import ManifestLoader

    _, manager = setup_trust(tmp_path)
    private, public_b64 = create_key()
    manager.register_publisher("acme_ocr", "ACME OCR", public_b64, "admin")
    package = tmp_path / "source"
    make_signed_package(package, private)
    archive = tmp_path / "invoice_reader.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for item in package.iterdir():
            bundle.write(item, item.name)
    installer = FeatureInstaller(
        tmp_path / "packages", tmp_path / "features",
        ManifestLoader(), PackageVerifier(publisher_trust=manager),
    )
    candidate = installer.stage_archive(archive)
    assert candidate.manifest.publisher_id == "acme_ocr"
    assert candidate.package_digest.startswith("sha256:")
