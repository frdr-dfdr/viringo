"""Handles interactions to the DataCite REST Service for retrieving metadata"""

import base64
import logging
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from operator import itemgetter
import dateutil.parser
import dateutil.tz
import requests
from viringo import config

class Metadata:
    """Represents a DataCite metadata resultset"""
    def __init__(
            self,
            identifier=None,
            created_datetime=None,
            updated_datetime=None,
            xml=None,
            titles=None,
            creators=None,
            subjects=None,
            descriptions=None,
            publisher=None,
            publication_year=None,
            dates=None,
            contributors=None,
            resource_types=None,
            funding_references=None,
            geo_locations=None,
            formats=None,
            identifiers=None,
            language=None,
            relations=None,
            rights=None,
            sizes=None,
            client=None,
            active=True
        ):

        self.identifier = identifier
        self.created_datetime = created_datetime or datetime.min
        self.updated_datetime = updated_datetime or datetime.min
        self.xml = xml
        self.titles = titles or []
        self.creators = creators or []
        self.subjects = subjects or []
        self.descriptions = descriptions or []
        self.publisher = publisher
        self.publication_year = publication_year
        self.dates = dates or []
        self.contributors = contributors or []
        self.resource_types = resource_types or []
        self.funding_references = funding_references or []
        self.geo_locations = geo_locations or []
        self.formats = formats or []
        self.identifiers = identifiers or []
        self.language = language
        self.relations = relations or []
        self.rights = rights or []
        self.sizes = sizes or []
        self.client = client
        self.active = active

def build_metadata(data):
    """Parse single json-api data dict into metadata object"""
    result = Metadata()

    result.identifier = data.get('id')

    # Here we want to parse a ISO date but convert to UTC and then remove the TZinfo entirely
    # This is because OAI always works in UTC.
    created = dateutil.parser.parse(data['attributes']['created'])
    result.created_datetime = created.astimezone(dateutil.tz.UTC).replace(tzinfo=None)
    updated = dateutil.parser.parse(data['attributes']['updated'])
    result.updated_datetime = updated.astimezone(dateutil.tz.UTC).replace(tzinfo=None)

    result.xml = base64.b64decode(data['attributes']['xml']) \
        if data['attributes']['xml'] is not None else None

    result.titles = [
        title.get('title', '') for title in data['attributes']['titles']
    ] if data['attributes']['titles'] is not None else []

    result.creators = [
        creator.get('name', '') for creator in data['attributes']['creators']
    ]  if data['attributes']['creators'] is not None else []

    result.subjects = [
        subject.get('subject', '') for subject in data['attributes']['subjects']
    ] if data['attributes']['subjects'] is not None else []

    result.descriptions = [
        description.get('description', '') for description in data['attributes']['descriptions']
    ]  if data['attributes']['descriptions'] is not None else []

    result.publisher = data['attributes'].get('publisher') or ''
    result.publication_year = data['attributes'].get('publicationYear') or ''

    result.dates = [
        {'type': date['dateType'], 'date': date['date']} for date in data['attributes']['dates']
    ] if data['attributes']['dates'] is not None else []

    result.contributors = data['attributes'].get('contributors') or []
    result.funding_references = data['attributes'].get('fundingReferences') or []
    result.sizes = data['attributes'].get('sizes') or []
    result.geo_locations = data['attributes'].get('geoLocations') or []

    result.resource_types = []
    result.resource_types += [data['attributes']['types'].get('resourceTypeGeneral')] \
        if data['attributes']['types'].get('resourceTypeGeneral') is not None else []
    result.resource_types += [data['attributes']['types'].get('resourceType')] \
        if data['attributes']['types'].get('resourceType') is not None else []

    result.formats = data['attributes'].get('formats') or []

    result.identifiers = []

    for identifier in data['attributes']['identifiers']:
        if identifier['identifier']:
            result.identifiers.append({
                'type': identifier['identifierType'],
                'identifier': strip_uri_prefix(identifier['identifier'])
            })

    result.language = data['attributes'].get('language') or ''

    result.relations = [
        {'type': related['relatedIdentifierType'], 'identifier': related['relatedIdentifier']}
        for related in data['attributes']['relatedIdentifiers']
    ] if data['attributes']['relatedIdentifiers'] is not None else []

    result.rights = [
        {'statement': right.get('rights', None), 'uri': right.get('rightsUri', None)}
        for right in data['attributes']['rightsList']
    ] if data['attributes']['rightsList'] is not None else []

    result.client = data['relationships']['client']['data'].get('id').upper() or ''

    # We make the active decision based upon if there is metadata and the isActive flag
    # This is the same as previous oai-pmh datacite implementation.
    result.active = True if result.xml and data.get('isActive', True) else False

    return result

