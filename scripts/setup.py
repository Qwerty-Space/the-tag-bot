# Uses the admin password to create the tagbot role and user, and create the index
import json
from elasticsearch import Elasticsearch

import sys
sys.path.insert(0,'..')
from secrets import HTTP_PASS, ADMIN_HTTP_PASS
from constants import INDEX_NAME


with open('settings.json') as f:
  settings = json.load(f)

es = Elasticsearch(http_auth=('elastic', ADMIN_HTTP_PASS))

es.security.put_role(
  name='tagbot',
  body={
    'cluster': [ 'monitor' ],
    'indices': [
      {
        'names': ['tagbot'],
        'privileges': ['all']
      }
    ]
  }
)

es.security.put_user(
  username='tagbot',
  body={
    "password" : HTTP_PASS,
    "roles" : ["tagbot"],
    "full_name" : "Tag Bot",
  }
)

es.indices.create(
index=INDEX_NAME,
  settings=settings['settings'],
  mappings=settings['mappings']
)
