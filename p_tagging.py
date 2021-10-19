import os
from itertools import chain
import mimetypes

from telethon import events, tl
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputDocument

from proxy_globals import client
import p_cached
import db, utils


async def get_media_metatags(file):
  tags = [f't:{utils.get_media_type(file.media)}']

  if file.mime_type == 'application/x-tgsticker':
    tags.append('t:animated')

  pack = await p_cached.get_sticker_pack(file.sticker_set)
  print(pack)
  if pack:
    tags.append(utils.sanitise_tag(f'g:{pack.title}'))

  exts = set(mimetypes.guess_all_extensions(file.mime_type))
  if file.name:
    ext = os.path.splitext(file.name)[1]
    if ext:
      exts.add(ext)
  tags.extend(f"e:{ext.lstrip('.')}" for ext in exts)
  return ' '.join(tags)


@client.on(events.InlineQuery())
async def on_inline(event: events.InlineQuery.Event):
  user_id = event.query.user_id
  tags = utils.parse_tags(event.text)
  tags, _ = await db.get_corrected_user_tags(user_id, tags)
  # print(event.stringify())
  rows = await db.search_user_media(user_id, tags)
  print(rows)
  builder = event.builder
  await event.answer(
    [
      builder.document(InputDocument(r['id'], r['access_hash'], b''), '', type='photo')
      for r in rows
    ],
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
  metatags = await get_media_metatags(reply.file)
  await db.set_media_tags(
    file_id, m.sender_id, access_hash, metatags, new_tags
  )
  await event.reply(
    f'Tags for {file_id}:\n[meta] {metatags}\n{new_tags}',
    parse_mode=None
  )


@client.on(events.NewMessage(pattern=r'/parse (.+)'))
async def parse(event: events.NewMessage.Event):
  def format_tags(tags):
    if tags.is_empty():
      return '<empty>'
    return ' '.join(chain(tags.pos, (f'!{tag}' for tag in tags.neg)))

  query = event.pattern_match.group(1)
  tags = utils.parse_tags(query)
  if tags.is_empty():
    await event.reply('No valid tags found.')
    return

  out_text = f'input: {format_tags(tags)}'

  tags, dropped = await db.get_corrected_user_tags(event.sender_id, tags)
  out_text += f'\noutput: {format_tags(tags)}'

  if dropped:
    out_text += '\n\ndropped:'
    for row in dropped:
      out_text += f"\n{row['search_tag']} ≉ {row['match']} (Δ={round(row['dist'] * 100)}%)"

  await event.reply(out_text, parse_mode=None)


@client.on(events.NewMessage(pattern='/mytags'))
async def my_tags(event: events.NewMessage.Event):
  rows = await db.get_user_tags(event.sender_id)
  if not rows:
    await event.reply('You have not tagged any media.')
    return

  out_text = '\n'.join(
    f"{r['name']} ({r['count']})" for r in rows
  )
  await event.reply(
    f'Your tags (including metatags):\n{out_text}',
    parse_mode=None
  )
