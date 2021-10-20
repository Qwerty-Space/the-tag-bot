import os
from itertools import chain
import mimetypes

from telethon import events, tl
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputDocument, InputPhoto

from proxy_globals import client
import p_cached
import db, utils


async def get_media_generated_tags(file):
  tags = []

  if file.mime_type == 'application/x-tgsticker':
    tags.append('a:animated')

  pack = await p_cached.get_sticker_pack(file.sticker_set)
  if pack:
    tags.append(utils.sanitise_tag(f'g:{pack.title}'))

  ext = mimetypes.guess_extension(file.mime_type)

  # TODO: maybe extract file name to tags
  file_title = file.name or ''
  if file.performer and file.title:
    file_title = f'{file.performer} - {file.title}'
    tags.append(utils.sanitise_tag(f'a:{file.performer}'))
    tags.append(utils.sanitise_tag(f'n:{file.title}'))

  if file.name:
    file_ext = os.path.splitext(file.name)[1]
    if file_ext:
      ext = file_ext
  tags.append(f"e:{ext.lstrip('.')}")
  return utils.get_media_type(file.media), file_title, ' '.join(tags)


@client.on(events.InlineQuery())
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

  rows = await db.search_user_media(user_id, m_type, tags)
  result_type = {
    # 'audio' only works for audio/mpeg, thanks durov
    utils.MediaTypes.audio: utils.MediaTypes.file
  }.get(m_type, m_type).value

  builder = event.builder
  if m_type == utils.MediaTypes.photo:
    get_result = lambda r: builder.photo(InputPhoto(r['id'], r['access_hash'], b''))
  else:
    get_result = (
      lambda r: builder.document(
        InputDocument(r['id'], r['access_hash'], b''),
        type=result_type,
        title=r['title'] or get_unmatched_tags(r['all_tags'])
      )
    )
  await event.answer(
    [get_result(r) for r in rows],
    cache_time=0,
    private=True,
  )


@client.on(events.NewMessage())
async def on_tag(event):
  m = event.message
  if not m.is_reply or m.raw_text.startswith('/'):
    return
  reply = await event.get_reply_message()
  if not reply.media:
    return
  if not isinstance(reply.media, (tl.types.MessageMediaDocument, tl.types.MessageMediaPhoto)):
    await event.respond("I don't know how to handle that media type yet!")
    return
  file_id, access_hash = reply.file.media.id, reply.file.media.access_hash

  tags = utils.parse_tags(m.raw_text)
  if tags.is_empty():
    return
  old_tags = await db.get_media_tags(file_id, m.sender_id)
  old_tags = set(old_tags.split(' ')) if old_tags else set()

  new_tags = ' '.join((old_tags | tags.pos) - tags.neg)
  m_type, title, metatags = await get_media_generated_tags(reply.file)
  await db.set_media_tags(
    id=file_id,
    owner=m.sender_id,
    access_hash=access_hash,
    m_type=m_type,
    title=title,
    metatags=metatags,
    tags=new_tags
  )
  await event.reply(
    f'Tags for {file_id}:\n[meta] <t:{m_type.value}> {metatags}\n{new_tags}',
    parse_mode=None
  )


@client.on(events.NewMessage(pattern=r'/parse (.+)'))
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


@client.on(events.NewMessage(pattern=r'/mytags ?(.*)'))
async def my_tags(event: events.NewMessage.Event):
  type_str = event.pattern_match.group(1) or utils.MediaTypes.sticker.value
  m_type = await db.get_corrected_media_type(type_str)
  if not my_tags:
    await event.reply('I don\'t understand what that type refers to!')
    return

  rows = await db.get_user_tags_for_type(event.sender_id, m_type)
  if not rows:
    await event.reply('You have not tagged any media of that type.')
    return

  out_text = '\n'.join(
    f"{r['name']} ({r['count']})" for r in rows
  )
  await event.reply(
    f'Your tags for t:{m_type.value}:\n{out_text}',
    parse_mode=None
  )
