import base64
import functools
import struct
import time
from dataclasses import dataclass
from cachetools import TTLCache

from elasticsearch import NotFoundError
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import MultiMatch, Terms, Bool, Term
from idna.core import valid_contextj

import db_init
from utils import acached
from query_parser import ParsedQuery
from data_model import TaggedDocument
from constants import (
  MAX_MEDIA_PER_USER, MAX_EMOJI_PER_FILE, MAX_TAGS_PER_FILE, MAX_TAG_LENGTH,
  MAX_RESULTS_PER_PAGE, INDEX
)


@dataclass
class CachedCounter:
  real: int
  offset: int = 0

  @property
  def count(self):
    return self.real + self.offset

  def set(self, value):
    self.offset = value - self.real

es = db_init.es_main
init = db_init.init


def pack_doc_id(owner: int, id: int):
  return base64.urlsafe_b64encode(struct.pack('!QQ', owner, id))


def get_index(is_transfer):
  return INDEX.transfer if is_transfer else INDEX.main


def resolve_index(func):
  @functools.wraps(func)
  def wrapper(*args, **kwargs):
    index = kwargs.get('index') or INDEX.main
    if kwargs.pop('is_transfer', None):
      index = INDEX.transfer
    kwargs['index'] = index
    return func(*args, **kwargs)
  return wrapper


@resolve_index
async def count_user_media_by_type(owner: int, only_marked=False, index: str = None):
  q = Search()
  aggs = q.aggs.bucket('user', 'filter', term={'owner': owner})
  if only_marked:
    aggs = aggs.bucket('marked', 'filter', term={'marked': True})
  aggs = aggs .bucket('types', 'terms', field='type')
  r = await es.search(index=index, size=0, **q.to_dict())
  return r['aggregations']['user']


@acached(TTLCache(1024, ttl=60 * 10))
@resolve_index
async def count_user_media(owner: int, index: str):
  q = Search().filter('term', owner=owner)
  r = await es.count(index=index, body=q.to_dict())
  return CachedCounter(r['count'])


@resolve_index
async def search_user_media(
  owner: int, query: ParsedQuery, index: str, page: int = 0
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
    .sort('_score', '-last_used')
    .source(includes=['id', 'access_hash', 'type', 'tags', 'emoji', 'filename', 'title'])
  )
  search_type = query.get_first('type')
  if search_type == 'document':
    q = q.exclude('term', type='photo')
  else:
    q = q.filter('term', type=search_type)

  for (field, is_neg), values in query.fields.items():
    func = field_queries.get(field)
    if not func:
      continue
    sub_q = func(field, values)
    if is_neg:
      sub_q = ~sub_q
    q = q.query(sub_q)

  r = await es.search(
    index=index,
    size=MAX_RESULTS_PER_PAGE,
    from_=page * MAX_RESULTS_PER_PAGE,
    **q.to_dict()
  )
  return [TaggedDocument(**o['_source']) for o in r['hits']['hits']]


@resolve_index
async def get_user_media(owner: int, id: int, index: str):
  try:
    r = await es.get(index=index, id=pack_doc_id(owner, id))
    r['_source']['last_used'] = round(time.time())
    return TaggedDocument(**r['_source'])
  except NotFoundError:
    return None


@resolve_index
async def update_user_media(
  doc: TaggedDocument, index: str, refresh=False, check_limits=True
):
  if check_limits:
    if any(len(tag) > MAX_TAG_LENGTH for tag in doc.tags):
      raise ValueError(f'Tags are limited to a length of {MAX_TAG_LENGTH}!')
    if len(doc.tags) > MAX_TAGS_PER_FILE:
      raise ValueError(f'Only {MAX_TAGS_PER_FILE} tags are allowed per file!')
    if len(doc.emoji) > MAX_EMOJI_PER_FILE:
      raise ValueError(f'Only {MAX_EMOJI_PER_FILE} emoji are allowed per file!')

  counter = await count_user_media(doc.owner, index=index)
  try:
    r = await es.update(
      index=index,
      id=pack_doc_id(doc.owner, doc.id),
      doc=doc.to_dict(),
      doc_as_upsert=(counter.count < MAX_MEDIA_PER_USER),
      refresh=refresh
    )
  except NotFoundError:
    raise ValueError(f'Only {MAX_MEDIA_PER_USER} media allowed per user')
  if r['result'] == 'created':
    counter.offset += 1

  return r


@resolve_index
async def update_last_used(owner: int, id: int, index: str):
  return await es.update(
    index=index,
    id=pack_doc_id(owner, id),
    doc={'last_used': round(time.time())}
  )


@resolve_index
async def delete_user_media(owner: int, id: int, index: str):
  try:
    count = await count_user_media(owner, index=index)
    r = await es.delete(
      index=index,
      id=pack_doc_id(owner, id)
    )
    count.offset -= 1
    return r
  except NotFoundError:
    return None


async def copy_to_transfer_index(owner: int, id: int):
  doc = await get_user_media(owner, id)
  if not doc:
    raise ValueError('You have not saved this media')
  await update_user_media(doc, is_transfer=True, refresh=True, check_limits=False)


async def clear_transfer_index(owner: int, pop=False):
  q = Search().filter('term', owner=owner)
  docs = []
  if pop:
    r = await es.search(
      index=INDEX.transfer,
      **q.source(excludes=['owner', 'last_used', 'created']).to_dict()
    )
    docs = [o['_source'] for o in r['hits']['hits']]
  r = await es.delete_by_query(
    index=INDEX.transfer,
    body=q.to_dict()
  )
  (await count_user_media(owner, is_transfer=True)).set(0)
  return docs or r['deleted']