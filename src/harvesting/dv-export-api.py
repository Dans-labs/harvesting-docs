# Metadata export API for Dataverse repositories
#
# Enables export of dataset metadata from Dataverse repositories
# Especially useful for the non-XML exporters that are not available via OAI,
# like the `dataverse_json` exporter, that contains all metadata fields of a dataset

import requests
import json
import os
import random
import re
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REQUEST_TIMEOUT = 60  # seconds
MAX_RETRIES = 3
DEFAULT_DELAY = 0.0


class DataverseExportClient:
    def __init__(self, base_url, timeout=REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        # Retries throttling and transient server errors, honouring Retry-After.
        retry = Retry(total=MAX_RETRIES, backoff_factor=1, status_forcelist=(429, 502, 503, 504))
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def request(self, params):
        export_url = f"{self.base_url}/api/datasets/export"
        response = self.session.get(export_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response

    def _export(self, dataset_pid, exporter):
        return self.request({"exporter": exporter, "persistentId": dataset_pid})

    def export_dataset_metadata(self, dataset_pid, exporter):
        response = self._export(dataset_pid, exporter)
        if _is_json(response):
            return response.json()
        return response.text

    def export_dataset_metadata_for_pid(
        self, dataset_pid, exporter, dirname, quiet=False
    ):
        response = self._export(dataset_pid, exporter)
        if _is_json(response):
            content, extension = json.dumps(response.json(), indent=4).encode("utf-8"), "json"
        else:
            # Raw bytes: an XML prolog may declare an encoding other than the one requests guesses.
            content = response.content
            extension = "xml" if "xml" in response.headers.get("Content-Type", "") else "txt"
        file_name = f"{get_save_dir_or_file_name(dataset_pid)}.{get_save_dir_or_file_name(exporter)}.{extension}"
        filename = os.path.join(dirname, file_name)
        os.makedirs(dirname, exist_ok=True)
        if not quiet:
            print(f"Writing metadata to file: {filename}")
        with open(filename, "wb") as f_out:
            f_out.write(content)

    def export_dataset_metadata_for_pids(
        self, pid_file, exporter, dirname, quiet=False, before_pid=None, after_pid=None, delay=DEFAULT_DELAY
    ):
        """Export every PID in the file; return a list of (pid, error) for the ones that failed.

        delay scales the randomized pause between PIDs (see nice_delay); 0 means no pause.
        before_pid(pid) is called first and stops the export when it returns True.
        after_pid(pid, error) is called afterwards, with error None on success.
        """
        count = count_pids(pid_file)
        if not quiet:
            print(f"Total PIDs to process: {count}")
        failures = []
        first = True
        with open(pid_file, "r") as f:
            for line in f:
                dataset_pid = line.strip()
                if not dataset_pid:
                    continue
                if not first:
                    nice_delay(delay)
                first = False
                if before_pid and before_pid(dataset_pid):
                    break
                if not quiet:
                    print(f"Processing dataset PID: {dataset_pid}")
                error = None
                try:
                    self.export_dataset_metadata_for_pid(
                        dataset_pid, exporter, dirname, quiet=quiet
                    )
                except requests.RequestException as request_error:
                    error = request_error
                    failures.append((dataset_pid, error))
                    if not quiet:
                        print(f"Failed to export {dataset_pid}: {error}")
                if after_pid:
                    after_pid(dataset_pid, error)
        return failures


def dv_export_dataset_metadata(dataverse_url, dataset_pid, exporter):
    """Backward-compatible wrapper around :class:`DataverseExportClient`."""
    return DataverseExportClient(dataverse_url).export_dataset_metadata(dataset_pid, exporter)


def export_dataset_metadata_for_pid(
    url, dataset_pid, exporter, dirname, quiet=False, client=None
):
    client = client or DataverseExportClient(url)
    client.export_dataset_metadata_for_pid(dataset_pid, exporter, dirname, quiet=quiet)


def export_dataset_metadata_for_pids(
    url, pid_file, exporter, dirname, quiet=False, before_pid=None, after_pid=None, delay=0
):
    client = DataverseExportClient(url)
    return client.export_dataset_metadata_for_pids(
        pid_file, exporter, dirname, quiet=quiet, before_pid=before_pid, after_pid=after_pid, delay=delay
    )


def nice_delay(scale_max_delay=DEFAULT_DELAY):
    """Sleep for a short, randomized delay to avoid hammering the server."""
    if scale_max_delay <= 0:
        return
    delay = random.uniform(0.1, 0.3)
    delay += min(random.lognormvariate(0.1, 0.3), 0.7)
    # total delay now ranges from 0.1 to 1.0
    delay *= scale_max_delay
    time.sleep(delay)


def _is_json(response):
    return "application/json" in response.headers.get("Content-Type", "")


def count_pids(pid_file):
    count = 0
    with open(pid_file, "r") as f:
        for line in f:
            # we just test for non-empty, we do not validate if the line is a pid
            if line.strip():
                count += 1
    return count


def get_save_dir_or_file_name(name):
    # Replace path separators and characters that are invalid in Windows file names.
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
