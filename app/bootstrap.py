"""Application composition root for Core, persistence, security, and presentation."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QDialog

from app import __version__
from app.core.application import ApplicationRuntime
from app.core.config_manager import ConfigManager
from app.core.event_bus import EventBus
from app.core.exceptions import ApplicationError
from app.core.logging_config import configure_logging
from app.core.service_registry import ServiceRegistry
from app.feature_manager.manager import FeatureManagerService
from app.feature_manager.configuration_manager import FeatureConfigurationManagerService
from app.feature_manager.migration_engine import FeatureDataMigrationEngine
from app.feature_manager.health_check import FeatureHealthCheckManager
from app.feature_manager.rollback import FeatureRollbackCoordinator
from app.feature_manager.package_verifier import PackageVerifier
from app.feature_manager.publisher_trust import PublisherTrustManager
from app.feature_manager.runtime import FeatureRuntimeManager
from app.persistence.repositories.feature_registry_repository import SQLiteFeatureRegistryRepository
from app.persistence.repositories.feature_configuration_repository import SQLiteFeatureConfigurationRepository
from app.persistence.repositories.publisher_trust_repository import SQLitePublisherTrustRepository
from app.persistence.repositories.user_repository import SQLiteUserRepository
from app.security.audit import SecurityAuditService
from app.security.authentication import AuthenticationManager
from app.security.authorization import RbacAuthorizationService
from app.security.models import UserIdentity
from app.security.session_manager import SessionManager
from app.services.registration import register_document_processing_services
from app.ui.application_window import ApplicationWindow
from app.ui.dialogs.authentication_dialogs import InitialAdministratorDialog, LoginDialog
from app.ui.view_models.feature_catalog import RegistryFeatureCatalogProvider
from app.ui.view_models.feature_management import AuthorizedRegistryFeatureManagementProvider
from app.ui.view_models.feature_runtime import FeatureRuntimeWorkspaceFactory

APPLICATION_NAME = "OCR Automation"
APPLICATION_VERSION = __version__
ORGANIZATION_NAME = "OCR Automation"


def _application_data_directory() -> Path:
    """Resolve the OS-managed application data directory."""
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    if not location:
        raise RuntimeError("The operating system did not provide an application data path.")
    return Path(location)


def bootstrap_application(
    argv: Sequence[str] | None = None,
    *,
    authenticate: bool = True,
) -> tuple[QApplication, ApplicationWindow]:
    """Compose the desktop app and require first-run setup/sign-in by default.

    ``authenticate=False`` exists for isolated tests and presentation previews only;
    the production process entry point must retain the secure default.
    """
    application = QApplication.instance()
    if application is None:
        application = QApplication(list(argv or []))
    application.setApplicationName(APPLICATION_NAME)
    application.setApplicationVersion(APPLICATION_VERSION)
    application.setOrganizationName(ORGANIZATION_NAME)

    data_directory = _application_data_directory()
    configure_logging(data_directory / "logs")
    runtime = ApplicationRuntime(
        config=ConfigManager(data_directory / "config.json"),
        event_bus=EventBus(),
        service_registry=ServiceRegistry(),
    )
    runtime.initialize()
    register_document_processing_services(runtime.service_registry)
    application.aboutToQuit.connect(runtime.shutdown)

    database_path = data_directory / "database" / "ocr_automation.sqlite3"
    registry_repository = SQLiteFeatureRegistryRepository(database_path)
    user_repository = SQLiteUserRepository(database_path)
    configuration_repository = SQLiteFeatureConfigurationRepository(database_path)
    session_manager = SessionManager()
    audit_service = SecurityAuditService(user_repository)
    authorization = RbacAuthorizationService(user_repository, session_manager, audit_service)
    authentication_manager = AuthenticationManager(
        user_repository, authorization=authorization, audit_service=audit_service
    )

    current_user: UserIdentity | None = None
    if authenticate:
        if not user_repository.has_users():
            setup_dialog = InitialAdministratorDialog(authentication_manager)
            if setup_dialog.exec() != QDialog.DialogCode.Accepted:
                runtime.shutdown()
                raise ApplicationError("AUTH_SETUP_CANCELLED", "Initial administrator setup was cancelled.")
        login_dialog = LoginDialog(authentication_manager)
        if login_dialog.exec() != QDialog.DialogCode.Accepted or login_dialog.identity is None:
            runtime.shutdown()
            raise ApplicationError("AUTH_LOGIN_CANCELLED", "Sign-in was cancelled.")
        current_user = login_dialog.identity
        session = session_manager.create(current_user)
        # Keep the process-local session manager alive for the lifetime of QApplication.
        application._ocr_session_manager = session_manager  # type: ignore[attr-defined]
        application.setProperty("ocr_session_id", session.session_id)

        def close_user_session() -> None:
            session_manager.revoke(session.session_id)
            audit_service.record(
                actor_id=current_user.user_id, action="logout",
                target_user_id=current_user.user_id, outcome="success",
            )

        application.aboutToQuit.connect(close_user_session)

    # Installed feature packages live in OS-managed application data, never beside
    # the editable source tree. This prevents installation from colliding with
    # features/tax_invoice in a source checkout.
    feature_root = data_directory / "features" / "installed"
    feature_root.mkdir(parents=True, exist_ok=True)
    publisher_repository = SQLitePublisherTrustRepository(database_path)
    publisher_trust_manager = PublisherTrustManager(
        repository=publisher_repository, authorization=authorization, event_bus=runtime.event_bus,
    )
    runtime.service_registry.register("publisher.trust", publisher_trust_manager, version="1.0.0")
    feature_configuration_manager = FeatureConfigurationManagerService(
        registry=registry_repository, configurations=configuration_repository,
        authorization=authorization, event_bus=runtime.event_bus,
    )
    runtime.service_registry.register("feature.configuration", feature_configuration_manager, version="1.0.0")
    package_verifier = PackageVerifier(publisher_trust=publisher_trust_manager)
    feature_migration_engine = FeatureDataMigrationEngine(
        configurations=configuration_repository, authorization=authorization,
        registry=registry_repository, data_root=data_directory / "database" / "features",
        backup_root=data_directory / "backups" / "migrations",
        verifier=package_verifier, event_bus=runtime.event_bus,
    )
    runtime.service_registry.register("feature.migrations", feature_migration_engine, version="1.0.0")
    feature_health_manager = FeatureHealthCheckManager(
        registry=registry_repository, configurations=configuration_repository,
        authorization=authorization, services=runtime.service_registry.provider,
        verifier=package_verifier, data_root=data_directory / "database" / "features",
        event_bus=runtime.event_bus,
    )
    runtime.service_registry.register("feature.health", feature_health_manager, version="1.0.0")
    feature_rollback_coordinator = FeatureRollbackCoordinator(
        registry=registry_repository, authorization=authorization,
        backup_root=data_directory / "backups" / "feature_rollback",
        verifier=package_verifier, event_bus=runtime.event_bus,
    )
    runtime.service_registry.register("feature.rollback", feature_rollback_coordinator, version="1.0.0")
    # Restore only prepared, independently verified checkpoints before exposing feature management.
    feature_rollback_coordinator.recover_pending()
    feature_manager = FeatureManagerService(
        feature_root=feature_root,
        repository=registry_repository,
        authorization=authorization,
        service_provider=runtime.service_registry.provider,
        event_bus=runtime.event_bus,
        verifier=package_verifier,
        backup_root=data_directory / "backups" / "features",
        quarantine_root=data_directory / "quarantine" / "packages",
        health_check_manager=feature_health_manager,
        rollback_coordinator=feature_rollback_coordinator,
    )
    actor_id = current_user.user_id if current_user is not None else "anonymous"
    feature_runtime = FeatureRuntimeManager(
        feature_manager=feature_manager,
        services=runtime.service_registry.provider,
        event_bus=runtime.event_bus,
    )
    workspace_factory = FeatureRuntimeWorkspaceFactory(feature_runtime, actor_id, runtime.event_bus)
    application.aboutToQuit.connect(feature_runtime.shutdown_all)
    main_window = ApplicationWindow(
        feature_catalog=RegistryFeatureCatalogProvider(feature_manager, user_id=actor_id),
        workspace_factory=workspace_factory,
        feature_management_provider=AuthorizedRegistryFeatureManagementProvider(
            registry_repository, authorization, actor_id
        ),
        feature_manager=feature_manager,
        publisher_trust_manager=publisher_trust_manager,
        feature_configuration_manager=feature_configuration_manager,
        authorization=authorization,
        current_user=current_user,
        authentication_manager=authentication_manager if current_user is not None else None,
    )
    return application, main_window
