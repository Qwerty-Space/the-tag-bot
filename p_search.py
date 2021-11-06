from collections import defaultdict
from itertools import chain
from cachetools import LRUCache

from telethon import events

from data_model import MediaTypes
from proxy_globals import client
import db, utils, query_parser
from telethon.tl.types import InputDocument, InputPhoto, UpdateBotInlineSend


last_query_cache = LRUCache(128)


@client.on(events.Raw(UpdateBotInlineSend))
async def on_inline_selected(event):
  await db.update_last_used(event.user_id, int(event.id))


@client.on(events.InlineQuery())
@utils.whitelist
async def on_inline(event: events.InlineQuery.Event):
  # TODO: highlight matches
  # https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html#matched-fields
  def truncate_tags(tags):
    return ' '.join(tags)[:128].rsplit(' ', 1)[0] + '…'
  user_id = event.query.user_id
  last_query_cache[user_id] = event.text
  q, warnings = query_parser.parse_query(event.text)
  # TODO: fix
  # offset = int(event.offset or 0)
  docs = await db.search_user_media(user_id, q)

  res_type = q.get_first('type')
  # 'audio' only works for audio/mpeg, thanks durov
  if res_type == MediaTypes.audio.value:
    res_type = MediaTypes.file.value

  builder = event.builder
  if res_type == MediaTypes.photo.value:
    get_result = lambda d: builder.photo(
      id=str(d.id),
      file=InputPhoto(d.id, d.access_hash, b'')
    )
  else:
    get_result = (
      lambda d: builder.document(
        id=str(d.id),
        file=InputDocument(d.id, d.access_hash, b''),
        type=res_type,
        title=d.title or truncate_tags(d.tags) or f'[{res_type}]'
      )
    )
  await event.answer(
    [get_result(d) for d in docs],
    cache_time=0 if warnings else 5,
    private=True,
    # next_offset=f'{offset + 1}' if len(rows) >= 50 else None,
    switch_pm=f'{len(warnings)} warnings' if warnings else None,
    switch_pm_param='parse'
  )


@client.on(events.NewMessage(pattern=r'/parse (.+)'))
@utils.whitelist
async def parse(event: events.NewMessage.Event, query=None):
  query = query or event.pattern_match.group(1)

  out_text = ''
  q, warnings = query_parser.parse_query(query)
  if warnings:
    out_text += 'Errors:\n' + '\n'.join(warnings) + '\n'

  out_text += '\nParsed fields:'

  parsed = defaultdict(list)
  for (field, is_neg), values in q.fields.items():
    f_vals = [('!' if is_neg else '') + value for value in values]
    parsed[field].extend(f_vals)

  for field, values in parsed.items():
    out_text += f'\n{field}: {" ".join(values)}'

  await event.reply(out_text, parse_mode=None)


@client.on(events.NewMessage(pattern=r'/start parse$'))
@utils.whitelist
async def parse_from_start(event: events.NewMessage.Event):
  query = last_query_cache.get(event.sender_id, None)
  if not query:
    await event.respond('No previous query found.')
    return
  await parse(event, query)