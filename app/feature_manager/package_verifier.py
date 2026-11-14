"""Deterministic package hashing and externally managed trust allowlist."""
from __future__ import annotations

import hashlib
from pathlib import Path
from collections.abc import Mapping, Sequence

from app.core.exceptions import ApplicationError


class PackageVerifier:
    def __init__(
        self, trusted_digests: Mapping[str, str | Sequence[str]] | None = None,
        *, publisher_trust: object | None = None,
    ) -> None:
        self._publisher_trust = publisher_trust
        self._trusted_digests = {
            key: ({value.lower()} if isinstance(value, str) else {item.lower() for item in value})
            for key, value in (trusted_digests or {}).items()
        }

    @staticmethod
    def digest_directory(package_path: Path) -> str:
        if package_path.is_symlink():
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Feature package root cannot be a symbolic link.")
        try:
            root = package_path.resolve(strict=True)
        except OSError as exc:
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Feature package directory is unavailable.") from exc
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Feature packages cannot contain symbolic links.")
            if path.is_file() and path.relative_to(root).as_posix() == "publisher_signature.json":
                continue
            if path.is_file():
                relative = path.relative_to(root).as_posix().encode("utf-8")
                digest.update(len(relative).to_bytes(4, "big"))
                digest.update(relative)
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"

    def verify(self, feature_id: str, package_path: Path) -> str:
        if self._publisher_trust is not None:
            return self._publisher_trust.verify_package(feature_id, package_path)
        actual = self.digest_directory(package_path)
        expected = self._trusted_digests.get(feature_id, set())
        if actual.lower() not in expected:
            raise ApplicationError(
                "FEATURE_SIGNATURE_INVALID",
                "Feature package is not present in the trusted package allowlist.",
                details={"feature_id": feature_id, "package_digest": actual},
            )
        return actual
