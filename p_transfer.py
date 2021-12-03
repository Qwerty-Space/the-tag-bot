import functools

from telethon import events

from proxy_globals import client
import utils
import p_media_mode
import p_stats


# Only collections with this version will be accepted to be imported
DATA_VERSION = 1

export_handler = p_media_mode.create_handler('export')
import_handler = p_media_mode.create_handler('import')


def check_transferring(callback):
  @functools.wraps(callback)
  async def wrapper(event, *args, **kwargs):
    handler = p_media_mode.get_user_handler(event.sender.id).base
    if handler not in {export_handler, import_handler}:
      return
    return await callback(event, *args, **kwargs, transfer_type=handler.base.name)
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


async def send_transfer_stats(
  event,
  initial_msg=None,
  only_marked=True,
  use_transfer=False,
  buttons=[],
  empty_buttons=[]
):
  msg = []
  if initial_msg:
    msg.append(initial_msg)

  handler = p_media_mode.get_user_handler(event.sender.id)
  name = handler.base.name
  stats = await p_stats.get_stats(event.sender_id, only_marked, use_transfer)

  if stats.sub_total:
    msg.append(f'Here\'s a summary of what will be {name}ed:\n{stats.pretty()}\n')
    msg.append(
      'You can add or remove some items with the buttons below, '
      f'use /done to finalize the {name}, or /cancel it.'
    )
  else:
    msg.append(
      f'No items are marked to be {name}ed, use the button below '
      f'to add some or /cancel the {name}.'
    )
    buttons = empty_buttons

  buttons = [utils.inline_pm_button(text, query) for text, query in buttons]
  await event.respond(
    '\n'.join(msg),
    parse_mode='HTML',
    buttons=[buttons] if buttons else None
  )


import p_transfer_export
import p_transfer_import