import base64
import struct
import time

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import MultiMatch, Terms, Bool, Term

from query_parser import ParsedQuery
from data_model import TaggedDocument


es = AsyncElasticsearch()
INDEX_NAME = 'tagbot'


def pack_doc_id(owner: int, id: int):
  return base64.urlsafe_b64encode(struct.pack('!QQ', owner, id))


async def search_user_media(
  owner: int, query: ParsedQuery
):
  fuzzy_match = lambda fields, values: MultiMatch(
    query=' '.join(values),
    type='most_fields',
    fields=fields,
    operator='and',
    fuzziness='AUTO:4,6',  # disable fuzzy for trigrams
    prefix_length=1
  )
  fuzzy_ngram = lambda fields, values: fuzzy_match(
    [
      f for field in fields for f in
      [f'{field}', f'{field}.prefix_ngram^2', f'{field}.trigram']
    ],
    values
  )
  field_queries = {
    'tags': lambda f, v: fuzzy_ngram([f, 'title'], v),
    'filename': lambda f, v: fuzzy_ngram([f, 'title'], v),
    'pack_name': lambda f, v: fuzzy_ngram([f], v),
    'ext': lambda f, v: fuzzy_match([f], v),
    'is_animated': lambda f, v: Bool(filter=[Term(is_animated=v[0] == 'yes')]),
    'emoji': lambda f, v: Terms(emoji=v)
  }

  q = (
    Search()
    .filter('term', owner=owner)
    .filter('term', type=query.get_first('type'))
    .sort('_score', '-last_used')
    .source(includes=['id', 'access_hash', 'tags', 'filename', 'title'])
  )

  for (field, is_neg), values in query.fields.items():
    func = field_queries.get(field)
    if not func:
      continue
    sub_q = func(field, values)
    if is_neg:
      sub_q = ~sub_q
    q = q.query(sub_q)

  r = await es.search(
    index=INDEX_NAME,
    size=50,
    **q.to_dict()
  )
  return [TaggedDocument(**o['_source']) for o in r['hits']['hits']]


async def get_user_media(owner: int, id: int):
  try:
    r = await es.get(index=INDEX_NAME, id=pack_doc_id(owner, id))
    return TaggedDocument(**r['_source'])
  except NotFoundError:
    return None


async def update_user_media(owner: int, id: int, doc: dict):
  r = await es.update(
    index=INDEX_NAME,
    id=pack_doc_id(owner, id),
    doc=doc,
    doc_as_upsert=True
  )
  # if r['result'] == 'created' ...
  return r


async def update_last_used(owner: int, id: int):
  return await es.update(
    index=INDEX_NAME,
    id=pack_doc_id(owner, id),
    doc={'last_used': round(time.time())}
  )


async def delete_user_media(owner: int, id: int):
  try:
    return await es.delete(
      index=INDEX_NAME,
      id=pack_doc_id(owner, id)
    )
  except NotFoundError:
    return None