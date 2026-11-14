from __future__ import annotations

from app import main as main_module


class FakeWindow:
    def __init__(self) -> None:
        self.was_shown = False

    def show(self) -> None:
        self.was_shown = True


class FakeApplication:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.event_loop_started = False

    def exec(self) -> int:
        self.event_loop_started = True
        return self.exit_code


def test_main_shows_window_and_returns_qt_exit_code(monkeypatch) -> None:
    application = FakeApplication(exit_code=7)
    window = FakeWindow()
    monkeypatch.setattr(
        main_module,
        "bootstrap_application",
        lambda argv: (application, window),
    )

    result = main_module.main(["ocr-automation"])

    assert result == 7
    assert window.was_shown is True
    assert application.event_loop_started is True


def test_main_returns_one_when_startup_fails(monkeypatch) -> None:
    def fail_bootstrap(argv):
        raise RuntimeError("startup failure")

    monkeypatch.setattr(main_module, "bootstrap_application", fail_bootstrap)

    assert main_module.main(["ocr-automation"]) == 1
