# Remember to stop the bot before running this
from elasticsearch import Elasticsearch

INDEX_NAME = 'tagbot'
TMP_INDEX = f'{INDEX_NAME}_tmp'

es = Elasticsearch()

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
