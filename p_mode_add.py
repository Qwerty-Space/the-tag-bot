
from telethon import events

from proxy_globals import client
from query_parser import format_tagged_doc, parse_tags
import db, utils
from p_help import add_to_help
import p_media_mode
from p_tagging import get_doc_from_file, calculate_new_tags


add_handler = p_media_mode.create_handler('add')


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


@add_handler.register('on_event')
async def on_add_media(event, m_type, is_delete, q, chat):
  if is_delete:
    return await p_media_mode.default_handler.on_event(event, m_type, is_delete)
  doc = await get_doc_from_file(event.sender_id, m_type, event.file)
  calculate_new_tags(doc, q)
  # Skip adding if no tags were provided and the document has no tags
  if not q.fields and not doc.tags and not doc.emoji:
    return

  try:
    await db.update_user_media(doc)
  except ValueError as e:
    await event.reply(f'Error: {e}')
    return p_media_mode.Cancel

  await event.reply(
    format_tagged_doc(doc),
    parse_mode='HTML'
  )


@add_handler.register('on_done')
async def on_add_done(chat, q):
  await client.send_message(
    chat,
    'Done adding media? Now use me inline to search your media!',
    buttons=[[utils.inline_pm_button('Search', '')]]
  )


@add_handler.register('on_cancel')
async def on_add_cancel(chat, q, replaced_with_self):
  if replaced_with_self:
    return
  await client.send_message(
    chat,
    'The previous add operation was cancelled (any media sent was still saved, however)'
  )
