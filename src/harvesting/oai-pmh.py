# Harvesting client code for OAI-PMH (Open Archives Initiative Protocol for Metadata Harvesting) 

import requests
import urllib3
import xml.etree.ElementTree as ET
import os
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NAMESPACE = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("oai", OAI_NAMESPACE)
ET.register_namespace("oai_dc", OAI_DC_NAMESPACE)
ET.register_namespace("dc", DC_NAMESPACE)
ET.register_namespace("xsi", XSI_NAMESPACE)

HEADER_TAG = f"{{{OAI_NAMESPACE}}}header"
IDENTIFIER_TAG = f"{{{OAI_NAMESPACE}}}identifier"
RESUMPTION_TOKEN_TAG = f"{{{OAI_NAMESPACE}}}resumptionToken"
ERROR_TAG = f"{{{OAI_NAMESPACE}}}error"
RECORD_TAG = f"{{{OAI_NAMESPACE}}}record"

REQUEST_TIMEOUT = 60  # seconds
MAX_RETRIES = 3

class OAIError(Exception):
    """The server answered with an OAI-PMH <error> element."""

    def __init__(self, code, message):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


class OAIClient:
    def __init__(self, base_url, timeout=REQUEST_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        # Retries throttling and transient server errors, honouring Retry-After.
        retry = Retry(total=MAX_RETRIES, backoff_factor=1, status_forcelist=(429, 502, 503, 504))
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    @staticmethod
    def _raise_on_error(element):
        # noRecordsMatch means an empty result, not a failure.
        code = element.attrib.get('code')
        if code != 'noRecordsMatch':
            raise OAIError(code, (element.text or '').strip())

    @staticmethod
    def _identifier_from_header(header):
        # Deleted records are skipped; maybe store them somewhere so they can be removed downstream.
        identifier = header.find(IDENTIFIER_TAG)
        deleted = header.attrib.get('status') == 'deleted'
        value = None if deleted or identifier is None or not identifier.text else identifier.text
        header.clear()
        return value

    @staticmethod
    def _live_record(record):
        header = record.find(HEADER_TAG)
        if header is not None and header.attrib.get('status') == 'deleted':
            record.clear()
            return None
        return record

    def request(self, params):
        response = self.session.get(self.base_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as error:
            raise OAIError('invalidXml', str(error)) from error
        for error in root.iter(ERROR_TAG):
            self._raise_on_error(error)
        return root

    @staticmethod
    def _list_params(metadata_prefix, from_date, oai_set):
        params = {'metadataPrefix': metadata_prefix}
        if from_date:
            params['from'] = from_date
        if oai_set:
            params['set'] = oai_set
        return params

    def _iter_pages(self, verb, item_tag, extract, params):
        """Yield one list of items per server-defined page, following resumption tokens."""
        while True:
            items = []
            token = None
            response = self.session.get(
                self.base_url, params={'verb': verb, **params}, stream=True, timeout=self.timeout
            )
            # Parse the XML response for headers and resumption token.
            # Note that while the total number of items may be large, each 'page' will not be huge
            try:
                response.raise_for_status()
                response.raw.decode_content = True
                for _, element in ET.iterparse(response.raw, events=('end',)):
                    if element.tag == item_tag:
                        item = extract(element)
                        if item is not None:
                            items.append(item)
                    elif element.tag == RESUMPTION_TOKEN_TAG:
                        token = (element.text or '').strip() or None
                        element.clear()
                    elif element.tag == ERROR_TAG:
                        self._raise_on_error(element)
            except ET.ParseError as error:
                raise OAIError('invalidXml', str(error)) from error
            except urllib3.exceptions.HTTPError as error:
                # Raw reads bypass requests, so a dropped connection surfaces as a urllib3 error.
                raise requests.exceptions.ChunkedEncodingError(error) from error
            finally:
                response.close()

            if items:
                yield items
            if not token:
                break
            params = {'resumptionToken': token}
    
    def identify(self):
        return self.request({'verb': 'Identify'})
    
    def list_metadata_formats(self):
        return self.request({'verb': 'ListMetadataFormats'})

    def list_sets(self):
        return self.request({'verb': 'ListSets'})
    
    def list_records(self, metadata_prefix='oai_dc', from_date=None, oai_set=None):
        params = {'verb': 'ListRecords', **self._list_params(metadata_prefix, from_date, oai_set)}
        return self.request(params)

    def get_record(self, identifier, metadata_prefix='oai_dc'):
        return self.request({'verb': 'GetRecord', 'identifier': identifier, 'metadataPrefix': metadata_prefix})

    def list_identifiers(self, metadata_prefix='oai_dc', from_date=None, oai_set=None):
        params = {'verb': 'ListIdentifiers', **self._list_params(metadata_prefix, from_date, oai_set)}
        return self.request(params)

    def iter_identifier_pages(self, metadata_prefix='oai_dc', from_date=None, oai_set=None):
        """Yield one list of identifiers for each server-defined OAI-PMH page."""
        params = self._list_params(metadata_prefix, from_date, oai_set)
        yield from self._iter_pages('ListIdentifiers', HEADER_TAG, self._identifier_from_header, params)

    # An iterator to get all identifiers using the resumption token.
    # Example usage:
    # client = OAIClient("https://example.org/oai")
    # for identifier in client.iter_identifiers():
    #     print(identifier)
    def iter_identifiers(self, metadata_prefix='oai_dc', from_date=None, oai_set=None):
        for identifiers in self.iter_identifier_pages(metadata_prefix, from_date=from_date, oai_set=oai_set):
            yield from identifiers

    def iter_record_pages(self, metadata_prefix='oai_dc', from_date=None, oai_set=None):
        params = self._list_params(metadata_prefix, from_date, oai_set)
        yield from self._iter_pages('ListRecords', RECORD_TAG, self._live_record, params)

    def iter_records(self, metadata_prefix='oai_dc', from_date=None, oai_set=None):
        for record_page in self.iter_record_pages(metadata_prefix, from_date=from_date, oai_set=oai_set):
            yield from record_page


def retrieve_identifiers(url, output_file, from_date=None, oai_set=None):
    client = OAIClient(url)
    with open(output_file, "w", encoding="utf-8") as file_handle:
        for identifier in client.iter_identifiers(from_date=from_date, oai_set=oai_set):
            file_handle.write(identifier + "\n")
            # maybe log something in a file or database record?
            #console.print(f"Retrieved identifier: {identifier}", markup=False)

# TODO: add retrieve records functionality, given the identifiers from a file
def retrieve_records(url, output_dir, metadata_prefix='oai_dc', from_date=None, oai_set=None):
    client = OAIClient(url)
    os.makedirs(output_dir, exist_ok=True)
    records = client.iter_records(metadata_prefix=metadata_prefix, from_date=from_date, oai_set=oai_set)
    for i, record in enumerate(records, start=1):
        # extract the identifier from the record if available
        identifier_element = record.find(f"{HEADER_TAG}/{IDENTIFIER_TAG}")
        identifier = identifier_element.text if identifier_element is not None else f"record_{i}"

        file_name = f"{get_save_dir_or_file_name(identifier)}_{metadata_prefix}.xml"
        output_file = os.path.join(output_dir, file_name)
        ET.indent(record, space="  ")
        with open(output_file, "w", encoding="utf-8") as file_handle:
            file_handle.write(ET.tostring(record, encoding="unicode"))
            file_handle.write("\n")
            # maybe log something in a file or database record?
            #console.print(f"Retrieved record: {record}", markup=False)

def get_save_dir_or_file_name(name):
    # Replace path separators and characters that are invalid in Windows file names.
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
