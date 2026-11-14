"""Tax Invoice feature manifest and configuration tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.configuration_manager import FeatureConfigurationManagerService
from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.models import FeatureDescriptor
from features.tax_invoice.config import CONFIGURATION_SCHEMA_VERSION, default_configuration
from features.tax_invoice.entry import TaxInvoiceFeature

FEATURE_ROOT = Path(__file__).resolve().parents[1]


def _schema() -> dict:
    return json.loads((FEATURE_ROOT / "config_schema.json").read_text(encoding="utf-8"))


def test_feature_manifest_loads_with_declared_shared_services() -> None:
    manifest = ManifestLoader().load(FEATURE_ROOT)

    assert manifest.feature_id == "tax_invoice"
    assert manifest.api_contract_version == "2.15.0"
    assert manifest.entry_point == "entry:TaxInvoiceFeature"
    assert {item.service_id for item in manifest.dependencies.services} == {
        "pdf.render",
        "ocr.recognize",
        "image.process",
        "excel.workbook",
        "validation.generic",
    }


def test_configuration_schema_is_supported_and_has_valid_defaults() -> None:
    schema = _schema()
    FeatureConfigurationManagerService._validate_schema_definition(schema)
    defaults = FeatureConfigurationManagerService._defaults(schema)
    FeatureConfigurationManagerService._validate_configuration(schema, defaults)

    assert FeatureConfigurationManagerService._schema_version(schema) == CONFIGURATION_SCHEMA_VERSION
    assert defaults["detection"]["top_region_ratio"] == 0.25
    assert defaults["detection"]["fallback_full_page"] is False
    assert defaults["ocr"]["language"] == "ind+eng"
    assert defaults["processing"]["max_pages_per_document"] == 200
    assert defaults["processing"]["render_dpi"] == 200
    assert defaults["excel"] is None


def test_default_configuration_returns_independent_nested_values() -> None:
    first = default_configuration()
    first["detection"]["marker_phrases"].append("CUSTOM")  # type: ignore[index, union-attr]

    second = default_configuration()
    assert "CUSTOM" not in second["detection"]["marker_phrases"]  # type: ignore[index, operator]


def test_configuration_rejects_unknown_fields() -> None:
    schema = _schema()
    values = FeatureConfigurationManagerService._defaults(schema)
    values["detection"]["unexpected"] = True

    with pytest.raises(ApplicationError) as error:
        FeatureConfigurationManagerService._validate_configuration(schema, values)
    assert error.value.code == "FEATURE_CONFIGURATION_INVALID"


def test_configuration_rejects_out_of_range_detection_region() -> None:
    schema = _schema()
    values = FeatureConfigurationManagerService._defaults(schema)
    values["detection"]["top_region_ratio"] = 0.9

    with pytest.raises(ApplicationError) as error:
        FeatureConfigurationManagerService._validate_configuration(schema, values)
    assert error.value.code == "FEATURE_CONFIGURATION_INVALID"


def test_runtime_descriptor_matches_manifest_metadata() -> None:
    manifest = ManifestLoader().load(FEATURE_ROOT)
    descriptor = TaxInvoiceFeature().get_descriptor()

    assert descriptor == FeatureDescriptor(
        manifest.feature_id,
        manifest.display_name,
        manifest.description,
        manifest.version,
        manifest.icon,
        manifest.permissions,
        manifest.license_entitlement,
    )


def test_excel_mapping_configuration_accepts_invoice_whitespace_profile() -> None:
    configuration = {
        "detection": dict(default_configuration()["detection"]),
        "ocr": dict(default_configuration()["ocr"]),
        "processing": dict(default_configuration()["processing"]),
        "excel": {
            "source_workbook_path": "C:/data/tracking.xlsx",
            "worksheet": "Invoices",
            "header_row": 1,
            "data_start_row": 2,
            "source_key_column": "Invoice Number",
            "target_column": "Tax Invoice Number",
            "match_field": "invoice_number",
            "write_field": "tax_invoice_number",
            "key_type": "text",
            "normalization_profile": "remove_whitespace",
            "duplicate_policy": "review",
            "unmatched_policy": "report",
            "overwrite_policy": "empty_only",
        },
    }

    assert TaxInvoiceFeature().validate_configuration(configuration) == configuration


def test_excel_mapping_configuration_rejects_same_match_and_write_field() -> None:
    configuration = {
        "detection": dict(default_configuration()["detection"]),
        "ocr": dict(default_configuration()["ocr"]),
        "processing": dict(default_configuration()["processing"]),
        "excel": {
            "source_workbook_path": "C:/data/tracking.xlsx",
            "worksheet": "Invoices",
            "header_row": 1,
            "data_start_row": 2,
            "source_key_column": "Invoice Number",
            "target_column": "Tax Invoice Number",
            "match_field": "invoice_number",
            "write_field": "invoice_number",
        },
    }

    with pytest.raises(ApplicationError) as error:
        TaxInvoiceFeature().validate_configuration(configuration)
    assert error.value.code == "FEATURE_CONFIGURATION_INVALID"
