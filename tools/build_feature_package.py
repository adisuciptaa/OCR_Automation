"""Build and sign a ZIP feature package from a source feature directory."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sign_feature_package import sign_package  # noqa: E402


def build_package(feature_id: str, publisher_id: str, private_key: Path, output: Path) -> Path:
    source = ROOT / "features" / feature_id
    if not (source / "manifest.json").is_file():
        raise FileNotFoundError(f"Feature manifest not found: {source / 'manifest.json'}")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{feature_id}-package-") as temporary:
        staging = Path(temporary) / feature_id
        shutil.copytree(source, staging, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".pytest_cache", "tests"
        ))
        manifest_path = staging / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["publisher_id"] = publisher_id
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        sign_package(staging, publisher_id, private_key.resolve(strict=True))
        temporary_zip = output.with_suffix(output.suffix + ".tmp")
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(feature_id) / path.relative_to(staging))
        temporary_zip.replace(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature_id", help="Feature folder ID, e.g. tax_invoice")
    parser.add_argument("--publisher-id", default="ocr_automation_dev")
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_package(args.feature_id, args.publisher_id, args.private_key, args.output)
    print(f"Signed package created: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
