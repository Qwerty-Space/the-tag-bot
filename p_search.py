from collections import defaultdict
from itertools import chain
from cachetools import LRUCache

from telethon import events

from proxy_globals import client
import db, utils, query_parser
from telethon.tl.types import InputDocument, InputPhoto, UpdateBotInlineSend


last_query_cache = LRUCache(128)


@client.on(events.Raw(UpdateBotInlineSend))
async def on_inline_selected(event):
  await db.update_last_used(event.user_id, int(event.id))


# @client.on(events.InlineQuery())
# @utils.whitelist
# async def on_inline(event: events.InlineQuery.Event):
#   def get_unmatched_tags(tag_str):
#     return ' '.join(set(tag_str.split(' ')) - tags.pos - tags.neg) or m_type.value

#   user_id = event.query.user_id
#   last_query_cache[user_id] = event.text
#   tags = utils.parse_tags(event.text)
#   m_type, tags, dropped = await db.get_corrected_user_tags(user_id, tags)
#   if not m_type:
#     await event.answer(
#       switch_pm='Failed to parse media type',
#       switch_pm_param='parse'
#     )
#     return

#   offset = int(event.offset or 0)
#   rows = await db.search_user_media(user_id, m_type, tags, offset)
#   result_type = {
#     # 'audio' only works for audio/mpeg, thanks durov
#     utils.MediaTypes.audio: utils.MediaTypes.file
#   }.get(m_type, m_type).value

#   builder = event.builder
#   if m_type == utils.MediaTypes.photo:
#     get_result = lambda r: builder.photo(
#       id=str(r['id']),
#       file=InputPhoto(r['id'], r['access_hash'], b'')
#     )
#   else:
#     get_result = (
#       lambda r: builder.document(
#         id=str(r['id']),
#         file=InputDocument(r['id'], r['access_hash'], b''),
#         type=result_type,
#         title=r['title'] or get_unmatched_tags(r['all_tags']) or result_type
#       )
#     )
#   await event.answer(
#     [get_result(r) for r in rows],
#     cache_time=0 if dropped else 5,
#     private=True,
#     next_offset=f'{offset + 1}' if len(rows) >= 50 else None,
#     switch_pm=f'{len(dropped)} tags dropped' if dropped else None,
#     switch_pm_param='parse'
#   )


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