# Remember to stop the bot before running this
# Clones the index to {index}_tmp so you can safely use recreate.py without
# losing data
from elasticsearch import Elasticsearch

import sys
sys.path.insert(0,'..')
from secrets import ADMIN_HTTP_PASS
from constants import INDEX_NAME


TMP_INDEX = f'{INDEX_NAME}_tmp'

es = Elasticsearch(http_auth=('elastic', ADMIN_HTTP_PASS))

# make index read only
es.indices.put_settings(
  index=INDEX_NAME,
  body={
    "settings": {
      "index.blocks.write": True
    }
  }
)
# copy to temp
es.indices.clone(index=INDEX_NAME, target=TMP_INDEX)

# wait for clone to finish
es.cluster.health(index=TMP_INDEX, wait_for_status='yellow', timeout='30s')
