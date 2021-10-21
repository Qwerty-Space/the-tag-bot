import logging
from dataclasses import dataclass
from collections import OrderedDict

from buildpg import asyncpg, V, Func, RawDangerous
from cachetools import LRUCache

from utils import ParsedTags, MediaTypes, acached

pool: asyncpg.BuildPgPool
logger = logging.getLogger('db')
TAG_DIFF_MAX = 0.7

corrected_tag_cache = LRUCache(4096)
@dataclass
class SearchTag:
  in_name: str
  is_pos: bool
  out_name: str = None


async def set_media_tags(
  id: int, owner: int, access_hash: int,
  m_type: MediaTypes, title: str, metatags: str, tags: str
):
  r = await pool.fetchrow_b(
    '''
    INSERT INTO media
    (id, owner, access_hash, type, title, metatags, tags) VALUES
      (:id, :owner, :access_hash, :type, :title, :metatags, :tags)
    ON CONFLICT (id, owner) DO UPDATE
    SET access_hash = :access_hash, type = :type, title = :title,
      metatags = :metatags, tags = :tags
    RETURNING all_tags as new, (
      SELECT all_tags FROM media t WHERE id = media.id AND owner = media.owner
    ) as old;
    ''',
    id=id, owner=owner, access_hash=access_hash,
    type=m_type.value, title=title, metatags=metatags, tags=tags
  )
  # prevent any tags that have just been created from being corrected to
  # old (previously correct) values
  for tag in tags.split(' '):
    key = (owner, m_type, tag)
    out_tag = corrected_tag_cache.get(key)
    if out_tag and tag != out_tag:
      del corrected_tag_cache[key]
  # drop all deleted tags
  all_old_tags = set((r.get('old') or '').split(' '))
  all_new_tags = set((r.get('new') or '').split(' '))
  for tag in (all_old_tags - all_new_tags):
    key = (owner, m_type, tag)
    corrected_tag_cache.pop(key, None)


async def delete_media(id: int, owner: int):
  return await pool.fetchval_b(
    'DELETE FROM media WHERE id = :id AND owner = :owner RETURNING *',
    id=id, owner=owner
  )

async def get_media_tags(id: int, owner: int):
  return await pool.fetchrow_b(
    'SELECT metatags, tags FROM media WHERE id = :id AND owner = :owner',
    id=id, owner=owner
  )


async def get_media_user_tags(id: int, owner: int):
  return await pool.fetchval_b(
    'SELECT tags FROM media WHERE id = :id AND owner = :owner',
    id=id, owner=owner
  )


async def get_user_tags_for_type(owner: int, m_type: MediaTypes):
  return await pool.fetch_b(
    '''SELECT name, count FROM tags WHERE
    owner = :owner AND type = :type ORDER BY count DESC''',
    owner=owner, type=m_type.value
  )


async def update_last_used(owner: int, id: int):
  return await pool.execute_b(
    '''UPDATE media SET last_used_at = CURRENT_TIMESTAMP WHERE
    owner = :owner AND id = :id''',
    owner=owner, id=id
  )

async def search_user_media(
  owner: int, m_type: MediaTypes, tags: ParsedTags, offset=0
):
  space_split = lambda s1: Func('string_to_array', s1, RawDangerous("' '"))
  all_tags_split = lambda: space_split(V('all_tags'))

  where_logic = (V('owner') == owner) & (V('type') == m_type.value)
  if tags.pos:
    where_logic &= all_tags_split().contains(space_split(' '.join(tags.pos)))
  if tags.neg:
    where_logic &= ~all_tags_split().overlap(space_split(' '.join(tags.neg)))

  return await pool.fetch_b(
    '''
    SELECT id, access_hash, title, all_tags FROM media
    WHERE :where ORDER BY last_used_at DESC LIMIT 50 OFFSET :offset
    ''',
    where=where_logic,
    offset=offset * 50
  )


@acached(LRUCache(1024))
async def get_corrected_media_type(search_val: str):
  try:
    return MediaTypes(search_val)
  except ValueError:
    pass

  row = await pool.fetchrow_b(
    '''
    SELECT name AS match, name::text <-> :search_val::text AS dist
    FROM UNNEST(enum_range(NULL::media_type)) name ORDER BY dist LIMIT 1
    ''',
    search_val=search_val
  )
  if row['dist'] <= TAG_DIFF_MAX:
    return MediaTypes(row['match'])
  return None


async def get_corrected_user_tags(owner: int, tags: ParsedTags):
  m_type = await get_corrected_media_type(tags.type)
  if not m_type:
    # No point correcting tags if we don't know what type to look for
    return m_type, None, []

  get_cache_key = lambda name: (owner, m_type, name)
  iter_resolved = lambda: (t for t in resolved_tags.values() if t.out_name)
  tag_matches = (
    lambda r:
    r['dist'] <= TAG_DIFF_MAX
    or (len(r['search_tag']) >= 4 and r['search_tag'] in r['match'])
  )

  # Pull tags from cache
  resolved_tags = OrderedDict(((v, SearchTag(v, True)) for v in tags.pos))
  resolved_tags.update(((v, SearchTag(v, False)) for v in tags.neg))
  for tag in resolved_tags.values():
    tag.out_name = corrected_tag_cache.get(get_cache_key(tag.in_name), None)

  # Query unresolved tags
  fetch_tags = [name for name, tag in resolved_tags.items() if not tag.out_name]
  dropped = []
  if fetch_tags:
    res = await pool.fetch_b(
      '''
      SELECT * FROM UNNEST(string_to_array(:tag_str, ' ')) search_tag,
      LATERAL (
        SELECT name AS match, name <-> search_tag AS dist
        FROM tags WHERE owner = :owner AND type = :m_type ORDER BY dist LIMIT 1
      ) AS s;
      ''',
      owner=owner, m_type=m_type, tag_str=' '.join(fetch_tags)
    )

    assert len(res) == len(fetch_tags)

    for in_name, row in zip(fetch_tags, res):
      if tag_matches(row):
        resolved_tags[in_name].out_name = row['match']
      else:
        dropped.append(row)

  # Cache results
  for tag in iter_resolved():
    corrected_tag_cache[get_cache_key(tag.in_name)] = tag.out_name

  ret_tags = ParsedTags(
    m_type.value,
    set(t.out_name for t in iter_resolved() if t.is_pos),
    set(t.out_name for t in iter_resolved() if not t.is_pos)
  )

  return m_type, ret_tags, dropped


async def init():
  global pool
  logger.info('Creating connection pool...')
  pool = await asyncpg.create_pool_b(
    database='tagbot',
    user='tagbot',
    host='localhost'
  )

  rows = await pool.fetch_b('SELECT unnest(enum_range(NULL::media_type)) as v')
  assert set(r['v'] for r in rows) == set(e.value for e in MediaTypes)

  logger.info('Initialized')
