import asyncio
import logging
import itertools

from buildpg import asyncpg, V, funcs, Func, RawDangerous

from utils import ParsedTags

pool: asyncpg.BuildPgPool
logger = logging.getLogger('db')
# TODO: put this somewhere else
TAG_DIFF_MAX = 0.7


async def set_media_tags(
  id: int, owner: int, access_hash: int, metatags: str, tags: str
):
  await pool.execute(
    '''
    INSERT INTO media
    (id, owner, access_hash, metatags, tags) VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (id, owner) DO UPDATE
    SET metatags = $4, tags = $5;
    ''',
    id, owner, access_hash, metatags, tags
  )


async def get_media_tags(id: int, owner: int):
  return await pool.fetchval(
    'SELECT tags FROM media WHERE id = $1 AND owner = $2',
    id, owner
  )


async def get_user_tags(owner: int):
  return await pool.fetch(
    'SELECT name, count FROM tags WHERE owner = $1 ORDER BY count DESC',
    owner
  )


async def search_user_media(owner: int, tags: ParsedTags):
  space_split = lambda s1: Func('string_to_array', s1, RawDangerous("' '"))
  all_tags_split = lambda: space_split(V('all_tags'))

  where_logic = V('owner') == owner
  if tags.pos:
    where_logic &= all_tags_split().contains(space_split(' '.join(tags.pos)))
  if tags.neg:
    where_logic &= ~all_tags_split().overlap(space_split(' '.join(tags.neg)))

  return await pool.fetch_b(
    'SELECT id, access_hash, metatags FROM media WHERE :where ORDER BY last_used_at DESC',
    where=where_logic
  )


# TODO: cache each corrected tag (per user)
async def get_corrected_user_tags(owner: int, tags: ParsedTags):
  num_positive = len(tags.pos)
  tag_str = ' '.join(itertools.chain(tags.pos, tags.neg))
  res = await pool.fetch(
    '''
    SELECT * FROM UNNEST(string_to_array($2, ' ')) search_tag,
    LATERAL (
      SELECT name AS match, name <-> search_tag AS dist
      FROM tags WHERE owner = $1 ORDER BY dist LIMIT 1
    ) AS s;
    ''',
    owner, tag_str
  )
  pos = res[:num_positive]
  neg = res[num_positive:]

  tag_matches = (
    lambda r:
    r['dist'] <= TAG_DIFF_MAX
    or (len(r['search_tag']) >= 4 and r['search_tag'] in r['match'])
  )
  good = ParsedTags(
    set(r['match'] for r in pos if tag_matches(r)),
    set(r['match'] for r in neg if tag_matches(r))
  )
  bad = [r for r in itertools.chain(pos, neg) if not tag_matches(r)]

  return good, bad


async def init():
  global pool
  logger.info('Creating connection pool...')
  pool = await asyncpg.create_pool_b(
    database='tagbot',
    user='tagbot',
    host='localhost'
  )

  logger.info('Creating tables...')

  # TODO: put this behind a --init flag
  with open('db.sql') as f:
    sql = f.read()

  await pool.execute(sql)

  async with pool.acquire() as con:
    await con.execute(sql)

  logger.info('Initialized')
