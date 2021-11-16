import os
import mimetypes
import functools
import time

from telethon import events, tl

from proxy_globals import client
from emoji_extractor import strip_emojis
import p_cached
from p_help import add_to_help
from data_model import MediaTypes, TaggedDocument
from query_parser import parse_tags, ALIAS_TO_FIELD
import db, utils


def extract_taggable_media(handler):
  @functools.wraps(handler)
  async def wrapper(event, *args, **kwargs):
    reply = await event.get_reply_message()
    m_type = MediaTypes.from_media(reply.file.media) if reply and reply.file else None
    ret = await handler(event, reply=reply, m_type=m_type, *args, **kwargs)
    if isinstance(ret, str):
      await event.respond(ret)
    return ret
  return wrapper


def format_tagged_doc(doc: TaggedDocument):
  info = []
  for alias in ('t', 'e', 'fn', 'p', 'a'):
    key = ALIAS_TO_FIELD[alias].name
    value = getattr(doc, key)
    if value:
      info.append(f'{alias}:{value}')
  return (
    f'Info for {doc.id}:'
    f'\ninfo: {" ".join(info)}'
    f'\ntags: {utils.html_format_tags(doc.tags)}'
    + (f'\nemoji: {" ".join(doc.emoji)}' if doc.emoji else '')
  )


async def get_media_generated_attrs(file):
  ext = mimetypes.guess_extension(file.mime_type)
  if file.name:
    ext = os.path.splitext(file.name)[1] or ext

  attrs = {
    'ext': ext.strip('.'),
    'is_animated': (file.mime_type == 'application/x-tgsticker'),
  }

  if file.emoji:
    _, attrs['emoji'] = strip_emojis(file.emoji)
  pack = await p_cached.get_sticker_pack(file.sticker_set)
  if pack:
    attrs['pack_name'] = pack.title
    attrs['pack_link'] = pack.short_name
    attrs['emoji'] = pack.sticker_emojis[file.media.id]

  # don't include filename for stickers with a pack
  if file.name and not pack:
    attrs['filename'] = file.name

  if file.title:
    attrs['title'] = file.title
  if file.performer and file.title:
    attrs['title'] = f'{file.performer} - {file.title}'

  return attrs


async def get_doc_from_file(owner, m_type, file):
  file_id, access_hash = file.media.id, file.media.access_hash
  doc = (
    await db.get_user_media(owner, file_id)
    or TaggedDocument(
      owner=owner, id=file_id, access_hash=access_hash, type=m_type
    )
  )

  gen_attrs = await get_media_generated_attrs(file)
  # don't replace user emoji with ones from pack
  if doc.emoji:
    gen_attrs.pop('emoji', None)
  doc = doc.merge(**gen_attrs)
  doc.last_used = round(time.time())

  return doc


@client.on(events.NewMessage())
@utils.whitelist
@extract_taggable_media
async def on_tag(event, reply, m_type):
  m = event.message
  if m.raw_text[:1] in {'/', '.'}:
    return
  if not reply or not reply.media:
    return
  if not m_type:
    return 'I don\'t know how to handle that media type yet!'

  q = parse_tags(m.raw_text)
  if not q.fields:
    return

  doc = await get_doc_from_file(event.sender_id, m_type, reply.file)

  # calculate new tags and emoji
  doc.tags = (doc.tags | q.get('tags')) - q.get('tags', is_neg=True)
  doc.emoji = (doc.emoji | q.get('emoji')) - q.get('emoji', is_neg=True)

  try:
    await db.update_user_media(doc)
  except ValueError as e:
    return f'Error: {e}'

  await event.reply(
    format_tagged_doc(doc),
    parse_mode='HTML'
  )


@client.on(events.NewMessage(pattern=r'/set(.+)?$'))
@utils.whitelist
@extract_taggable_media
@add_to_help('set')
async def set_tags(event: events.NewMessage.Event, reply, m_type, show_help):
  """
  Sets (replaces) the tags for media
  Reply to media to use this command. Note that any existing tags will be lost!
  Usage: <code>/set [new tags]</code>
  """
  if not reply or not m_type or not event.pattern_match[1]:
    return await show_help()

  q = parse_tags(event.pattern_match[1])
  if not q.fields:
    return

  doc = await get_doc_from_file(event.sender_id, m_type, reply.file)

  new_tags, new_emoji = q.get('tags'), q.get('emoji')
  if new_tags:
    doc.tags = new_tags
  if new_emoji:
    doc.emoji = new_emoji

  try:
    await db.update_user_media(doc)
  except ValueError as e:
    return f'Error: {e}'

  await event.reply(
    format_tagged_doc(doc),
    parse_mode='HTML'
  )


@client.on(events.NewMessage(pattern=r'/tags$'))
@utils.whitelist
@extract_taggable_media
@add_to_help('tags')
async def show_tags(event: events.NewMessage.Event, reply, m_type, show_help):
  """
  Shows the tags for media that you have saved
  Reply to media to use this command.
  """

  if not m_type:
    return await show_help()

  file_id = reply.file.media.id
  doc = await db.get_user_media(event.sender_id, file_id)
  if not doc:
    await event.reply('No tags found.')
    return

  await event.reply(
    format_tagged_doc(doc),
    parse_mode='HTML'
  )


@client.on(events.NewMessage(pattern=r'/(delete|remove)$'))
@utils.whitelist
@extract_taggable_media
@add_to_help('delete', 'remove')
async def delete(event: events.NewMessage.Event, reply, m_type, show_help):
  """
  Deletes media that you have saved.
  Reply to media to use this command.
  """

  if not m_type:
    return await show_help()

  file_id = reply.file.media.id
  deleted_res = await db.delete_user_media(event.sender_id, file_id)
  await event.reply('Media deleted.' if deleted_res else 'Media not found.')