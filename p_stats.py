from telethon import events

from proxy_globals import client
from data_model import MediaTypes
from p_help import add_to_help
from p_transfer import current_transfer_type
import db, utils


@client.on(events.NewMessage(pattern=r'/stats$'))
@utils.whitelist
@add_to_help('stats')
async def stats(event: events.NewMessage.Event, show_help):
  """
  Shows counts for media you have saved
  """

  r = await db.count_user_media_by_type(event.sender_id)
  counts = {t['key']: t['doc_count'] for t in r['types']['buckets']}
  if not counts:
    await event.respond('You have not saved any media. Send /start to get started.')
    return

  transfer_type = current_transfer_type(event.sender_id)
  search_pre = 'pending:yes ' if transfer_type else ''
  buttons = []
  has_photos = counts.get(MediaTypes.photo.value)
  if not has_photos or len(counts) > 1:
    buttons.append(utils.inline_pm_button('View Media', f'{search_pre}t:doc'))
  if has_photos:
    buttons.append(utils.inline_pm_button('View Photos', f'{search_pre}t:photo'))

  await event.respond(
    f'Here are the number of items '
    + (f"to be {transfer_type}ed" if transfer_type else "you have saved")
    + ', per type:\n\n'
    f'Total: {r["doc_count"]}\n'
    + '\n'.join(f'{k}: {v}' for k, v in counts.items()),
    buttons=[buttons]
  )