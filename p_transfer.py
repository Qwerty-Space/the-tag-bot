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
    buttons=[[utils.inline_pm_button('Delete', 'pending:yes delete:yes')]]
  )
  raise events.StopPropagation


@client.on(events.NewMessage(pattern=r'/export$'))
@utils.whitelist
@add_to_help('export')
async def on_export(event: events.NewMessage.Event, show_help):
  """
  Exports part of or all of your data to share with friends
  """
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
    buttons=[[utils.inline_pm_button('Export item', '')]]
  )


async def on_export_media(event, m_type, chat):
  file_id = event.file.media.id
  try:
    await db.copy_to_transfer_index(event.sender_id, file_id)
  except ValueError as e:
    await event.reply(f'Error: {e}')
    return

  await p_stats.stats(
    event,
    pre_text=(
      f'Media (<code>{file_id}</code>) added to export list. '
      'Use /done to finalize the export.\n'
    ),
    extra_buttons=[
      utils.inline_pm_button('Add', ''),
      utils.inline_pm_button('Remove', 'pending:yes delete:yes')
    ]
  )


async def on_export_done(chat):
  docs = await db.clear_transfer_index(chat.user_id, pop=True)
  if not docs:
    return p_media_mode.Cancel

  async with client.conversation(chat) as conv:
    await conv.send_message('Enter a title for the exported data, or /cancel to cancel the export.')
    resp = await conv.get_response()
    if resp.raw_text.startswith('/'):
      return

  file = BytesIO(json.dumps(docs, sort_keys=True).encode('utf-8'))
  file.name = f'{resp.raw_text}.json' 
  await client.send_file(
    chat,
    caption=f'/import\nForward to @{me.username} to import this collection',
    file=file,
    force_document=True
  )


async def on_export_cancel(chat, replaced_with_self):
  num_deleted = await db.clear_transfer_index(chat.user_id)
  if replaced_with_self:
    return
  await client.send_message(
    chat,
    f'The export of {num_deleted} item(s) was cancelled.'
    if num_deleted else
    'The export was cancelled.'
  )
