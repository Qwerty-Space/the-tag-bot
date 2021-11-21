import os
import mimetypes
import time

from telethon import events
from telethon.tl.types import UpdateBotInlineSend
from constants import INDEX

from proxy_globals import client
from emoji_extractor import strip_emojis
from data_model import TaggedDocument, InlineResultID
from query_parser import ParsedQuery, format_tagged_doc, parse_tags
import db, utils
import p_cached
from p_help import add_to_help
import p_media_mode


def calculate_new_tags(doc: TaggedDocument, q: ParsedQuery):
  doc.tags = (doc.tags | q.get('tags')) - q.get('tags', is_neg=True)
  doc.emoji = (doc.emoji | q.get('emoji')) - q.get('emoji', is_neg=True)


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
@utils.extract_taggable_media
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
  calculate_new_tags(doc, q)

  try:
    await db.update_user_media(doc)
  except ValueError as e:
    return f'Error: {e}'

  await event.reply(
    format_tagged_doc(doc),
    parse_mode='HTML'
  )


@client.on(events.NewMessage(pattern=r'/add(.+)?$'))
@utils.whitelist
@add_to_help('add')
async def on_add(event: events.NewMessage.Event, show_help):
  """
  Allows you to add multiple items at once
  Usage: <code>/add [new tags]</code>
  """
  q = parse_tags(event.pattern_match[1] or '')
  if q.fields:
    out_text = 'Send me media to add it to your collection with the following info:'
    out_text += '\n\n' + q.pretty()
  else:
    out_text = (
      'Send me stickers* to add it to your collection'
      '\n<b>*Because you did not specify any tags with <code>/add [new tags]</code>, '
      'I will currently only accept stickers from sticker packs. '
      'Send <code>/add [new tags]</code> to be able to save other media with the specified tags.</b>'
    )
  out_text += '\n\nSend /done when you\'re finished adding media'
  await p_media_mode.set_user_handler(
    user_id=event.sender_id,
    name='add',
    chat=await event.get_input_chat(),
    q=q
  )
  await event.respond(out_text, parse_mode='HTML')


async def on_add_media(event, m_type, is_delete, q, chat):
  if is_delete:
    return await on_taggable_delete(event, m_type, is_delete)
  doc = await get_doc_from_file(event.sender_id, m_type, event.file)
  calculate_new_tags(doc, q)
  # Skip adding if no tags were provided and the document has no tags
  if not q.fields and not doc.tags and not doc.emoji:
    return

  try:
    await db.update_user_media(doc)
  except ValueError as e:
    await event.reply(f'Error: {e}')
    # TODO: cancel only if media limit reached
    return p_media_mode.Cancel

  await event.reply(
    format_tagged_doc(doc),
    parse_mode='HTML'
  )


async def on_add_done(chat, q):
  await client.send_message(
    chat,
    'Done adding media? Now use me inline to search your media!',
    buttons=[[utils.inline_pm_button('Search', '')]]
  )


async def on_add_cancel(chat, q, replaced_with_self):
  if replaced_with_self:
    return
  await client.send_message(
    chat,
    'The previous add operation was cancelled (any media sent was still saved, however)'
  )


@client.on(events.NewMessage(pattern=r'/set(.+)?$'))
@utils.whitelist
@utils.extract_taggable_media
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
@utils.extract_taggable_media
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
@utils.extract_taggable_media
@add_to_help('delete', 'remove')
async def delete(event: events.NewMessage.Event, reply, m_type, show_help):
  """
  Deletes media that you have saved.
  Reply to media or use the button below to delete something
  """

  if not m_type:
    return await show_help(buttons=[[
      utils.inline_pm_button('Delete', 'delete:yes')
    ]])

  file_id = reply.file.media.id
  deleted = await db.delete_user_media(event.sender_id, file_id)
  await event.reply('Media deleted.' if deleted else 'Media not found.')


async def on_taggable_delete(event, m_type, is_delete):
  if not is_delete:
    return
  deleted = await db.delete_user_media(event.sender_id, event.file.media.id)
  await event.respond('Media deleted.' if deleted else 'Media not found.')

p_media_mode.default_handler.on_event = on_taggable_delete

p_media_mode.register_handler(p_media_mode.MediaHandler(
  name='add',
  on_event=on_add_media,
  on_done=on_add_done,
  on_cancel=on_add_cancel
))