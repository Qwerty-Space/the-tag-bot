import asyncio
import json
from io import BytesIO

from telethon import events

from proxy_globals import client, me
from p_transfer import DATA_VERSION, export_handler, send_transfer_stats
import db, utils
from query_parser import parse_query
from p_help import add_to_help
import p_media_mode


@client.on(events.NewMessage(pattern=r'/export$'))
@utils.whitelist
@add_to_help('export')
async def on_export(event: events.NewMessage.Event, show_help):
  """
  Exports part of or all of your data to share with friends
  """
  if p_media_mode.get_user_handler(event.sender_id).base is export_handler:
    return
  await db.mark_all_media(event.sender_id, False, True)
  await p_media_mode.set_user_handler(
    user_id=event.sender_id,
    name='export',
    chat=await event.get_input_chat()
  )
  await event.respond(
    (
      'Export initiated! Send me media from your collection to export it.'
      '\nYou can search for an item to add with the button below'
    ),
    parse_mode='HTML',
    buttons=[[utils.inline_pm_button('Export item', 'marked:n')]]
  )


@export_handler.register('on_start')
async def on_export_inline_start(event, query, chat):
  q = parse_query(query)
  is_delete = q.has('delete')
  r = await db.mark_all_media_from_query(event.sender_id, q, not is_delete)
  await send_transfer_stats(
    event,
    f'{"Uns" if is_delete else "S"}elected {r["updated"]} item(s) for export\n'
  )


@export_handler.register('get_start_text')
def get_start_text(q, is_pm):
  if not is_pm:
    return
  is_delete = q.has('delete')
  if is_delete:
    return 'Remove all from export'
  return 'Export all'


@export_handler.register('on_media')
async def on_export_media(event, m_type, is_delete, chat):
  file_id = event.file.media.id
  try:
    await db.mark_media(event.sender_id, file_id, not is_delete)
  except ValueError as e:
    await event.respond(f'Error: {e}')
    return

  await send_transfer_stats(
    event,
    f'{"Uns" if is_delete else "S"}elected <code>{file_id}</code> for export\n'
  )


@export_handler.register('on_done')
async def on_export_done(chat):
  #TODO: use count here to prevent holding docs in memory
  docs = await db.get_marked_media(chat.user_id)
  if not docs:
    return p_media_mode.Cancel
  await db.mark_all_media(chat.user_id, False)

  title = 'export'
  try:
    async with client.conversation(chat, total_timeout=60 * 10) as conv:
      await conv.send_message('Enter a title for the exported data, or /cancel to cancel the export.')
      while 1:
        resp = await conv.get_response()
        if resp.raw_text == '/cancel':
          return p_media_mode.Cancel
        if not resp.raw_text or resp.raw_text.startswith('/'):
          continue
        title = resp.raw_text
        break
  except asyncio.exceptions.TimeoutError:
    pass

  file = BytesIO(json.dumps(docs, sort_keys=True).encode('utf-8'))
  file.name = f'{title}.json' 
  await client.send_file(
    chat,
    caption=(
      f'/import_v{DATA_VERSION}'
      f'\nForward to @{me.username} to import'
      f' this collection of {len(docs)} item(s)'
    ),
    file=file,
    force_document=True
  )


@export_handler.register('on_cancel')
async def on_export_cancel(chat):
  r = await db.mark_all_media(chat.user_id, False)
  num_unmarked = r['updated']

  await client.send_message(
    chat,
    f'The export of {num_unmarked} item(s) was cancelled.'
    if num_unmarked else
    'The export was cancelled.'
  )
