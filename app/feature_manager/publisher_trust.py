"""Publisher identity lifecycle and Ed25519 package signature verification."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.event_bus import ApplicationEvent, EventBus
from app.core.exceptions import ApplicationError
from app.feature_manager.models import (
    PublisherKeyRecord, PublisherRecord, PublisherStatus,
)
from app.feature_manager.package_verifier import PackageVerifier


_SIGNATURE_FILENAME = "publisher_signature.json"
_PUBLISHER_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class PublisherTrustRepository(Protocol):
    def get_publisher(self, publisher_id: str) -> PublisherRecord | None: ...
    def list_publishers(self) -> tuple[PublisherRecord, ...]: ...
    def register_publisher(self, publisher: PublisherRecord, key: PublisherKeyRecord) -> None: ...
    def add_key(self, key: PublisherKeyRecord) -> None: ...
    def get_key(self, publisher_id: str, key_id: str) -> PublisherKeyRecord | None: ...
    def list_keys(self, publisher_id: str) -> tuple[PublisherKeyRecord, ...]: ...
    def revoke_publisher(self, publisher_id: str, now: datetime) -> None: ...
    def revoke_key(self, publisher_id: str, key_id: str, now: datetime) -> None: ...
    def audit(self, *, actor_id: str, publisher_id: str, action: str,
              outcome: str, details: dict[str, object] | None = None) -> None: ...


class PublisherTrustManager:
    """Manages trusted publisher public keys; private signing keys never enter the app."""

    def __init__(
        self, *, repository: PublisherTrustRepository, authorization: object,
        event_bus: EventBus | None = None, logger: logging.Logger | None = None,
    ) -> None:
        self._repository = repository
        self._authorization = authorization
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)

    def register_publisher(
        self, publisher_id: str, display_name: str, public_key_b64: str, actor_id: str,
    ) -> PublisherRecord:
        self._authorization.require(actor_id, "publisher.manage")
        if not _PUBLISHER_ID.fullmatch(publisher_id):
            raise ApplicationError("PUBLISHER_ID_INVALID", "Publisher ID must be lowercase snake_case.")
        if not display_name or not display_name.strip() or len(display_name) > 200:
            raise ApplicationError("PUBLISHER_NAME_INVALID", "Publisher display name is invalid.")
        public_key = self._decode_public_key(public_key_b64)
        key_id = self._key_id(public_key)
        if self._repository.get_publisher(publisher_id) is not None:
            raise ApplicationError("PUBLISHER_ALREADY_EXISTS", "Publisher ID is already registered.")
        now = datetime.now(UTC)
        publisher = PublisherRecord(
            publisher_id, display_name.strip(), PublisherStatus.ACTIVE, now, now,
        )
        key = PublisherKeyRecord(
            publisher_id, key_id, base64.b64encode(public_key).decode("ascii"), "active", now,
        )
        self._repository.register_publisher(publisher, key)
        self._audit(actor_id, publisher_id, "publisher.registered", {"key_id": key_id})
        self._publish("publisher.registered", publisher_id, actor_id, {"key_id": key_id})
        return publisher

    def add_public_key(self, publisher_id: str, public_key_b64: str, actor_id: str) -> PublisherKeyRecord:
        self._authorization.require(actor_id, "publisher.manage")
        publisher = self._repository.get_publisher(publisher_id)
        if publisher is None:
            raise ApplicationError("PUBLISHER_NOT_FOUND", "Publisher is not registered.")
        if publisher.status is not PublisherStatus.ACTIVE:
            raise ApplicationError("PUBLISHER_REVOKED", "A revoked publisher cannot receive new keys.")
        public_key = self._decode_public_key(public_key_b64)
        key_id = self._key_id(public_key)
        if self._repository.get_key(publisher_id, key_id) is not None:
            raise ApplicationError("PUBLISHER_KEY_ALREADY_EXISTS", "Publisher key is already registered.")
        now = datetime.now(UTC)
        key = PublisherKeyRecord(
            publisher_id, key_id, base64.b64encode(public_key).decode("ascii"), "active", now,
        )
        self._repository.add_key(key)
        self._audit(actor_id, publisher_id, "publisher.key_added", {"key_id": key_id})
        self._publish("publisher.key_added", publisher_id, actor_id, {"key_id": key_id})
        return key

    def revoke_key(self, publisher_id: str, key_id: str, actor_id: str) -> None:
        self._authorization.require(actor_id, "publisher.manage")
        key = self._repository.get_key(publisher_id, key_id)
        if key is None:
            raise ApplicationError("PUBLISHER_KEY_NOT_FOUND", "Publisher key is not registered.")
        if key.status == "revoked":
            return
        self._repository.revoke_key(publisher_id, key_id, datetime.now(UTC))
        self._audit(actor_id, publisher_id, "publisher.key_revoked", {"key_id": key_id})
        self._publish("publisher.key_revoked", publisher_id, actor_id, {"key_id": key_id})

    def revoke_publisher(self, publisher_id: str, actor_id: str) -> None:
        self._authorization.require(actor_id, "publisher.manage")
        publisher = self._repository.get_publisher(publisher_id)
        if publisher is None:
            raise ApplicationError("PUBLISHER_NOT_FOUND", "Publisher is not registered.")
        if publisher.status is PublisherStatus.REVOKED:
            return
        self._repository.revoke_publisher(publisher_id, datetime.now(UTC))
        self._audit(actor_id, publisher_id, "publisher.revoked", {})
        self._publish("publisher.revoked", publisher_id, actor_id, {})

    def list_publishers(self, actor_id: str) -> tuple[PublisherRecord, ...]:
        self._authorization.require(actor_id, "publisher.manage")
        return self._repository.list_publishers()

    def list_keys(self, publisher_id: str, actor_id: str) -> tuple[PublisherKeyRecord, ...]:
        self._authorization.require(actor_id, "publisher.manage")
        if self._repository.get_publisher(publisher_id) is None:
            raise ApplicationError("PUBLISHER_NOT_FOUND", "Publisher is not registered.")
        return self._repository.list_keys(publisher_id)

    def verify_package(self, feature_id: str, package_root: Path) -> str:
        """Verify detached package signature, publisher status, key status, and manifest binding."""
        signature_path = package_root / _SIGNATURE_FILENAME
        manifest_path = package_root / "manifest.json"
        if manifest_path.is_symlink():
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Feature manifest cannot be a symbolic link.")
        if signature_path.is_symlink() or not signature_path.is_file():
            raise ApplicationError("FEATURE_SIGNATURE_MISSING", "Feature package publisher signature is missing.")
        try:
            signature_doc = json.loads(signature_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Package signature metadata is invalid.") from exc
        if not isinstance(signature_doc, dict) or set(signature_doc) != {
            "signature_schema_version", "algorithm", "publisher_id", "key_id", "signature"
        } or not isinstance(manifest, dict):
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Package signature metadata has an invalid structure.")
        if signature_doc.get("signature_schema_version") != "1.0" or signature_doc.get("algorithm") != "Ed25519":
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Unsupported package signature format.")
        publisher_id = signature_doc.get("publisher_id")
        key_id = signature_doc.get("key_id")
        if not isinstance(publisher_id, str) or not isinstance(key_id, str):
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Package signature identity is incomplete.")
        if manifest.get("feature_id") != feature_id or manifest.get("publisher_id") != publisher_id:
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Package manifest publisher identity does not match its signature.")
        publisher = self._repository.get_publisher(publisher_id)
        if publisher is None:
            raise ApplicationError("PUBLISHER_NOT_TRUSTED", "Package publisher is not registered as trusted.")
        if publisher.status is not PublisherStatus.ACTIVE:
            raise ApplicationError("PUBLISHER_REVOKED", "Package publisher trust has been revoked.")
        if manifest.get("publisher") != publisher.display_name:
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Manifest publisher name does not match the trusted publisher.")
        key = self._repository.get_key(publisher_id, key_id)
        if key is None or key.status != "active":
            raise ApplicationError("PUBLISHER_KEY_NOT_TRUSTED", "Package signing key is not active and trusted.")
        try:
            public_key_bytes = self._decode_public_key(key.public_key_b64)
            if self._key_id(public_key_bytes) != key_id:
                raise ValueError("Public key fingerprint does not match key ID.")
            if not isinstance(signature_doc["signature"], str):
                raise ValueError("Signature must be a base64 string.")
            signature = base64.b64decode(signature_doc["signature"], validate=True)
            if len(signature) != 64:
                raise ValueError("Invalid Ed25519 signature length.")
            digest = PackageVerifier.digest_directory(package_root)
            payload = self.signature_payload(
                publisher_id=publisher_id, feature_id=feature_id,
                version=str(manifest.get("version", "")), package_digest=digest,
            )
            Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, payload)
        except InvalidSignature as exc:
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Publisher signature verification failed.") from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Package signature encoding is invalid.") from exc
        return digest

    @staticmethod
    def signature_payload(*, publisher_id: str, feature_id: str, version: str, package_digest: str) -> bytes:
        payload = {
            "signature_schema_version": "1.0",
            "algorithm": "Ed25519",
            "publisher_id": publisher_id,
            "feature_id": feature_id,
            "version": version,
            "package_digest": package_digest,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _decode_public_key(value: str) -> bytes:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, TypeError) as exc:
            raise ApplicationError("PUBLISHER_PUBLIC_KEY_INVALID", "Public key must be valid base64.") from exc
        if len(decoded) != 32:
            raise ApplicationError("PUBLISHER_PUBLIC_KEY_INVALID", "Ed25519 public keys must contain 32 bytes.")
        return decoded

    @staticmethod
    def _key_id(public_key: bytes) -> str:
        return "ed25519-" + hashlib.sha256(public_key).hexdigest()[:24]

    def _audit(self, actor_id: str, publisher_id: str, action: str, details: dict[str, object]) -> None:
        self._repository.audit(
            actor_id=actor_id, publisher_id=publisher_id, action=action,
            outcome="success", details=details,
        )

    def _publish(self, event_name: str, publisher_id: str, actor_id: str, payload: dict[str, object]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(ApplicationEvent(
                event_name, {"publisher_id": publisher_id, **payload}, actor_id=actor_id,
            ))
