import logging
import itertools

from buildpg import asyncpg, V, Func, RawDangerous
from cachetools import LRUCache

from utils import ParsedTags, MediaTypes, acached

pool: asyncpg.BuildPgPool
logger = logging.getLogger('db')
TAG_DIFF_MAX = 0.7


async def set_media_tags(
  id: int, owner: int, access_hash: int,
  m_type: MediaTypes, metatags: str, tags: str
):
  await pool.execute_b(
    '''
    INSERT INTO media
    (id, owner, access_hash, type, metatags, tags) VALUES
      (:id, :owner, :access_hash, :type, :metatags, :tags)
    ON CONFLICT (id, owner) DO UPDATE
    SET access_hash = :access_hash, type = :type, metatags = :metatags, tags = :tags;
    ''',
    id=id, owner=owner, access_hash=access_hash,
    type=m_type.value, metatags=metatags, tags=tags
  )


async def get_media_tags(id: int, owner: int):
  return await pool.fetchval_b(
    'SELECT tags FROM media WHERE id = :id AND owner = :owner',
    id=id, owner=owner
  )


async def get_user_tags_for_type(owner: int, m_type: MediaTypes):
  return await pool.fetch_b(
    '''SELECT name, count FROM tags WHERE
    owner = :owner and type = :type ORDER BY count DESC''',
    owner=owner, type=m_type.value
  )


async def search_user_media(owner: int, m_type: MediaTypes, tags: ParsedTags):
  space_split = lambda s1: Func('string_to_array', s1, RawDangerous("' '"))
  all_tags_split = lambda: space_split(V('all_tags'))

  where_logic = (V('owner') == owner) & (V('type') == m_type.value)
  if tags.pos:
    where_logic &= all_tags_split().contains(space_split(' '.join(tags.pos)))
  if tags.neg:
    where_logic &= ~all_tags_split().overlap(space_split(' '.join(tags.neg)))

  return await pool.fetch_b(
    'SELECT id, access_hash, metatags FROM media WHERE :where ORDER BY last_used_at DESC',
    where=where_logic
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


# TODO: cache each corrected tag (per user and type)
async def get_corrected_user_tags(owner: int, tags: ParsedTags):
  m_type = await get_corrected_media_type(tags.type)
  if not m_type:
    # No point correcting tags if we don't know what type to look for
    return m_type, None

  num_positive = len(tags.pos)
  tag_str = ' '.join(itertools.chain(tags.pos, tags.neg))
  res = await pool.fetch_b(
    '''
    SELECT * FROM UNNEST(string_to_array(:tag_str, ' ')) search_tag,
    LATERAL (
      SELECT name AS match, name <-> search_tag AS dist
      FROM tags WHERE owner = :owner AND type = :m_type ORDER BY dist LIMIT 1
    ) AS s;
    ''',
    owner=owner, m_type=m_type, tag_str=tag_str
  )
  pos = res[:num_positive]
  neg = res[num_positive:]

  tag_matches = (
    lambda r:
    r['dist'] <= TAG_DIFF_MAX
    or (len(r['search_tag']) >= 4 and r['search_tag'] in r['match'])
  )
  good = ParsedTags(
    m_type.value,
    set(r['match'] for r in pos if tag_matches(r)),
    set(r['match'] for r in neg if tag_matches(r))
  )
  # TODO: return this in some kind of hint wrapper
  # bad = [r for r in itertools.chain(pos, neg) if not tag_matches(r)]

  return m_type, good


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
