import functools
import json
from io import BytesIO

from telethon import events

from proxy_globals import client, me
import db, utils
from query_parser import parse_query
from p_help import add_to_help
import p_media_mode
import p_stats


export_handler = p_media_mode.create_handler('export')
import_handler = p_media_mode.create_handler('import')


def check_transferring(callback):
  @functools.wraps(callback)
  async def wrapper(event, *args, **kwargs):
    handler = p_media_mode.get_user_handler(event.sender.id)
    if handler not in {export_handler, import_handler}:
      return
    return await callback(event, *args, **kwargs, transfer_type=handler.name)
  return wrapper


@client.on(events.NewMessage(pattern=r'/(delete|remove)$'))
@utils.whitelist
@check_transferring
async def delete(event: events.NewMessage.Event, transfer_type):
  await event.respond(
    f'Use the button below to unselect an item for the {transfer_type}',
    buttons=[[utils.inline_pm_button('Delete', 'marked:y delete:y')]]
  )
  raise events.StopPropagation


@client.on(events.NewMessage(pattern=r'/export$'))
@utils.whitelist
@add_to_help('export')
async def on_export(event: events.NewMessage.Event, show_help):
  """
  Exports part of or all of your data to share with friends
  """
  if p_media_mode.get_user_handler(event.sender_id) is export_handler:
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


async def export_stats(event, initial_msg=None):
  msg = []
  if initial_msg:
    msg.append(initial_msg)

  stats = await p_stats.get_stats(event.sender_id, only_marked=True)
  buttons = [utils.inline_pm_button('Add', 'marked:n')]

  if stats.sub_total:
    msg.append(f'Here\'s a summary of what will be exported:\n{stats.pretty()}\n')
    msg.append(
      'You can add or remove some items with the buttons below, '
      'use /done to finalize the export, or /cancel it.'
    )
    buttons.append(utils.inline_pm_button('Remove', 'marked:y delete:y'))
  else:
    msg.append(
      'No items are marked to be exported, use the button below '
      'to add some or /cancel the export.'
    )

  await event.respond(
    '\n'.join(msg),
    parse_mode='HTML',
    buttons=[buttons]
  )


@export_handler.register('on_start')
async def on_export_inline_start(event, query, chat):
  q = parse_query(query)
  is_delete = q.has('delete')
  r = await db.mark_all_media_from_query(event.sender_id, q, not is_delete)
  await export_stats(
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

  await export_stats(
    event,
    f'{"Uns" if is_delete else "S"}elected <code>{file_id}</code> for export\n'
  )


@export_handler.register('on_done')
async def on_export_done(chat):
  docs = await db.get_marked_media(chat.user_id)
  if not docs:
    return p_media_mode.Cancel
  await db.mark_all_media(chat.user_id, False)

  async with client.conversation(chat) as conv:
    await conv.send_message('Enter a title for the exported data, or /cancel to cancel the export.')
    resp = await conv.get_response()
    if resp.raw_text.startswith('/'):
      return

  file = BytesIO(json.dumps(docs, sort_keys=True).encode('utf-8'))
  file.name = f'{resp.raw_text}.json' 
  await client.send_file(
    chat,
    caption=(
      f'/import\nForward to @{me.username} to import'
      f' this collection of {len(docs)} item(s)'
    ),
    file=file,
    force_document=True
  )


@export_handler.register('on_cancel')
async def on_export_cancel(chat, replaced_with_self):
  r = await db.mark_all_media(chat.user_id, False)
  num_unmarked = r['updated']

  await client.send_message(
    chat,
    f'The export of {num_unmarked} item(s) was cancelled.'
    if num_unmarked else
    'The export was cancelled.'
  )
