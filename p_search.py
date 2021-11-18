from collections import defaultdict
from itertools import chain
from cachetools import LRUCache

from telethon import events

from data_model import MediaTypes, InlineResultID
from p_help import add_to_help
from p_media_mode import set_ignore_next
from proxy_globals import client
import db, utils, query_parser
from constants import MAX_RESULTS_PER_PAGE, INDEX
from telethon.tl.types import InlineQueryPeerTypeSameBotPM, InputDocument, InputPhoto, UpdateBotInlineSend


last_query_cache = LRUCache(128)


@client.on(events.Raw(UpdateBotInlineSend))
async def on_inline_selected(event):
  id = InlineResultID.unpack(event.id)
  if id.should_remove:
    return
  await db.update_last_used(event.user_id, id.id)


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
  last_query_cache[user_id] = event.text
  q, warnings = query_parser.parse_query(event.text)
  offset = int(event.offset or 0)
  is_transfer = q.has('show_transfer')
  docs = await db.search_user_media(
    owner=user_id, query=q, page=offset, is_transfer=is_transfer
  )

  res_type = MediaTypes(q.get_first('type'))
  # 'audio' only works for audio/mpeg, thanks durov
  if res_type == MediaTypes.audio:
    res_type = MediaTypes.file
  show_types = False
  # display special document type as files
  if res_type == MediaTypes.document:
    res_type = MediaTypes.file
    show_types = True
  gallery_types = {MediaTypes.gif, MediaTypes.sticker, MediaTypes.photo, MediaTypes.video}

  is_in_pm = isinstance(event.query.peer_type, InlineQueryPeerTypeSameBotPM)
  should_remove = q.has('delete') and is_in_pm
  if is_in_pm:
    set_ignore_next(user_id, should_remove)

  builder = event.builder
  if res_type == MediaTypes.photo:
    get_result = lambda d: builder.photo(
      id=InlineResultID(d.id, should_remove).pack(),
      file=InputPhoto(d.id, d.access_hash, b'')
    )
  else:
    get_result = (
      lambda d: builder.document(
        id=InlineResultID(d.id, should_remove).pack(),
        file=InputDocument(d.id, d.access_hash, b''),
        type=res_type.value,
        title=get_doc_title(d),
        description=''.join(d.emoji) or None
      )
    )
  await event.answer(
    [get_result(d) for d in docs],
    cache_time=0 if warnings or should_remove or is_transfer else 5,
    private=True,
    next_offset=f'{offset + 1}' if len(docs) >= MAX_RESULTS_PER_PAGE else None,
    switch_pm=f'{len(warnings)} Warning(s)' if warnings else None,
    switch_pm_param='parse',
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
  q, warnings = query_parser.parse_query(query)
  if warnings:
    out_text += 'Errors:\n' + '\n'.join(warnings) + '\n'

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