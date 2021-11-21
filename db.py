import base64
import json
import functools
import struct
import time
from dataclasses import dataclass
from typing import Callable
from cachetools import TTLCache

from elasticsearch import NotFoundError
from elasticsearch_dsl import Search

import db_init
from gen_search_query import gen_search_query
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
  q = gen_search_query(
    owner, query, includes=['id', 'access_hash', 'type', 'tags', 'emoji', 'filename', 'title']
  )

  r = await es.search(
    index=index,
    size=MAX_RESULTS_PER_PAGE,
    from_=page * MAX_RESULTS_PER_PAGE,
    **q.to_dict()
  )
  return (
    r['hits']['total']['value'],
    [TaggedDocument(**o['_source']) for o in r['hits']['hits']]
  )


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
  doc: TaggedDocument, index: str
):
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


@resolve_index
async def mark_user_media(owner: int, id: int, marked=True, index: str = None):
  try:
    return await es.update(
      index=index,
      id=pack_doc_id(owner, id),
      doc={
        'marked': marked,
        'last_used': round(time.time())
      },
      refresh=True
    )
  except NotFoundError:
    raise ValueError('You have not saved this media')


@resolve_index
async def mark_all_user_media(
  owner: int,
  marked: bool,
  refresh: bool = False,
  query_gen: Callable = None,
  index: str = None
):
  q = Search().filter('term', owner=owner)
  if marked:
    q = q.exclude('term', marked=True)
  else:
    q = q.filter('term', marked=True)

  if query_gen:
    q = query_gen(q)

  return await es.update_by_query(
    index=index,
    body=q.to_dict() | {
      'script': {
        'source': 'ctx._source.marked = params.marked',
        'params': { 'marked': marked }
      }
    },
    refresh=refresh
  )


@resolve_index
async def mark_all_user_media_from_query(
  owner: int,
  query: ParsedQuery,
  marked: bool,
  index: str = None
):
  return await mark_all_user_media(
    owner=owner,
    marked=marked,
    refresh=True,
    query_gen=lambda q: gen_search_query(
      owner, query, initial_q=q
    ),
    index=index
  )


@resolve_index
async def get_marked_user_media(
  owner: int,
  excludes=['owner', 'last_used', 'created', 'marked'],
  index: str = None
):
  q = Search().filter('term', owner=owner).filter('term', marked=True)
  if excludes:
    q = q.source(excludes=excludes)
  r = await es.search(index=index, **q.to_dict(), size=10000)
  return [o['_source'] for o in r['hits']['hits']]
