import os
import mimetypes
from collections import defaultdict
import functools

from telethon import events, tl
from telethon.network import mtprotosender

from proxy_globals import client
import p_cached
import db, utils


def extract_taggable_media(handler):
  @functools.wraps(handler)
  async def wrapper(event, *args, **kwargs):
    reply = await event.get_reply_message()
    m_type = utils.get_media_type(reply.file.media) if reply else None
    return await handler(event, reply=reply, m_type=m_type, *args, **kwargs)
  return wrapper


def format_tags(media_name, m_type, metatags, tags):
  return (
    f'Tags for {media_name}:'
    f'\nmeta: [t:{m_type.value}] {utils.html_format_tags(metatags)}'
    f'\n{utils.html_format_tags(tags)}'
  )


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
  return file_title, ' '.join(tags)


@client.on(events.NewMessage())
@utils.whitelist
@extract_taggable_media
async def on_tag(event, reply, m_type):
  m = event.message
  if m.raw_text.startswith('/'):
    return
  if not reply or not reply.media:
    return
  if not m_type:
    await event.respond("I don't know how to handle that media type yet!")
    return
  file_id, access_hash = reply.file.media.id, reply.file.media.access_hash

  tags = utils.parse_tags(m.raw_text)
  if tags.is_empty():
    return
  old_tags = await db.get_media_user_tags(file_id, m.sender_id)
  old_tags = set(old_tags.split(' ')) if old_tags else set()

  new_tags = ' '.join((old_tags | tags.pos) - tags.neg)
  title, metatags = await get_media_generated_tags(reply.file)
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
    format_tags(file_id, m_type, metatags, new_tags),
    parse_mode='HTML'
  )


@client.on(events.NewMessage(pattern=r'/type_tags ?(.*)'))
@utils.whitelist
@extract_taggable_media
async def my_tags(event: events.NewMessage.Event, reply, m_type):
  type_str = event.pattern_match.group(1) or utils.MediaTypes.sticker.value
  if not m_type:
    m_type = await db.get_corrected_media_type(type_str)

  if not m_type:
    await event.reply('I don\'t understand what type of media that is!')
    return

  rows = await db.get_user_tags_for_type(event.sender_id, m_type)
  if not rows:
    await event.reply(
      f'You have not tagged any media of type "t:{m_type.value}"".'
    )
    return

  group_by_count = defaultdict(list)
  for r in rows:
    group_by_count[r['count']].append(r['name'])

  out_text = '\n'.join(
    f"({count}) {' '.join(names)}" for count, names in group_by_count.items()
  )
  await event.reply(
    f'Your tags for "t:{m_type.value}":\n{out_text}',
    parse_mode=None
  )


@client.on(events.NewMessage(pattern=r'/show_tags$'))
@utils.whitelist
@extract_taggable_media
async def show_tags(event: events.NewMessage.Event, reply, m_type):
  if not m_type:
    await event.reply('Reply to media to use this command.')
    return

  file_id = reply.file.media.id
  row = await db.get_media_tags(file_id, event.sender_id)
  if not row:
    await event.reply('No tags found.')
    return

  await event.reply(
    format_tags(file_id, m_type, row['metatags'], row['tags']),
    parse_mode='HTML'
  )


@client.on(events.NewMessage(pattern=r'/(delete|remove)$'))
@utils.whitelist
@extract_taggable_media
async def show_tags(event: events.NewMessage.Event, reply, m_type):
  if not m_type:
    await event.reply('Reply to media to use this command.')
    return

  file_id = reply.file.media.id
  deleted_id = await db.delete_media(file_id, event.sender_id)
  await event.reply('Media deleted.' if deleted_id else 'Media not found.')