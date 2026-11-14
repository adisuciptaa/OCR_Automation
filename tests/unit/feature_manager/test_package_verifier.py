from __future__ import annotations

import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.package_verifier import PackageVerifier


def test_package_digest_is_deterministic_and_allowlist_verified(tmp_path):
    package = tmp_path / "feature"
    package.mkdir()
    (package / "a.txt").write_text("hello", encoding="utf-8")
    digest = PackageVerifier.digest_directory(package)
    assert PackageVerifier({"feature": digest}).verify("feature", package) == digest
    (package / "a.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        PackageVerifier({"feature": digest}).verify("feature", package)
    assert error.value.code == "FEATURE_SIGNATURE_INVALID"


def test_untrusted_package_is_rejected(tmp_path):
    package = tmp_path / "feature"
    package.mkdir()
    (package / "file.txt").write_text("data", encoding="utf-8")
    with pytest.raises(ApplicationError):
        PackageVerifier().verify("feature", package)
