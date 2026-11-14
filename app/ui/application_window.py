"""Main application shell owned by the Presentation Layer."""

from __future__ import annotations

import logging

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.security.contracts import AuthorizationService, UserAdministrationService
from app.feature_manager.contracts import FeatureConfigurationManager
from app.security.models import UserIdentity
from app.ui.components.application_header import ApplicationHeader
from app.ui.components.sidebar import Sidebar
from app.ui.navigation.navigation_controller import NavigationController
from app.ui.pages.dashboard.dashboard_page import DashboardPage
from app.ui.pages.feature_cms.feature_cms_page import FeatureCmsPage
from app.ui.pages.settings.settings_page import SettingsPage
from app.ui.pages.users.user_management_page import UserManagementPage
from app.ui.view_models.feature_management import FeatureManagementProvider
from app.ui.view_models.feature_catalog import (
    FeatureCatalogProvider,
    FeatureSummary,
    FeatureWorkspaceFactory,
)

LOGGER = logging.getLogger(__name__)


class ApplicationWindow(QMainWindow):
    """Composes presentation pages and delegates feature workspaces to an adapter."""

    PAGE_CONTEXT = {
        "dashboard": ("Overview", "Your document processing workspace"),
        "feature_cms": ("Feature Management", "Manage installed business capabilities"),
        "settings": ("Settings", "Application preferences and runtime information"),
        "users": ("User Management", "Manage application accounts and roles"),
    }

    def __init__(
        self,
        *,
        feature_catalog: FeatureCatalogProvider | None = None,
        workspace_factory: FeatureWorkspaceFactory | None = None,
        feature_management_provider: FeatureManagementProvider | None = None,
        feature_manager: object | None = None,
        publisher_trust_manager: object | None = None,
        feature_configuration_manager: FeatureConfigurationManager | None = None,
        authorization: AuthorizationService | None = None,
        current_user: UserIdentity | None = None,
        authentication_manager: UserAdministrationService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._feature_catalog = feature_catalog
        self._current_user = current_user
        self._allowed_pages = self._resolve_allowed_pages(current_user)
        self._workspace_factory = workspace_factory
        self._features: tuple[FeatureSummary, ...] = ()
        self._navigation = NavigationController()
        self._workspace_pages: dict[str, QWidget] = {}

        self.setWindowTitle("OCR Automation")
        self.setObjectName("applicationWindow")
        self.resize(1360, 860)
        self.setMinimumSize(1080, 680)

        central = QWidget()
        central.setObjectName("applicationSurface")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = ApplicationHeader()
        root.addWidget(self.header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        horizontal = QHBoxLayout()
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(0)
        self.sidebar = Sidebar()
        self.pages = QStackedWidget()
        self.pages.setObjectName("pageContainer")
        self.dashboard_page = DashboardPage()
        self.feature_cms_page = FeatureCmsPage(
            feature_management_provider,
            configuration_manager=feature_configuration_manager,
            authorization=authorization,
            actor_id=current_user.user_id if current_user is not None else None,
            feature_manager=feature_manager,
            publisher_trust_manager=publisher_trust_manager,
        )
        self.settings_page = SettingsPage()
        can_manage_users = current_user is not None and (
            "user.manage" in current_user.permissions or "*" in current_user.permissions
        )
        self.users_page = (
            UserManagementPage(authentication_manager, current_user.user_id)
            if authentication_manager is not None and current_user is not None and can_manage_users
            else None
        )
        self._page_indexes: dict[str, int] = {}
        self._add_page("dashboard", self.dashboard_page)
        self._add_page("feature_cms", self.feature_cms_page)
        self._add_page("settings", self.settings_page)
        if self.users_page is not None:
            self._add_page("users", self.users_page)

        horizontal.addWidget(self.sidebar)
        horizontal.addWidget(self.pages, 1)
        body_layout.addLayout(horizontal)
        root.addWidget(body, 1)
        self.setCentralWidget(central)
        self._apply_theme()

        self.sidebar.navigation_requested.connect(self.navigate)
        feature_unloaded = getattr(self._workspace_factory, "feature_unloaded", None)
        if feature_unloaded is not None:
            feature_unloaded.connect(self._remove_feature_workspace)
        self.header.sign_out_requested.connect(self.close)
        self.sidebar.feature_requested.connect(self.open_feature)
        self.sidebar.set_page_visibility(self._allowed_pages)
        if current_user is not None:
            self.header.set_user(current_user.display_name, current_user.username)
        self.dashboard_page.feature_selected.connect(self.open_feature)
        self.refresh_features()
        self.navigate("dashboard")

    @staticmethod
    def _resolve_allowed_pages(user: UserIdentity | None) -> frozenset[str]:
        if user is None:
            # Unauthenticated construction is retained for isolated presentation tests.
            return frozenset({"dashboard", "feature_cms", "settings"})
        permissions = set(user.permissions)
        allowed = {"dashboard"}
        if "*" in permissions or "feature.registry.view" in permissions:
            allowed.add("feature_cms")
        if "*" in permissions or "settings.manage" in permissions:
            allowed.add("settings")
        if "*" in permissions or "user.manage" in permissions:
            allowed.add("users")
        return frozenset(allowed)

    def _add_page(self, key: str, page: QWidget) -> None:
        self._page_indexes[key] = self.pages.addWidget(page)

    def refresh_features(self) -> None:
        """Refresh the feature projection without hardcoding business feature IDs."""
        if self._feature_catalog is None:
            features: tuple[FeatureSummary, ...] = ()
        else:
            try:
                features = self._feature_catalog.list_available()
            except Exception:
                LOGGER.exception("Unable to load authorized feature catalog for the GUI.")
                features = ()

        self._features = tuple(features)
        available_ids = {feature.feature_id for feature in self._features}
        for stale_id in tuple(self._workspace_pages):
            if stale_id not in available_ids:
                self._remove_feature_workspace(stale_id)
        self._navigation.set_available_features(self._features)
        self.sidebar.set_features(self._features)
        self.dashboard_page.set_features(self._features)
        current_widget = self.pages.currentWidget()
        current_feature_id = next(
            (feature_id for feature_id, page in self._workspace_pages.items() if page is current_widget),
            None,
        )
        if current_feature_id is not None and not self._navigation.can_open_feature(current_feature_id):
            self.pages.setCurrentWidget(self.dashboard_page)
            self.sidebar.set_active("dashboard")
            title, subtitle = self.PAGE_CONTEXT["dashboard"]
            self.header.set_context(title, subtitle)

    def _remove_feature_workspace(self, feature_id: str) -> None:
        """Dispose a workspace whose feature was disabled, updated, or uninstalled."""
        page = self._workspace_pages.pop(feature_id, None)
        if page is None:
            return
        if self.pages.currentWidget() is page:
            self.pages.setCurrentWidget(self.dashboard_page)
            self.sidebar.set_active("dashboard")
            title, subtitle = self.PAGE_CONTEXT["dashboard"]
            self.header.set_context(title, subtitle)
        self.pages.removeWidget(page)
        page.setParent(None)
        page.deleteLater()

    def navigate(self, page_key: str) -> None:
        self.refresh_features()
        if page_key == "feature_cms":
            self.feature_cms_page.refresh_records()
        elif page_key == "users" and self.users_page is not None:
            self.users_page.refresh()
        if (
            not self._navigation.can_navigate_to_page(page_key)
            or page_key not in self._page_indexes
            or page_key not in self._allowed_pages
        ):
            return
        self.pages.setCurrentIndex(self._page_indexes[page_key])
        self.sidebar.set_active(page_key)
        title, subtitle = self.PAGE_CONTEXT[page_key]
        self.header.set_context(title, subtitle)

    def open_feature(self, feature_id: str) -> None:
        self.refresh_features()
        if not self._navigation.can_open_feature(feature_id):
            LOGGER.warning("Rejected navigation to a feature outside the current catalog.")
            return
        feature = next((item for item in self._features if item.feature_id == feature_id), None)
        if feature is None:
            LOGGER.warning("Rejected navigation to a feature outside the current catalog.")
            return

        page_key = f"feature:{feature_id}"
        page = self._workspace_pages.get(feature_id)
        if page is None:
            if self._workspace_factory is None:
                page = self._workspace_unavailable_page(feature)
            else:
                try:
                    page = self._workspace_factory.create_workspace(feature_id, self.pages)
                except Exception:
                    LOGGER.exception("Feature workspace creation failed: feature_id=%s", feature_id)
                    page = self._workspace_unavailable_page(feature)
            if not isinstance(page, QWidget):
                LOGGER.error("Feature workspace factory returned an invalid widget: %s", feature_id)
                page = self._workspace_unavailable_page(feature)
            self._workspace_pages[feature_id] = page
            self._add_page(page_key, page)

        self.pages.setCurrentWidget(page)
        self.sidebar.set_active(feature_id)
        self.header.set_context(feature.display_name, feature.description)

    @staticmethod
    def _workspace_unavailable_page(feature: FeatureSummary) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 32, 36, 32)
        title = QLabel(f"{feature.display_name} workspace is unavailable")
        title.setObjectName("heroTitle")
        message = QLabel(
            "This feature is present in the authorized catalog, but its workspace "
            "adapter has not been connected to the application composition root."
        )
        message.setObjectName("bodySecondary")
        message.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(message)
        layout.addStretch(1)
        return page

    def closeEvent(self, event: QCloseEvent) -> None:
        """Release feature-owned resources before the main window closes."""
        shutdown = getattr(self._workspace_factory, "shutdown_all", None)
        if callable(shutdown):
            shutdown()
        super().closeEvent(event)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#applicationSurface { background: #f4f6fa; color: #172033; }
            QFrame#sidebar { background: #111b2e; border: 0; }
            QLabel#brandTitle {
                color: #ffffff; font-size: 17px; font-weight: 800; letter-spacing: 1px;
            }
            QLabel#brandCaption, QLabel#sidebarSection, QLabel#sidebarFooter {
                color: #8290a8; font-size: 9px; font-weight: 700; letter-spacing: 1px;
            }
            QLabel#sidebarSection { margin-top: 6px; margin-bottom: 5px; }
            QPushButton#navigationButton, QPushButton#featureNavigationButton {
                text-align: left; color: #b8c3d6; background: transparent; border: 0;
                border-radius: 7px; padding: 11px 12px; font-size: 12px;
            }
            QPushButton#navigationButton:hover, QPushButton#featureNavigationButton:hover {
                background: #1d2b43; color: #ffffff;
            }
            QPushButton#navigationButton:checked, QPushButton#featureNavigationButton:checked {
                background: #263b5b; color: #ffffff; font-weight: 700;
            }
            QFrame#applicationHeader {
                background: #ffffff; border: 0; border-bottom: 1px solid #e6eaf0;
            }
            QLabel#pageTitle { color: #172033; font-size: 17px; font-weight: 700; }
            QLabel#pageSubtitle, QLabel#bodySecondary { color: #68758a; font-size: 11px; }
            QLabel#signedInUser { color: #68758a; font-size: 10px; padding-right: 12px; }
            QPushButton#signOutButton { color: #526078; background: #f0f3f8; border: 0; border-radius: 6px; padding: 7px 10px; font-size: 10px; }
            QPushButton#signOutButton:hover { background: #e3e9f2; }
            QLabel#systemStatus {
                color: #247a58; background: #e8f5ee; border-radius: 10px;
                padding: 7px 11px; font-size: 9px; font-weight: 800;
            }
            QLabel#eyebrow, QLabel#statLabel {
                color: #738096; font-size: 9px; font-weight: 800; letter-spacing: 1px;
            }
            QLabel#heroTitle { color: #172033; font-size: 27px; font-weight: 750; }
            QLabel#sectionTitle { color: #172033; font-size: 17px; font-weight: 700; }
            QFrame#statCard, QFrame#featureCard, QFrame#emptyState, QFrame#noticeCard {
                background: #ffffff; border: 1px solid #e6eaf0; border-radius: 11px;
            }
            QLabel#statValue { color: #172033; font-size: 25px; font-weight: 750; }
            QLabel#statDetail { color: #8994a6; font-size: 10px; }
            QLabel#emptyTitle, QLabel#cardTitle {
                color: #172033; font-size: 14px; font-weight: 700;
            }
            QPushButton#primaryButton {
                color: #ffffff; background: #315b9a; border: 0; border-radius: 6px;
                padding: 9px 12px; font-weight: 650;
            }
            QPushButton#primaryButton:hover { background: #264a80; }
            """
        )
