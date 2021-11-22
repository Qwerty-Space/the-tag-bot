from dataclasses import dataclass, field
from random import randint

from cachetools import TTLCache
from telethon import events

from data_model import MediaTypes, InlineResultID
from p_help import add_to_help
import p_media_mode
from proxy_globals import client
import db, utils, query_parser
from constants import MAX_RESULTS_PER_PAGE
from telethon.tl.types import InlineQueryPeerTypeSameBotPM, InputDocument, InputPhoto, UpdateBotInlineSend


# TODO: cache PM separately from others
last_query_cache = TTLCache(maxsize=float('inf'), ttl=60 * 20)

@dataclass
class CachedQuery:
  query: str
  id: str = field(default_factory=lambda: f'{randint(0, 0xFFFFFFFF):08X}')


@client.on(events.Raw(UpdateBotInlineSend))
async def on_inline_selected(event):
  id = InlineResultID.unpack(event.id)
  if id.skip_update:
    return
  await db.update_last_used(event.user_id, id.id)


# TODO: refactor blocks into subfunctions
@client.on(events.InlineQuery())
@utils.whitelist
async def on_inline(event: events.InlineQuery.Event):
  # TODO: highlight matches
  # https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html#matched-fields
  def get_doc_title(d):
    if d.title and not show_types:
      return d.title
    out_title = ' '.join(d.tags)
    if d.title:
      out_title = f'{d.title}; {out_title}'
    if len(out_title) >= 128:
      out_title = out_title[:128].rsplit(' ', 1)[0] + '…'
    if show_types:
      return f'[{d.type.value}] {out_title}'
    return out_title or f'[{d.type.value}]'

  user_id = event.query.user_id
  last_query_cache[user_id] = CachedQuery(event.text)
  cache_id = last_query_cache[user_id].id
  q = query_parser.parse_query(event.text)
  offset = int(event.offset or 0)
  is_transfer = q.has('show_transfer')  # TODO: put in db module
  total, docs = await db.search_user_media(
    owner=user_id, query=q, page=offset, is_transfer=is_transfer
  )

  res_type = MediaTypes(q.get_first('type'))
  # 'audio' only works for audio/mpeg, thanks durov
  if res_type == MediaTypes.audio:
    res_type = MediaTypes.file
  show_types = (res_type == MediaTypes.document)
  # display special document type as files
  if show_types:
    res_type = MediaTypes.file
  gallery_types = {MediaTypes.gif, MediaTypes.sticker, MediaTypes.photo, MediaTypes.video}

  media_mode_handler = p_media_mode.get_user_handler(user_id)
  is_in_pm = isinstance(event.query.peer_type, InlineQueryPeerTypeSameBotPM)
  should_delete = q.has('delete') and is_in_pm
  if is_in_pm:
    p_media_mode.set_delete_next(user_id, should_delete)
  skip_update = should_delete or (media_mode_handler and is_in_pm)

  # TODO: make this a method of the media mode handler
  switch_pm_text = None
  switch_pm_param = 'parse'
  if media_mode_handler and media_mode_handler.base.inline:
    switch_pm_text = ('Remove all from ' if should_delete else 'Add all to ') + media_mode_handler.base.name
    switch_pm_param = f'{media_mode_handler.base.name}_{cache_id}'

  builder = event.builder
  if res_type == MediaTypes.photo:
    get_result = lambda d: builder.photo(
      id=InlineResultID(d.id, skip_update).pack(),
      file=InputPhoto(d.id, d.access_hash, b'')
    )
  else:
    get_result = (
      lambda d: builder.document(
        id=InlineResultID(d.id, skip_update).pack(),
        file=InputDocument(d.id, d.access_hash, b''),
        type=res_type.value,
        title=get_doc_title(d),
        description=''.join(d.emoji) or None
      )
    )
  await event.answer(
    [get_result(d) for d in docs],
    cache_time=0 if warnings or skip_update or is_transfer else 5,
    private=True,
    next_offset=f'{offset + 1}' if total > MAX_RESULTS_PER_PAGE else None,
    switch_pm=f'{len(warnings)} Warning(s)' if warnings else switch_pm_text,
    switch_pm_param=switch_pm_param,
    gallery=(res_type in gallery_types)
  )


@client.on(events.NewMessage(pattern=r'/parse( .+)?'))
@utils.whitelist
@add_to_help('parse')
async def parse(event: events.NewMessage.Event, show_help, query=None):
  """
  Parses a query (for debugging)
  Shows the result of parsing a query, normally you shouldn't have to use this.
  Usage <code>/parse [query here]</code>
  """
  query = query or event.pattern_match.group(1)
  if not query:
    return await show_help()

  out_text = ''
  if q.warnings:
    out_text += 'Errors:\n' + '\n'.join(q.warnings) + '\n'

  out_text += '\nParsed fields:\n' + q.pretty()

  await event.reply(out_text, parse_mode=None)


@client.on(events.NewMessage(pattern=r'/start parse$'))
@utils.whitelist
async def parse_from_start(event: events.NewMessage.Event):
  query = last_query_cache.get(event.sender_id, None)
  if not query:
    await event.respond('No previous query found.')
    return
  await parse(event, query=query)


@client.on(events.NewMessage(pattern=r'/start parse$'))
@utils.whitelist
async def parse_from_start(event: events.NewMessage.Event):
  query = last_query_cache.get(event.sender_id, None)
  if not query:
    await event.respond('No previous query found.')
    return
  await parse(event, query=query)


# TODO: move this to media mode plugin
@client.on(events.NewMessage(pattern=r'/start (\w+)_([\dABCDEF]{8})$'))
@utils.whitelist
async def media_mode_start(event: events.NewMessage.Event):
  name = event.pattern_match[1]
  handler = p_media_mode.get_user_handler(event.sender_id)
  if not handler or handler.name != name or not handler.inline_start:
    return

  query = last_query_cache.get(event.sender_id, None)
  cache_id = event.pattern_match[2]
  if not query or query.id != cache_id:
    await event.respond('Error: query not found, please try again')
    return
  q, warnings = query_parser.parse_query(query.query)
  await handler.inline_start(event, q)