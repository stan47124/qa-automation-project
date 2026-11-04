from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import allure
import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Configure Allure before its plugin creates the listener/file logger."""
    if config.option.collectonly:
        config.option.allure_report_dir = None
        config.option.xmlpath = None
        return
    if config.option.help:
        return
    if config.option.clean_alluredir:
        raise pytest.UsageError("Use a new report directory; --clean-alluredir is disabled.")
    supplied = config.option.allure_report_dir
    if supplied:
        results = Path(supplied).resolve()
    else:
        stamp = datetime.now(timezone(timedelta(hours=3))).strftime("%Y%m%d_%H%M%S")
        results = config.rootpath / "artifacts" / f"{stamp}_{uuid4().hex}" / "allure-results"
    if results.exists() and (not results.is_dir() or any(results.iterdir())):
        raise pytest.UsageError("Allure directory is not empty; choose a new run directory.")
    junit = (
        Path(config.option.xmlpath).resolve()
        if config.option.xmlpath else results.parent / "junit.xml"
    )
    if junit.exists():
        raise pytest.UsageError("JUnit output already exists; choose a new run directory.")
    results.mkdir(parents=True, exist_ok=True)
    junit.parent.mkdir(parents=True, exist_ok=True)
    config.option.allure_report_dir = str(results)
    config.option.xmlpath = str(junit)
    # Captured console/log output is not a sanitized API attachment.
    config.option.attach_capture = False
    config._qa_report_directory = results.parent


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if not report.failed:
        return
    for name, diagnostic in getattr(item, "_qa_failure_diagnostics", {}).items():
        try:
            diagnostic(report.when)
        except Exception as error:
            try:
                allure.attach(type(error).__name__, name=f"{name}: diagnostic unavailable",
                              attachment_type=allure.attachment_type.TEXT)
            except Exception:
                pass
    # Fixtures register only already-created sessions. Never create a driver here.
    for kind, driver in getattr(item, "_qa_drivers", {}).items():
        try:
            if not driver.session_id:
                continue
            png = driver.get_screenshot_as_png()
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Driver did not return PNG")
            allure.attach(
                png, name=f"{kind}: {report.when} failure",
                attachment_type=allure.attachment_type.PNG,
            )
        except Exception as error:
            # Screenshot failure must not replace the original test failure.
            try:
                allure.attach(
                    f"Screenshot unavailable: {type(error).__name__}",
                    name=f"{kind}: screenshot diagnostic",
                    attachment_type=allure.attachment_type.TEXT,
                )
            except Exception:
                pass


def pytest_terminal_summary(terminalreporter):
    directory = getattr(terminalreporter.config, "_qa_report_directory", None)
    if directory is not None:
        terminalreporter.write_line(f"Run reports: {directory}")
