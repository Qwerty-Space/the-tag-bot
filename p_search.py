from telethon import events

from data_model import MediaTypes, InlineResultID
from p_help import add_to_help
import p_media_mode
from proxy_globals import client
import db, utils, query_parser
from constants import MAX_RESULTS_PER_PAGE
from telethon.tl.types import InlineQueryPeerTypeSameBotPM, InputDocument, InputPhoto, UpdateBotInlineSend


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

  switch_pm_text, switch_pm_param = media_mode_handler.get_inline_switch_pm(
    is_pm=is_in_pm, query_str=event.text, parsed_query=q
  )
  # TODO: move to transfer plugin
  # if media_mode_handler and media_mode_handler.base.inline:
  #   switch_pm_text = ('Remove all from ' if should_delete else 'Add all to ') + media_mode_handler.base.name
  #   switch_pm_param = f'{media_mode_handler.base.name}_{cache_id}'

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
    cache_time=0 if switch_pm_text else 5,
    private=True,
    next_offset=f'{offset + 1}' if total > MAX_RESULTS_PER_PAGE else None,
    switch_pm=switch_pm_text,
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
  q = query_parser.parse_query(query)
  if q.warnings:
    out_text += 'Errors:\n' + '\n'.join(q.warnings) + '\n'

  out_text += '\nParsed fields:\n' + q.pretty()

  await event.respond(out_text, parse_mode=None)


p_media_mode.default_inline_handler.get_start_text = (
  lambda q, is_pm: f'{len(q.warnings)} Warning(s)' if q.warnings else ''
)
p_media_mode.default_inline_handler.on_start = parse
