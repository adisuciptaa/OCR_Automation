"""Non-GUI tests for Tax Invoice workspace integration and worker teardown."""
from __future__ import annotations

import ast
from pathlib import Path

from features.tax_invoice.entry import TaxInvoiceFeature

FEATURE_ROOT = Path(__file__).resolve().parents[1]


class _FakeWorker:
    def __init__(self) -> None:
        self.waited = False

    def wait(self) -> None:
        self.waited = True


def test_manifest_workspace_target_resolves_to_tax_invoice_workspace_class() -> None:
    import json

    manifest = json.loads((FEATURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ui"]["workspace"] == "ui:TaxInvoiceWorkspace"
    tree = ast.parse((FEATURE_ROOT / "ui.py").read_text(encoding="utf-8"))
    class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert "TaxInvoiceWorkspace" in class_names


def test_workspace_uses_exact_three_user_facing_status_labels() -> None:
    tree = ast.parse((FEATURE_ROOT / "ui.py").read_text(encoding="utf-8"))
    status_assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_STATUS_LABELS" for target in node.targets)
    )
    labels = ast.literal_eval(status_assignment.value)
    assert labels == {
        "success": "Success",
        "review": "Need Review",
        "failed": "Failed",
        "skipped": "Need Review",
    }


def test_feature_shutdown_waits_for_registered_background_workers() -> None:
    feature = TaxInvoiceFeature()
    worker = _FakeWorker()
    feature.register_worker(worker)

    feature.shutdown()

    assert worker.waited is True
    assert feature._context is None
    assert feature._active_workers == set()


def test_worker_can_be_unregistered_before_feature_shutdown() -> None:
    feature = TaxInvoiceFeature()
    worker = _FakeWorker()
    feature.register_worker(worker)
    feature.unregister_worker(worker)

    feature.shutdown()

    assert worker.waited is False
