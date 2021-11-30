import functools

from telethon import events

from proxy_globals import client
import utils
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


async def send_transfer_stats(event, initial_msg=None, only_marked=True, is_transfer=False):
  msg = []
  if initial_msg:
    msg.append(initial_msg)

  handler = p_media_mode.get_user_handler(event.sender.id)
  name = handler.base.name
  query_suf = 'pending:y ' if is_transfer else ''
  stats = await p_stats.get_stats(event.sender_id, only_marked, is_transfer)
  buttons = [utils.inline_pm_button('Add', f'{query_suf}marked:n')]

  if stats.sub_total:
    msg.append(f'Here\'s a summary of what will be {name}ed:\n{stats.pretty()}\n')
    msg.append(
      'You can add or remove some items with the buttons below, '
      f'use /done to finalize the {name}, or /cancel it.'
    )
    buttons.append(utils.inline_pm_button('Remove', f'{query_suf}marked:y delete:y'))
  else:
    msg.append(
      f'No items are marked to be {name}ed, use the button below '
      f'to add some or /cancel the {name}.'
    )

  await event.respond(
    '\n'.join(msg),
    parse_mode='HTML',
    buttons=[buttons]
  )


import p_transfer_export
import p_transfer_import