# Remember to stop the bot before running this
import json
from elasticsearch import Elasticsearch

INDEX_NAME = 'tagbot'
TMP_INDEX = f'{INDEX_NAME}_tmp'

with open('settings.json') as f:
  settings = json.load(f)

es = Elasticsearch()

if not es.indices.exists(index=TMP_INDEX):
  raise RuntimeError('Backup index not found, run backup.py first')

# delete old
es.indices.delete(index=INDEX_NAME)

# create with new settings
es.indices.create(
  index=INDEX_NAME,
  settings=settings['settings'],
  mappings=settings['mappings']
)

# copy data from tmp to new
es.reindex(body={
  "source": {"index": TMP_INDEX},
  "dest": {"index": INDEX_NAME}
})

input("Data copied! Press Enter to delete the temp index...")

# delete temp
es.indices.delete(index=TMP_INDEX)