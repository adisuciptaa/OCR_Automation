import time
from datetime import timedelta

import pytest

from app.core.exceptions import ApplicationError
from app.persistence.repositories.feature_registry_repository import SQLiteFeatureRegistryRepository
from app.persistence.repositories.user_repository import SQLiteUserRepository
from app.security.authentication import AuthenticationManager
from app.security.authorization import RbacAuthorizationService
from app.security.session_manager import SessionManager


@pytest.fixture
def security(tmp_path):
    repository = SQLiteUserRepository(tmp_path / "security.sqlite3")
    authentication = AuthenticationManager(repository)
    return repository, authentication


def test_first_admin_setup_and_rbac_permissions(security):
    repository, authentication = security
    admin = authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")

    assert "Administrator" in admin.roles
    authorization = RbacAuthorizationService(repository)
    assert authorization.is_allowed(admin.user_id, "user.manage")
    assert authorization.is_allowed(admin.user_id, "feature.configure.tax_invoice")
    with pytest.raises(ApplicationError) as error:
        authorization.require("missing-user", "user.manage")
    assert error.value.code == "AUTH_PERMISSION_DENIED"


def test_initial_admin_can_only_be_created_once(security):
    _, authentication = security
    authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")
    with pytest.raises(ApplicationError) as error:
        authentication.setup_initial_administrator("other", "Other Admin", "correct-horse-battery-99")
    assert error.value.code == "AUTH_INITIAL_SETUP_COMPLETE"


def test_login_success_and_invalid_password_lockout(security):
    repository, authentication = security
    identity = authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")

    authenticated = authentication.authenticate("ADMIN", "correct-horse-battery-99")
    assert authenticated.user_id == identity.user_id

    for attempt in range(authentication.MAX_FAILED_ATTEMPTS):
        with pytest.raises(ApplicationError):
            authentication.authenticate("admin", "incorrect-password-123")
    with pytest.raises(ApplicationError) as error:
        authentication.authenticate("admin", "correct-horse-battery-99")
    assert error.value.code == "AUTH_ACCOUNT_LOCKED"
    assert repository.get_auth_record("admin").locked_until is not None


def test_inactive_user_cannot_authenticate(security):
    repository, authentication = security
    identity = authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")
    repository.set_user_active(identity.user_id, False)
    with pytest.raises(ApplicationError) as error:
        authentication.authenticate("admin", "correct-horse-battery-99")
    assert error.value.code == "AUTH_INVALID_CREDENTIALS"


def test_session_idle_expiry_and_revocation(security):
    _, authentication = security
    identity = authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")
    sessions = SessionManager(idle_timeout=timedelta(milliseconds=1), absolute_timeout=timedelta(hours=1))
    session = sessions.create(identity)
    assert sessions.get(session.session_id) is not None
    time.sleep(0.01)
    assert sessions.get(session.session_id) is None
    sessions.revoke(session.session_id)
    assert sessions.get(session.session_id) is None


def test_user_management_requires_permission(security):
    repository, authentication = security
    admin = authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")
    authentication.authorization = RbacAuthorizationService(repository)
    operator = authentication.create_user(admin.user_id, "operator1", "Operator One",
                                          "operator-password-123", ("operator",))
    authorization = RbacAuthorizationService(repository)
    assert authorization.is_allowed(operator.user_id, "feature.view.tax_invoice")
    assert not authorization.is_allowed(operator.user_id, "user.manage")
    with pytest.raises(ApplicationError) as error:
        authentication.create_user(operator.user_id, "other1", "Other User",
                                   "operator-password-123", ("viewer",))
    assert error.value.code == "AUTH_PERMISSION_DENIED"


def test_session_bound_authorization_denies_without_active_session(security):
    repository, authentication = security
    identity = authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")
    sessions = SessionManager(idle_timeout=timedelta(minutes=1), absolute_timeout=timedelta(hours=1))
    authorization = RbacAuthorizationService(repository, sessions)
    assert not authorization.is_allowed(identity.user_id, "user.manage")
    session = sessions.create(identity)
    assert authorization.is_allowed(identity.user_id, "user.manage")
    sessions.revoke(session.session_id)
    assert not authorization.is_allowed(identity.user_id, "user.manage")


def test_last_active_administrator_cannot_be_deactivated_or_demoted(security):
    _, authentication = security
    admin = authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")

    class AllowAuthorization:
        def require(self, actor_id, permission, resource=None):
            return None

    authentication.authorization = AllowAuthorization()
    with pytest.raises(ApplicationError) as deactivate_error:
        authentication.set_user_active("other-admin", admin.user_id, False)
    assert deactivate_error.value.code == "AUTH_LAST_ADMIN_REQUIRED"
    with pytest.raises(ApplicationError) as role_error:
        authentication.update_user_roles("other-admin", admin.user_id, ("operator",))
    assert role_error.value.code == "AUTH_LAST_ADMIN_REQUIRED"


def test_authentication_migration_coexists_with_feature_registry(tmp_path):
    database_path = tmp_path / "application.sqlite3"
    SQLiteFeatureRegistryRepository(database_path)
    SQLiteUserRepository(database_path)
    import sqlite3

    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert {"feature_registry", "feature_audit", "app_users", "app_roles",
            "app_permissions", "app_user_roles", "app_role_permissions",
            "security_audit"}.issubset(tables)


def test_login_lockout_expires_and_success_resets_failures(security):
    repository, authentication = security
    authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")
    authentication.LOCKOUT_DURATION = timedelta(milliseconds=1)
    for _ in range(authentication.MAX_FAILED_ATTEMPTS):
        with pytest.raises(ApplicationError):
            authentication.authenticate("admin", "incorrect-password-123")
    time.sleep(0.01)
    identity = authentication.authenticate("admin", "correct-horse-battery-99")
    assert identity.username == "admin"
    assert repository.get_auth_record("admin").failed_login_attempts == 0


def test_session_absolute_expiry_is_not_extended_by_activity(security):
    _, authentication = security
    identity = authentication.setup_initial_administrator("admin", "System Admin", "correct-horse-battery-99")
    sessions = SessionManager(idle_timeout=timedelta(hours=1), absolute_timeout=timedelta(milliseconds=1))
    session = sessions.create(identity)
    time.sleep(0.01)
    assert sessions.get(session.session_id) is None
