import importlib.util
import json
import logging
import signal
import sys
from pathlib import Path

import pytest
import requests

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src" / "harvesting"


def load_module(file_name, module_name):
    # The source files have hyphens in their names, so they can't be imported normally.
    spec = importlib.util.spec_from_file_location(module_name, SOURCE_DIR / file_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dv_export = load_module("dv-export-api.py", "dv_export_api")
DataverseExportClient = dv_export.DataverseExportClient


@pytest.fixture
def dv_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return load_module("dv-export-api-cli.py", "dv_export_api_cli")


class FakeResponse:
    def __init__(self, body, content_type="application/json", content=None):
        self.body = body
        self.headers = {"Content-Type": content_type}
        self._content = content

    @property
    def content(self):
        if self._content is not None:
            return self._content
        return self.body.encode("utf-8") if isinstance(self.body, str) else json.dumps(self.body).encode("utf-8")

    def raise_for_status(self):
        pass

    def json(self):
        return self.body

    @property
    def text(self):
        return self.body


@pytest.fixture
def serve(monkeypatch):
    """Serve the given responses in order and record each (url, params) request."""

    def install(*responses):
        remaining = list(responses)
        requests_made = []

        def fake_get(self, url, params=None, **kwargs):
            requests_made.append((url, params))
            return remaining.pop(0)

        monkeypatch.setattr(requests.Session, "get", fake_get)
        return requests_made

    return install


def test_export_requests_the_exporter_for_the_pid(serve):
    requests_made = serve(FakeResponse({"id": 1}))
    DataverseExportClient("https://dv.example").export_dataset_metadata("doi:10.1/x", "dataverse_json")
    assert requests_made == [
        ("https://dv.example/api/datasets/export", {"exporter": "dataverse_json", "persistentId": "doi:10.1/x"})
    ]


def test_json_responses_are_parsed(serve):
    serve(FakeResponse({"id": 1}))
    assert DataverseExportClient("https://dv.example").export_dataset_metadata("doi:10.1/x", "dataverse_json") == {"id": 1}


def test_other_responses_are_returned_as_text(serve):
    serve(FakeResponse("<xml/>", content_type="application/xml"))
    assert DataverseExportClient("https://dv.example").export_dataset_metadata("doi:10.1/x", "ddi") == "<xml/>"


def test_http_errors_are_raised(monkeypatch):
    class Failing(FakeResponse):
        def raise_for_status(self):
            raise requests.HTTPError("404")

    monkeypatch.setattr(requests.Session, "get", lambda *args, **kwargs: Failing({}))
    with pytest.raises(requests.HTTPError):
        DataverseExportClient("https://dv.example").export_dataset_metadata("doi:10.1/x", "dataverse_json")


def test_requests_use_a_timeout_and_retry_transient_errors(monkeypatch):
    seen = {}

    def fake_get(self, url, params=None, **kwargs):
        seen.update(kwargs)
        return FakeResponse({})

    monkeypatch.setattr(requests.Session, "get", fake_get)
    client = DataverseExportClient("https://dv.example")
    client.export_dataset_metadata("doi:10.1/x", "dataverse_json")
    assert seen["timeout"] == dv_export.REQUEST_TIMEOUT
    retry = client.session.get_adapter("https://dv.example").max_retries
    assert retry.total == dv_export.MAX_RETRIES
    assert 503 in retry.status_forcelist


def test_json_metadata_is_written_indented_to_a_file_named_after_the_pid(serve, tmp_path):
    serve(FakeResponse({"id": 1}))
    output_dir = tmp_path / "new" / "dir"
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pid(
        "doi:10.1/x", "dataverse_json", str(output_dir), quiet=True
    )
    written = output_dir / "doi_10.1_x.dataverse_json.json"
    assert json.loads(written.read_text()) == {"id": 1}
    assert written.read_text() == json.dumps({"id": 1}, indent=4)


def test_text_metadata_is_written_as_is(serve, tmp_path):
    serve(FakeResponse("<xml/>", content_type="application/xml"))
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pid(
        "doi:10.1/x", "ddi", str(tmp_path), quiet=True
    )
    assert (tmp_path / "doi_10.1_x.ddi.xml").read_text() == "<xml/>"


def test_other_text_gets_a_txt_extension(serve, tmp_path):
    serve(FakeResponse("plain", content_type="text/plain"))
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pid(
        "doi:10.1/x", "custom", str(tmp_path), quiet=True
    )
    assert (tmp_path / "doi_10.1_x.custom.txt").read_text() == "plain"


def test_non_ascii_xml_is_written_as_utf8(serve, tmp_path):
    serve(FakeResponse("<name>Zoë</name>", content_type="application/xml"))
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pid(
        "doi:10.1/x", "ddi", str(tmp_path), quiet=True
    )
    assert (tmp_path / "doi_10.1_x.ddi.xml").read_bytes() == "<name>Zoë</name>".encode("utf-8")


def test_xml_is_written_byte_for_byte(serve, tmp_path):
    raw = '<?xml version="1.0" encoding="ISO-8859-1"?><n>Zoë</n>'.encode("iso-8859-1")
    serve(FakeResponse("misdecoded", content_type="application/xml", content=raw))
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pid(
        "doi:10.1/x", "ddi", str(tmp_path), quiet=True
    )
    assert (tmp_path / "doi_10.1_x.ddi.xml").read_bytes() == raw


def test_a_trailing_slash_in_the_base_url_is_ignored(serve):
    requests_made = serve(FakeResponse({}))
    DataverseExportClient("https://dv.example/").export_dataset_metadata("doi:10.1/x", "dataverse_json")
    assert requests_made[0][0] == "https://dv.example/api/datasets/export"


def test_json_that_is_not_an_object_is_written(serve, tmp_path):
    serve(FakeResponse([1, 2]))
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pid(
        "doi:10.1/x", "dataverse_json", str(tmp_path), quiet=True
    )
    assert json.loads((tmp_path / "doi_10.1_x.dataverse_json.json").read_text()) == [1, 2]


def test_the_exporter_cannot_escape_the_output_directory(serve, tmp_path):
    serve(FakeResponse({}))
    output_dir = tmp_path / "out"
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pid(
        "doi:10.1/x", "../../evil", str(output_dir), quiet=True
    )
    assert [p.parent for p in tmp_path.rglob("*.json")] == [output_dir]


def test_progress_is_printed_unless_quiet(serve, tmp_path, capsys):
    serve(FakeResponse({}), FakeResponse({}))
    client = DataverseExportClient("https://dv.example")
    client.export_dataset_metadata_for_pid("doi:10.1/x", "dataverse_json", str(tmp_path))
    assert "Writing metadata to file" in capsys.readouterr().out
    client.export_dataset_metadata_for_pid("doi:10.1/x", "dataverse_json", str(tmp_path), quiet=True)
    assert capsys.readouterr().out == ""


def test_pid_file_is_exported_skipping_blank_lines(serve, tmp_path):
    requests_made = serve(FakeResponse({"n": 1}), FakeResponse({"n": 2}))
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("doi:10.1/a\n\n  \ndoi:10.1/b\n")
    output_dir = tmp_path / "out"
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pids(
        str(pid_file), "dataverse_json", str(output_dir), quiet=True
    )
    assert [params["persistentId"] for _, params in requests_made] == ["doi:10.1/a", "doi:10.1/b"]
    assert sorted(p.name for p in output_dir.iterdir()) == [
        "doi_10.1_a.dataverse_json.json",
        "doi_10.1_b.dataverse_json.json",
    ]


def test_a_failing_pid_does_not_stop_the_rest_and_is_reported(monkeypatch, tmp_path):
    class NotFound(FakeResponse):
        def raise_for_status(self):
            raise requests.HTTPError("404")

    responses = [FakeResponse({"n": 1}), NotFound({}), FakeResponse({"n": 3})]
    monkeypatch.setattr(requests.Session, "get", lambda *args, **kwargs: responses.pop(0))
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("doi:10.1/a\ndoi:10.1/missing\ndoi:10.1/c\n")
    output_dir = tmp_path / "out"
    failures = DataverseExportClient("https://dv.example").export_dataset_metadata_for_pids(
        str(pid_file), "dataverse_json", str(output_dir), quiet=True
    )
    assert [pid for pid, _ in failures] == ["doi:10.1/missing"]
    assert sorted(p.name for p in output_dir.iterdir()) == [
        "doi_10.1_a.dataverse_json.json",
        "doi_10.1_c.dataverse_json.json",
    ]


def test_pid_hooks_see_every_pid_with_its_outcome(monkeypatch, tmp_path):
    class NotFound(FakeResponse):
        def raise_for_status(self):
            raise requests.HTTPError("404")

    responses = [FakeResponse({}), NotFound({})]
    monkeypatch.setattr(requests.Session, "get", lambda *args, **kwargs: responses.pop(0))
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("doi:10.1/a\n\ndoi:10.1/b\n")
    before, after = [], []
    dv_export.export_dataset_metadata_for_pids(
        "https://dv.example", str(pid_file), "dataverse_json", str(tmp_path / "out"), quiet=True,
        before_pid=before.append, after_pid=lambda pid, error: after.append((pid, type(error))),
    )
    assert before == ["doi:10.1/a", "doi:10.1/b"]
    assert after == [("doi:10.1/a", type(None)), ("doi:10.1/b", requests.HTTPError)]


def test_before_pid_can_stop_the_export(serve, tmp_path):
    requests_made = serve(FakeResponse({}), FakeResponse({}))
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("doi:10.1/a\ndoi:10.1/b\n")
    after = []
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pids(
        str(pid_file), "dataverse_json", str(tmp_path / "out"), quiet=True,
        before_pid=lambda pid: pid == "doi:10.1/b", after_pid=lambda pid, error: after.append(pid),
    )
    assert [params["persistentId"] for _, params in requests_made] == ["doi:10.1/a"]
    assert after == ["doi:10.1/a"]


def test_nice_delay_sleeps_within_the_scaled_range(monkeypatch):
    slept = []
    monkeypatch.setattr(dv_export.time, "sleep", slept.append)
    for _ in range(50):
        dv_export.nice_delay(2)
    assert len(slept) == 50
    assert all(0.2 <= seconds <= 2.0 for seconds in slept)


@pytest.mark.parametrize("scale", [0, -1])
def test_nice_delay_does_nothing_when_the_scale_is_not_positive(monkeypatch, scale):
    slept = []
    monkeypatch.setattr(dv_export.time, "sleep", slept.append)
    dv_export.nice_delay(scale)
    assert slept == []


def test_delay_is_applied_between_pids_but_not_before_the_first(serve, tmp_path, monkeypatch):
    serve(FakeResponse({}), FakeResponse({}), FakeResponse({}))
    delays = []
    monkeypatch.setattr(dv_export, "nice_delay", delays.append)
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("doi:10.1/a\n\ndoi:10.1/b\ndoi:10.1/c\n")
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pids(
        str(pid_file), "dataverse_json", str(tmp_path / "out"), quiet=True, delay=0.5
    )
    assert delays == [0.5, 0.5]


def test_no_delay_by_default(serve, tmp_path, monkeypatch):
    serve(FakeResponse({}), FakeResponse({}))
    delays = []
    monkeypatch.setattr(dv_export, "nice_delay", delays.append)
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("doi:10.1/a\ndoi:10.1/b\n")
    DataverseExportClient("https://dv.example").export_dataset_metadata_for_pids(
        str(pid_file), "dataverse_json", str(tmp_path / "out"), quiet=True
    )
    assert delays == [0]


def test_count_pids_ignores_blank_lines(tmp_path):
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("a\n\n  \nb\n")
    assert dv_export.count_pids(str(pid_file)) == 2


def test_save_names_replace_path_separators():
    assert dv_export.get_save_dir_or_file_name("doi:10.1/x") == "doi_10.1_x"


def test_module_level_wrappers_use_the_given_url(serve, tmp_path):
    requests_made = serve(FakeResponse({}))
    dv_export.export_dataset_metadata_for_pid("https://dv.example", "doi:10.1/x", "dataverse_json", str(tmp_path), quiet=True)
    assert requests_made[0][0] == "https://dv.example/api/datasets/export"


def test_cli_puts_the_output_directory_in_the_current_directory_by_default(dv_cli, monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(dv_cli, "export_dataset_metadata_for_pid", lambda url, pid, exporter, dirname, quiet: seen.update(dirname=dirname))
    monkeypatch.setattr(sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-p", "doi:10.1/x"])
    dv_cli.main()
    assert Path(seen["dirname"]).resolve() == (tmp_path / "metadata_demo.dataverse.org").resolve()


def test_cli_parent_dir_contains_the_output_directory(dv_cli, monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(dv_cli, "export_dataset_metadata_for_pid", lambda url, pid, exporter, dirname, quiet: seen.update(dirname=dirname))
    parent = tmp_path / "exports" / "2026"
    monkeypatch.setattr(
        sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-p", "doi:10.1/x", "--parent-dir", str(parent)]
    )
    dv_cli.main()
    assert Path(seen["dirname"]) == parent / "metadata_demo.dataverse.org"


def test_cli_quiet_pid_file_export_passes_its_options_on(dv_cli, monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(
        dv_cli, "export_dataset_metadata_for_pids",
        lambda url, pid_file, exporter, dirname, quiet, delay: seen.update(
            url=url, pid_file=pid_file, exporter=exporter, quiet=quiet, delay=delay
        ) or [],
    )
    monkeypatch.setattr(
        sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-f", "pids.txt", "-e", "ddi", "-q", "--delay", "0.5"]
    )
    dv_cli.main()
    assert seen == {
        "url": "https://demo.dataverse.org", "pid_file": "pids.txt", "exporter": "ddi", "quiet": True, "delay": 0.5
    }


def test_cli_delay_defaults_to_a_short_pause(dv_cli, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        dv_cli, "cli_export_dataset_metadata_for_pids",
        lambda url, pid_file, exporter, dirname, delay: seen.update(delay=delay) or [],
    )
    monkeypatch.setattr(sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-f", "pids.txt"])
    dv_cli.main()
    assert seen == {"delay": dv_cli.DEFAULT_DELAY}


def test_cli_quiet_pid_file_export_exits_nonzero_when_some_pids_fail(dv_cli, monkeypatch):
    monkeypatch.setattr(
        dv_cli, "export_dataset_metadata_for_pids", lambda *args, **kwargs: [("doi:10.1/x", "boom")]
    )
    monkeypatch.setattr(sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-f", "pids.txt", "-q"])
    with pytest.raises(SystemExit) as excinfo:
        dv_cli.main()
    assert excinfo.value.code == 1


def test_cli_requires_a_pid_or_pid_file(dv_cli, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["dv-export-api", "https://demo.dataverse.org"])
    with pytest.raises(SystemExit) as excinfo:
        dv_cli.main()
    assert excinfo.value.code == 2
    assert "--pid" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("url", ["demo.dataverse.org", "ftp://demo.dataverse.org", "https://"])
def test_cli_rejects_urls_without_an_http_scheme_and_host(dv_cli, monkeypatch, tmp_path, url):
    monkeypatch.setattr(sys, "argv", ["dv-export-api", url, "-p", "doi:10.1/x"])
    with pytest.raises(SystemExit) as excinfo:
        dv_cli.main()
    assert excinfo.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_cli_reports_http_errors_for_a_single_pid_and_exits(dv_cli, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise requests.HTTPError("404 Not Found")

    monkeypatch.setattr(dv_cli, "export_dataset_metadata_for_pid", fail)
    monkeypatch.setattr(sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-p", "doi:10.1/x"])
    with pytest.raises(SystemExit) as excinfo:
        dv_cli.main()
    assert excinfo.value.code == 1
    assert "404 Not Found" in capsys.readouterr().err


def test_importing_the_cli_has_no_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = signal.getsignal(signal.SIGINT)
    load_module("dv-export-api-cli.py", "dv_export_api_cli_import")
    assert signal.getsignal(signal.SIGINT) == before
    assert list(tmp_path.iterdir()) == []


def test_log_file_is_only_created_when_something_is_logged(dv_cli, tmp_path, monkeypatch):
    # basicConfig does nothing when the root logger already has handlers, as it does under pytest.
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", root.level)
    dv_cli._configure_logging()
    try:
        assert not (tmp_path / dv_cli.LOG_FILE).exists()
        dv_cli.logger.error("boom")
        assert (tmp_path / dv_cli.LOG_FILE).exists()
    finally:
        for handler in root.handlers:
            handler.close()


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTSTP is not available")
def test_pause_handler_is_only_installed_during_the_context(dv_cli):
    before = signal.getsignal(signal.SIGTSTP)
    with dv_cli.pause_on_signal():
        assert signal.getsignal(signal.SIGTSTP) == dv_cli._request_pause
    assert signal.getsignal(signal.SIGTSTP) == before


def test_interactive_export_reports_failures_and_still_exports_the_rest(dv_cli, monkeypatch, tmp_path):
    class NotFound(FakeResponse):
        def raise_for_status(self):
            raise requests.HTTPError("404")

    responses = [FakeResponse({"n": 1}), NotFound({}), FakeResponse({"n": 3})]
    monkeypatch.setattr(requests.Session, "get", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(dv_cli.Prompt, "ask", lambda *args, **kwargs: "y")
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("doi:10.1/a\ndoi:10.1/missing\ndoi:10.1/c\n")
    output_dir = tmp_path / "out"
    failures = dv_cli.cli_export_dataset_metadata_for_pids(
        "https://dv.example", str(pid_file), "dataverse_json", str(output_dir), delay=0
    )
    assert [pid for pid, _ in failures] == ["doi:10.1/missing"]
    assert sorted(p.name for p in output_dir.iterdir()) == [
        "doi_10.1_a.dataverse_json.json",
        "doi_10.1_c.dataverse_json.json",
    ]


def test_cli_exits_nonzero_when_the_interactive_export_had_failures(dv_cli, monkeypatch):
    monkeypatch.setattr(
        dv_cli, "cli_export_dataset_metadata_for_pids", lambda *args, **kwargs: [("doi:10.1/x", "boom")]
    )
    monkeypatch.setattr(sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-f", "pids.txt"])
    with pytest.raises(SystemExit) as excinfo:
        dv_cli.main()
    assert excinfo.value.code == 1


def test_interactive_output_escapes_markup_in_pids_and_errors(dv_cli, monkeypatch, tmp_path, capsys):
    def fail(*args, **kwargs):
        raise requests.HTTPError("bad [/oops] reply")

    monkeypatch.setattr(requests.Session, "get", fail)
    monkeypatch.setattr(dv_cli.Prompt, "ask", lambda *args, **kwargs: "y")
    pid_file = tmp_path / "pids.txt"
    pid_file.write_text("doi:[bold]x\n")
    failures = dv_cli.cli_export_dataset_metadata_for_pids(
        "https://dv.example", str(pid_file), "dataverse_json", str(tmp_path / "out"), delay=0
    )
    assert len(failures) == 1
    assert "bad [/oops] reply" in capsys.readouterr().out


def test_cli_reports_local_errors_and_exits(dv_cli, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-f", "missing.txt", "-q"])
    with pytest.raises(SystemExit) as excinfo:
        dv_cli.main()
    assert excinfo.value.code == 1
    assert "missing.txt" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "abc"])
def test_cli_rejects_invalid_delays(dv_cli, monkeypatch, value):
    monkeypatch.setattr(
        sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-f", "pids.txt", "--delay", value]
    )
    with pytest.raises(SystemExit) as excinfo:
        dv_cli.main()
    assert excinfo.value.code == 2


def test_cli_accepts_a_zero_delay(dv_cli, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        dv_cli, "cli_export_dataset_metadata_for_pids",
        lambda url, pid_file, exporter, dirname, delay: seen.update(delay=delay) or [],
    )
    monkeypatch.setattr(
        sys, "argv", ["dv-export-api", "https://demo.dataverse.org", "-f", "pids.txt", "--delay", "0"]
    )
    dv_cli.main()
    assert seen == {"delay": 0.0}
