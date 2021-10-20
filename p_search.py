from itertools import chain

from telethon import events, tl

from proxy_globals import client
import db, utils
from telethon.tl.types import InputDocument, InputPhoto, UpdateBotInlineSend


@client.on(events.Raw(UpdateBotInlineSend))
async def on_inline_selected(event):
  await db.update_last_used(event.user_id, int(event.id))


@client.on(events.InlineQuery())
@utils.whitelist
async def on_inline(event: events.InlineQuery.Event):
  def get_unmatched_tags(tag_str):
    return ' '.join(set(tag_str.split(' ')) - tags.pos - tags.neg) or m_type.value

  user_id = event.query.user_id
  tags = utils.parse_tags(event.text)
  m_type, tags = await db.get_corrected_user_tags(user_id, tags)
  if not m_type:
    await event.answer(
      switch_pm='Failed to parse media type',
      switch_pm_param='parse' # TODO: make this work
    )
    return

  offset = int(event.offset or 0)
  rows = await db.search_user_media(user_id, m_type, tags, offset)
  result_type = {
    # 'audio' only works for audio/mpeg, thanks durov
    utils.MediaTypes.audio: utils.MediaTypes.file
  }.get(m_type, m_type).value

  builder = event.builder
  if m_type == utils.MediaTypes.photo:
    get_result = lambda r: builder.photo(
      id=str(r['id']),
      file=InputPhoto(r['id'], r['access_hash'], b'')
    )
  else:
    get_result = (
      lambda r: builder.document(
        id=str(r['id']),
        file=InputDocument(r['id'], r['access_hash'], b''),
        type=result_type,
        title=r['title'] or get_unmatched_tags(r['all_tags'])
      )
    )
  await event.answer(
    [get_result(r) for r in rows],
    cache_time=5,
    private=True,
    next_offset=f'{offset + 1}' if len(rows) >= 50 else None
  )


@client.on(events.NewMessage(pattern=r'/parse (.+)'))
@utils.whitelist
async def parse(event: events.NewMessage.Event):
  def format_tags(tags):
    if tags.is_empty():
      return '[no tags]'
    return ' '.join(chain(tags.pos, (f'!{tag}' for tag in tags.neg)))

  tags = utils.parse_tags(event.pattern_match.group(1))
  out_text = f'parsed: <t:{tags.type}> {format_tags(tags)}'

  m_type, tags = await db.get_corrected_user_tags(event.sender_id, tags)
  if m_type:
    out_text += f'\ncorrected: <t:{m_type.value}> {format_tags(tags)}'
  else:
    out_text += '\ncorrected: <error> (unable to infer type)'

  # TODO: fix
  # if dropped:
  #   out_text += '\n\ndropped:'
  #   for row in dropped:
  #     out_text += f"\n{row['search_tag']} ≉ {row['match']} (Δ={round(row['dist'] * 100)}%)"

  await event.reply(out_text, parse_mode=None)
