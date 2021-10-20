import os
import mimetypes

from telethon import events, tl

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
  elif isinstance(file.sticker_set, tl.types.InputStickerSetEmpty):
    tags.append('g:none')

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


@client.on(events.NewMessage())
@utils.whitelist
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


@client.on(events.NewMessage(pattern=r'/mytags ?(.*)'))
@utils.whitelist
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
