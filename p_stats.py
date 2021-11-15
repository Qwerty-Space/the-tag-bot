from telethon import events

from proxy_globals import client
from p_help import add_to_help
import db, utils


@client.on(events.NewMessage(pattern=r'/stats$'))
@utils.whitelist
@add_to_help('stats')
async def stats(event: events.NewMessage.Event, show_help):
  """
  Shows counts for media you have saved
  """

  r = await db.count_user_media_by_type(event.sender_id)
  await event.respond(
    'Here are the number of items you have saved, per type:\n\n'
    f'Total: {r["doc_count"]}\n'
    + '\n'.join(
      f'{t["key"]}: {t["doc_count"]}' for t in r['types']['buckets']
    )
  )