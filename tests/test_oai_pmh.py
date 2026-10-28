import importlib.util
import io
import sys
from pathlib import Path

import pytest
import requests
import urllib3

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src" / "harvesting"


def load_module(file_name, module_name):
    # The source files have hyphens in their names, so they can't be imported normally.
    spec = importlib.util.spec_from_file_location(module_name, SOURCE_DIR / file_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oai_pmh = load_module("oai-pmh.py", "oai_pmh")
oai_pmh_cli = load_module("oai-pmh-cli.py", "oai_pmh_cli")
OAIClient = oai_pmh.OAIClient
OAIError = oai_pmh.OAIError

OAI = '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">{}</OAI-PMH>'


def header(identifier, deleted=False):
    status = ' status="deleted"' if deleted else ""
    return f"<header{status}><identifier>{identifier}</identifier></header>"


def page(*headers, token=None):
    token_xml = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return OAI.format(f"<ListIdentifiers>{''.join(headers)}{token_xml}</ListIdentifiers>")


class FakeResponse:
    def __init__(self, xml):
        self.raw = io.BytesIO(xml.encode())

    def raise_for_status(self):
        pass

    def close(self):
        pass


@pytest.fixture
def serve(monkeypatch):
    """Serve the given XML documents in order and record the request params."""

    def install(*documents):
        remaining = list(documents)
        requests_made = []

        def fake_get(self, url, params=None, **kwargs):
            requests_made.append(params)
            return FakeResponse(remaining.pop(0))

        monkeypatch.setattr(requests.Session, "get", fake_get)
        return requests_made

    return install


def test_follows_resumption_tokens(serve):
    requests_made = serve(page(header("a"), header("b"), token="T1"), page(header("c")))
    assert list(OAIClient("http://x/oai").iter_identifiers()) == ["a", "b", "c"]
    assert requests_made[1] == {"verb": "ListIdentifiers", "resumptionToken": "T1"}


def test_skips_deleted_records(serve):
    serve(page(header("a"), header("gone", deleted=True)))
    assert list(OAIClient("http://x/oai").iter_identifiers()) == ["a"]


def test_passes_set_and_from_date(serve):
    requests_made = serve(page(header("a")))
    list(OAIClient("http://x/oai").iter_identifiers(oai_set="s", from_date="2026-10-01"))
    assert requests_made[0]["set"] == "s"
    assert requests_made[0]["from"] == "2026-10-01"


def test_no_records_match_is_an_empty_result(serve):
    serve(OAI.format('<error code="noRecordsMatch"/>'))
    assert list(OAIClient("http://x/oai").iter_identifiers()) == []


def test_other_oai_errors_are_raised(serve):
    serve(OAI.format('<error code="badArgument">The set does not exist</error>'))
    with pytest.raises(OAIError) as excinfo:
        list(OAIClient("http://x/oai").iter_identifiers(oai_set="nope"))
    assert excinfo.value.code == "badArgument"
    assert "The set does not exist" in str(excinfo.value)


def test_truncated_xml_is_an_oai_error(serve):
    serve(page(header("a"))[:-30])
    with pytest.raises(OAIError) as excinfo:
        list(OAIClient("http://x/oai").iter_identifiers())
    assert excinfo.value.code == "invalidXml"


def test_dropped_connection_is_a_requests_error(monkeypatch):
    class DroppingRaw:
        def __init__(self):
            self.chunks = [page(header("a")).encode()[:60]]

        def read(self, size=-1):
            if self.chunks:
                return self.chunks.pop()
            raise urllib3.exceptions.ProtocolError("Connection broken")

    response = FakeResponse("")
    response.raw = DroppingRaw()
    monkeypatch.setattr(requests.Session, "get", lambda *args, **kwargs: response)
    with pytest.raises(requests.RequestException):
        list(OAIClient("http://x/oai").iter_identifiers())


def test_blank_resumption_token_ends_the_harvest(serve):
    requests_made = serve(OAI.format("<ListIdentifiers>" + header("a") + "<resumptionToken>\n </resumptionToken></ListIdentifiers>"))
    assert list(OAIClient("http://x/oai").iter_identifiers()) == ["a"]
    assert len(requests_made) == 1


def test_retrieve_identifiers_writes_one_per_line(serve, tmp_path):
    serve(page(header("a"), header("b")))
    output = tmp_path / "ids.txt"
    oai_pmh.retrieve_identifiers("http://x/oai", output)
    assert output.read_text() == "a\nb\n"


def test_retrieve_identifiers_reports_each_one_and_counts(serve):
    serve(page(header("a"), header("b")))
    seen = []
    assert oai_pmh.retrieve_identifiers("http://x/oai", on_identifier=seen.append) == 2
    assert seen == ["a", "b"]


def test_retrieve_records_writes_one_file_per_record(serve, tmp_path):
    record = "<record><header><identifier>oai:x:1</identifier></header></record>"
    serve(OAI.format(f"<ListRecords>{record}</ListRecords>"))
    seen = []
    assert oai_pmh.retrieve_records("http://x/oai", tmp_path, on_record=seen.append) == 1
    assert len(seen) == 1
    assert "oai:x:1" in (tmp_path / "oai_x_1_oai_dc.xml").read_text()


def test_cli_show_identifiers_prints_them(serve, capsys):
    serve(page(header("a"), header("b")))
    assert oai_pmh_cli.cli_retrieve_identifiers("http://x/oai", show_identifiers=True) == 2
    assert capsys.readouterr().out == "a\nb\n"


def test_cli_progress_mode_writes_the_file(serve, tmp_path):
    serve(page(header("a"), header("b")))
    output = tmp_path / "ids.txt"
    assert oai_pmh_cli.cli_retrieve_identifiers("http://x/oai", output_file=str(output)) == 2
    assert output.read_text() == "a\nb\n"


def test_identifiers_command_passes_its_options_on(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(oai_pmh_cli, "cli_retrieve_identifiers", lambda url, **kwargs: seen.update(url=url, **kwargs))
    output = str(tmp_path / "ids.txt")
    monkeypatch.setattr(
        sys, "argv", ["oai-pmh", "identifiers", "http://x/oai", "--set", "s", "--from", "2026-10-01", "-m", "oai_datacite", "--output-file", output]
    )
    oai_pmh_cli.main()
    assert seen == {
        "url": "http://x/oai",
        "output_file": output,
        "oai_set": "s",
        "metadata_prefix": "oai_datacite",
        "from_date": "2026-10-01",
        "show_identifiers": False,
        "quiet": False,
    }


def test_records_command_passes_its_options_on(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(oai_pmh_cli, "cli_retrieve_records", lambda url, output_dir, **kwargs: seen.update(url=url, output_dir=output_dir, **kwargs))
    output_dir = str(tmp_path / "records")
    monkeypatch.setattr(
        sys, "argv", ["oai-pmh", "records", "http://x/oai", "--set", "s", "--from", "2026-10-01", "--output-dir", output_dir]
    )
    oai_pmh_cli.main()
    assert seen == {
        "url": "http://x/oai",
        "output_dir": output_dir,
        "oai_set": "s",
        "metadata_prefix": "oai_dc",
        "from_date": "2026-10-01",
    }


def test_cli_reports_oai_errors_and_exits(monkeypatch, serve, tmp_path):
    serve(OAI.format('<error code="badArgument">The set does not exist</error>'))
    monkeypatch.setattr(
        sys, "argv", ["oai-pmh", "identifiers", "http://x/oai", "--set", "nope", "--output-file", str(tmp_path / "ids.txt")]
    )
    with pytest.raises(SystemExit) as excinfo:
        oai_pmh_cli.main()
    assert excinfo.value.code == 1
