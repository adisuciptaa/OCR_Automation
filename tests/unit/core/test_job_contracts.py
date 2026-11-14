from dataclasses import FrozenInstanceError

import pytest

from app.core.job_contracts import FileResult, JobProgress, JobRequest, JobResult


def make_request(**overrides):
    values = {
        "job_id": "job-1",
        "feature_id": "tax_invoice",
        "input_paths": ("input/a.pdf",),
        "output_path": "output/result.xlsx",
        "configuration": {"dpi": 300},
        "requested_by": "admin",
        "correlation_id": "corr-1",
    }
    values.update(overrides)
    return JobRequest(**values)


def test_job_request_is_immutable_and_freezes_configuration():
    request = make_request()
    with pytest.raises(TypeError):
        request.configuration["dpi"] = 200
    with pytest.raises(FrozenInstanceError):
        request.job_id = "other"


def test_job_request_requires_input_and_non_empty_identity():
    with pytest.raises(ValueError):
        make_request(input_paths=())
    with pytest.raises(ValueError):
        make_request(requested_by=" ")


def test_job_progress_rejects_invalid_counts():
    with pytest.raises(ValueError):
        JobProgress("job-1", "ocr", None, 2, 1, "OCR_RUNNING", "Processing")


def test_file_result_requires_error_code_for_failure():
    with pytest.raises(ValueError):
        FileResult("a.pdf", "failed", {}, {})


def test_job_result_counts_must_match_file_results():
    file_result = FileResult("a.pdf", "success", {"tax_invoice_number": "010"}, {})
    with pytest.raises(ValueError):
        JobResult("job-1", "completed", 1, 0, 0, 0, (file_result,), None)


def test_job_result_accepts_consistent_counts():
    file_result = FileResult("a.pdf", "review", {}, {}, warnings=("Low confidence",))
    result = JobResult("job-1", "completed_with_warnings", 1, 0, 0, 1, (file_result,), None)
    assert result.review_files == 1


def test_job_request_recursively_freezes_nested_configuration():
    request = make_request(configuration={"rules": {"regions": ["top", "full"]}})
    with pytest.raises(TypeError):
        request.configuration["rules"]["new"] = True
    with pytest.raises(AttributeError):
        request.configuration["rules"]["regions"].append("bottom")