def strip_uri_prefix(identifier):
    """Strip common prefixes because OAI doesn't work with those kind of ID's"""
    if identifier:
        if identifier.startswith("https://doi.org/"):
            _, identifier = identifier.split("https://doi.org/")
    else:
        identifier = ''
    return identifier

def get_metadata(doi):
    """Return a parsed metadata result from the DataCite API

    Aside from the raw xml, the attributes parsed are best guesses for returning filled data.
    """

    response = requests.get(config.DATACITE_API_URL + '/dois/' + doi)
    if response.status_code == 200:
        data = response.json()['data']
        return build_metadata(data)
    else:
        logging.error("Error receiving data from datacite REST API")

    return None

def get_metadata_list(
        query=None,
        provider_id=None,
        client_id=None,
        from_datetime=None,
        until_datetime=None,
        cursor=None
    ):
    """Returns metadata in parsed metadata result from the DataCite API"""

    # Trigger cursor navigation with a starting value
    if not cursor:
        cursor = 1

    # Whenever just a from is specified always set the until to latest timestamp.
    if from_datetime and not until_datetime:
        until_datetime = datetime.now()

    # Construct a custom query for datetime filtering.
    # We use the updated date not the created date because users tend to prefer
    # seeing latest changes.
    datetime_query = ''
    if from_datetime and until_datetime:
        datetime_query = "updated:[{0}+TO+{1}]".format(
            from_datetime.isoformat(), until_datetime.isoformat()
        )

    params = {
        'detail': True,
        'provider_id': provider_id,
        'client_id': client_id,
        'page[size]': config.RESULT_SET_SIZE,
        'page[cursor]': cursor
    }

    if datetime_query:
        if query:
            query = query + " AND " + datetime_query
        else:
            query = datetime_query

    if query:
        params['query'] = query

    # Construct the payload as a string
    # to avoid direct urlencoding by requests library which messes up some of the params
    payload_str = "&".join("%s=%s" % (k, v) for k, v in params.items() if v is not None)

    response = requests.get(config.DATACITE_API_URL + '/dois', params=payload_str)

    if response.status_code == 200:
        json = response.json()

        if json['meta']['total'] == 0:
            return None, None

        # Grab out the cursor bit from the full next link
        next_link = json['links'].get('next')
        if next_link:
            query = parse_qs(urlparse(json['links']['next']).query)
            cursor = query['page[cursor]'][0] # It comes back as a list but only ever one value
        else:
            cursor = 0

        data = json['data']
        results = []
        for doi_entry in data:
            result = build_metadata(doi_entry)
            results.append(result)

        return results, cursor
    else:
        response.raise_for_status()

    return None

def get_sets():
    """Returns sets that can be used for further sub dividing results"""

    params = {
        'page[size]': 1000,
    }

    response = requests.get(config.DATACITE_API_URL + '/clients', params)

    if response.status_code == 200:
        json = response.json()

        if json['meta']['total'] == 0:
            return None

        data = json['data'] # clients
        included = json['included'] # providers

        results = []
        for entry in data:
            if entry['id'] not in results:
                results.append((entry['id'], entry['attributes']['name']))

        for entry in included:
            if entry['id'] not in results:
                results.append((entry['id'], entry['attributes']['name']))

        # Sort the results, this should be relativly fast given sets tend to be a small subset.
        results.sort(key=itemgetter(0))

        return results
    else:
        response.raise_for_status()
