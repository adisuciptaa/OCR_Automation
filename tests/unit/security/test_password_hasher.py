from app.core.exceptions import ApplicationError
from app.security.password_hasher import PasswordHasher


def test_password_hash_is_salted_and_verifiable() -> None:
    hasher = PasswordHasher()
    first = hasher.hash("a-strong-password-123")
    second = hasher.hash("a-strong-password-123")

    assert first != second
    assert hasher.verify("a-strong-password-123", first)
    assert not hasher.verify("wrong-password-123", first)


def test_password_policy_requires_twelve_characters() -> None:
    try:
        PasswordHasher().hash("short")
    except ApplicationError as exc:
        assert exc.code == "AUTH_PASSWORD_POLICY"
    else:
        raise AssertionError("Expected password policy rejection")
