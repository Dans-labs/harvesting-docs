# Harvesting client code for OAI-PMH (Open Archives Initiative Protocol for Metadata Harvesting) 

import requests
import xml.etree.ElementTree as ET
import os

OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NAMESPACE = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("oai", OAI_NAMESPACE)
ET.register_namespace("oai_dc", OAI_DC_NAMESPACE)
ET.register_namespace("dc", DC_NAMESPACE)
ET.register_namespace("xsi", XSI_NAMESPACE)

class OAIClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def request(self, params):
        response = requests.get(self.base_url, params=params)
        response.raise_for_status()
        return ET.fromstring(response.content)
    
    def identify(self):
        return self.request({'verb': 'Identify'})
    
    def list_metadata_formats(self):
        return self.request({'verb': 'ListMetadataFormats'})

    def list_sets(self):
        return self.request({'verb': 'ListSets'})
    
    def list_records(self, metadata_prefix='oai_dc', oai_set=None, **kwargs):
        params = {'verb': 'ListRecords', 'metadataPrefix': metadata_prefix}
        if oai_set:
            params['set'] = oai_set
        params.update(kwargs)
        return self.request(params)

    def get_record(self, identifier, metadata_prefix='oai_dc'):
        return self.request({'verb': 'GetRecord', 'identifier': identifier, 'metadataPrefix': metadata_prefix})

    def list_identifiers(self, metadata_prefix='oai_dc', oai_set=None, **kwargs):
        params = {'verb': 'ListIdentifiers', 'metadataPrefix': metadata_prefix}
        if oai_set:
            params['set'] = oai_set
        params.update(kwargs)
        return self.request(params)

    def iter_identifier_pages(self, metadata_prefix='oai_dc', from_date=None, oai_set=None, **kwargs):
        """Yield one list of identifiers for each server-defined OAI-PMH page."""
        params = {'metadataPrefix': metadata_prefix, **kwargs}
        if from_date:
            params['from'] = from_date
        if oai_set:
            params['set'] = oai_set

        while True:
            response = requests.get(self.base_url, params={'verb': 'ListIdentifiers', **params}, stream=True)
            response.raise_for_status()
            response.raw.decode_content = True
            identifiers = []
            token = None

            try:
                for _, element in ET.iterparse(response.raw, events=('end',)):
                    if element.tag == '{http://www.openarchives.org/OAI/2.0/}header':
                        # skip if it has status="deleted"
                        # maybe we want to store that also somewhere, so we can get rid of these records at some point
                        if element.attrib.get('status') == 'deleted':
                            element.clear()
                            continue
                        identifier = element.find('{http://www.openarchives.org/OAI/2.0/}identifier')
                        if identifier is not None and identifier.text:
                            identifiers.append(identifier.text)
                        element.clear()
                    elif element.tag == '{http://www.openarchives.org/OAI/2.0/}resumptionToken':
                        token = element.text
                        element.clear()
                if identifiers:
                    yield identifiers
            finally:
                response.close()

            if not token:
                break
            params = {'resumptionToken': token}

    # An iterator to get all identifiers using the resumption token.
    # Example usage:
    # client = OAIClient("https://example.org/oai")
    # for identifier in client.iter_identifiers():
    #     print(identifier)
    def iter_identifiers(self, metadata_prefix='oai_dc', from_date=None, oai_set=None, **kwargs):
        for identifiers in self.iter_identifier_pages(metadata_prefix, from_date=from_date, oai_set=oai_set, **kwargs):
            yield from identifiers

    def iter_record_pages(self, metadata_prefix='oai_dc', from_date=None, oai_set=None, **kwargs):
        params = {'metadataPrefix': metadata_prefix}
        if from_date:
            params['from'] = from_date
        if oai_set:
            params['set'] = oai_set
        params.update(kwargs)

        while True:
            response = requests.get(self.base_url, params={'verb': 'ListRecords', **params}, stream=True)
            response.raise_for_status()
            response.raw.decode_content = True
            records = []
            token = None

            try:
                for _, element in ET.iterparse(response.raw, events=('end',)):
                    if element.tag == '{http://www.openarchives.org/OAI/2.0/}record':
                        records.append(element)
                    elif element.tag == '{http://www.openarchives.org/OAI/2.0/}resumptionToken':
                        token = element.text
                        element.clear()
                if records:
                    yield records
            finally:
                response.close()

            if not token:
                break
            params = {'resumptionToken': token}

    def iter_records(self, metadata_prefix='oai_dc', from_date=None, oai_set=None, **kwargs):
        for record_page in self.iter_record_pages(metadata_prefix, from_date=from_date, oai_set=oai_set, **kwargs):
            yield from record_page 


def retrieve_identifiers(url, output_file):
    client = OAIClient(url)
    with open(output_file, "w", encoding="utf-8") as file_handle:
        for identifier in client.iter_identifiers():
            file_handle.write(identifier + "\n")
            # maybe log something in a file or database record?
            #console.print(f"Retrieved identifier: {identifier}", markup=False)

# TODO: add retrieve records functionality, given the identifiers from a file
def retrieve_records(url, output_dir, metadata_prefix='oai_dc', from_date=None):
    client = OAIClient(url)
    os.makedirs(output_dir, exist_ok=True)
    for i, record in enumerate(client.iter_records(metadata_prefix=metadata_prefix, from_date=from_date), start=1):
        # extract the identifier from the record if available
        identifier_element = record.find('{http://www.openarchives.org/OAI/2.0/}header/{http://www.openarchives.org/OAI/2.0/}identifier')
        identifier = identifier_element.text if identifier_element is not None else f"record_{i}"

        file_name = f"{get_save_dir_or_file_name(identifier)}_{metadata_prefix}.xml"
        output_file = f"{output_dir}/{file_name}"
        ET.indent(record, space="  ")
        ET.indent(record, space="  ")
        with open(output_file, "w", encoding="utf-8") as file_handle:
            file_handle.write(ET.tostring(record, encoding="unicode"))
            file_handle.write("\n")
            # maybe log something in a file or database record?
            #console.print(f"Retrieved record: {record}", markup=False)

def get_save_dir_or_file_name(name):
    return name.replace(':', '_').replace('/', '_')
