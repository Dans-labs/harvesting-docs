# Metadata export API for Dataverse repositories
#
# Enables export of dataset metadata from Dataverse repositories
# Especially useful for the non-XML exporters that are not available via OAI, 
# like the `dataverse_json` exporter, that contains all metadata fields of a dataset

import requests
import json
import os

class DataverseExportClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def request(self, params):
        export_url = f"{self.base_url}/api/datasets/export"
        response = requests.get(export_url, params=params)
        response.raise_for_status()
        return response

    def export_dataset_metadata(self, dataset_pid, exporter):
        response = self.request(
            {"exporter": exporter, "persistentId": dataset_pid}
        )
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def export_dataset_metadata_for_pid(
        self, dataset_pid, exporter, dirname, quiet=False
    ):
        metadata = self.export_dataset_metadata(dataset_pid, exporter)
        filename = f"{dirname}/{get_save_dir_or_file_name(dataset_pid)}.{exporter}.json"
        os.makedirs(dirname, exist_ok=True)
        if not quiet:
            print(f"Writing metadata to file: {filename}")
        with open(filename, "w") as f_out:
            if isinstance(metadata, dict):
                f_out.write(json.dumps(metadata, indent=4))
            else:
                f_out.write(metadata)

    def export_dataset_metadata_for_pids(
        self, pid_file, exporter, dirname, quiet=False
    ):
        count = count_pids(pid_file)
        if not quiet:
            print(f"Total PIDs to process: {count}")
        with open(pid_file, "r") as f:
            for line in f:
                dataset_pid = line.strip()
                if not dataset_pid:
                    continue
                if not quiet:
                    print(f"Processing dataset PID: {dataset_pid}")
                self.export_dataset_metadata_for_pid(
                    dataset_pid, exporter, dirname, quiet=quiet
                )


def dv_export_dataset_metadata(dataverse_url, dataset_pid, exporter):
    """Backward-compatible wrapper around :class:`DataverseExportClient`."""
    return DataverseExportClient(dataverse_url).export_dataset_metadata(dataset_pid, exporter)


def export_dataset_metadata_for_pid(
    url, dataset_pid, exporter, dirname, quiet=False, client=None
):
    client = client or DataverseExportClient(url)
    client.export_dataset_metadata_for_pid(dataset_pid, exporter, dirname, quiet=quiet)


def export_dataset_metadata_for_pids(url, pid_file, exporter, dirname, quiet=False):
    client = DataverseExportClient(url)
    client.export_dataset_metadata_for_pids(pid_file, exporter, dirname, quiet=quiet)

def count_pids(pid_file):
    count = 0
    with open(pid_file, "r") as f:
        for line in f:
            # we just test for non-empty, we do not validate if the line is a pid
            if line.strip():
                count += 1
    return count

def get_save_dir_or_file_name(name):
    return name.replace(':', '_').replace('/', '_')
