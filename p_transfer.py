import functools
import json
from io import BytesIO

from telethon import events

from proxy_globals import client, me
import db, utils
from p_help import add_to_help
import p_media_mode
import p_stats


def current_transfer_type(user_id: int):
  handler = p_media_mode.user_media_handlers.get(user_id)
  if handler and handler.name in {'import', 'export'}:
    return handler.name
  return False


def check_transferring(handler):
  @functools.wraps(handler)
  async def wrapper(event, *args, **kwargs):
    transfer_type = current_transfer_type(event.sender_id)
    if not transfer_type:
      return
    return await handler(event, *args, **kwargs, transfer_type=transfer_type)
  return wrapper


@client.on(events.NewMessage(pattern=r'/(delete|remove)$'))
@utils.whitelist
@check_transferring
async def delete(event: events.NewMessage.Event, transfer_type):
  await event.reply(
    f'Use the button below to delete an item from your {transfer_type}',
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
  if p_media_mode.get_user_handler_name(event.sender_id) == 'export':
    return
  await db.mark_all_user_media(event.sender_id, False)
  await p_media_mode.set_user_handler(
    name='export',
    user_id=event.sender_id,
    on_event=on_export_media,
    on_done=on_export_done,
    on_cancel=on_export_cancel,
    extra_kwargs={
      'chat': await event.get_input_chat()
    }
  )
  await event.respond(
    (
      'Export initiated! Send me media from your collection to export it.'
      '\nYou can search for an item to add with the button below'
    ),
    parse_mode='HTML',
    buttons=[[utils.inline_pm_button('Export item', 'marked:n')]]
  )


async def on_export_media(event, m_type, is_delete, chat):
  file_id = event.file.media.id
  try:
    await db.mark_user_media(event.sender_id, file_id, not is_delete)
  except ValueError as e:
    await event.reply(f'Error: {e}')
    return

  msg = [
    f'{"Removed" if is_delete else "Added"} <code>{file_id}</code> to the export\n'
  ]

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


async def on_export_done(chat):
  docs = await db.get_marked_user_media(chat.user_id)
  if not docs:
    return p_media_mode.Cancel
  await db.mark_all_user_media(chat.user_id, False)

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
      f' this collection of {len(docs)} items'
    ),
    file=file,
    force_document=True
  )


async def on_export_cancel(chat, replaced_with_self):
  r = await db.mark_all_user_media(chat.user_id, False)
  num_unmarked = r['updated']

  await client.send_message(
    chat,
    f'The export of {num_unmarked} item(s) was cancelled.'
    if num_unmarked else
    'The export was cancelled.'
  )

# add from query (for export)
# delete from query