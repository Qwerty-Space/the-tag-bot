from dataclasses import dataclass, field

from telethon import events

from constants import INDEX
from proxy_globals import client
from data_model import MediaTypes
from p_help import add_to_help
from p_transfer import current_transfer_type
import db, utils


@dataclass
class Stats:
  total: int
  counts: dict[str, int]
  sub_total: int = None
  has_photos: bool = field(init=False, default=None)
  has_documents: bool = field(init=False, default=None)

  def __post_init__(self):
    self.has_photos = bool(self.counts.get('photo'))
    self.has_documents = (not self.has_photos and self.counts) or len(self.counts) > 1

  def pretty(self):
    first_line = f'Total: {self.total}'
    if self.sub_total:
      first_line = f'Total: {self.sub_total} out of your {self.total} saved items'
    count_lines = [f'{k}: {v}' for k, v in self.counts.items()]
    return '\n'.join([first_line] + count_lines)


async def get_stats(user_id: int, only_marked=False, is_transfer=False):
  r = await db.count_user_media_by_type(user_id, only_marked, is_transfer=is_transfer)
  sub_total = None
  total = r["doc_count"]
  if only_marked:
    sub_total = r["marked"]["doc_count"]
    r = r['marked']
  counts = {t['key']: t['doc_count'] for t in r['types']['buckets']}
  return Stats(total, counts, sub_total)


@client.on(events.NewMessage(pattern=r'/stats$'))
@utils.whitelist
@add_to_help('stats')
async def stats(event: events.NewMessage.Event, show_help):
  """
  Shows counts for media you have saved
  """

  stats = await get_stats(event.sender_id)

  if not stats.total:
    await event.respond('You have not saved any media. Send /start to get started.')
    return

  await event.respond(
    f'Here\'s a summary of what you have saved:\n{stats.pretty()}',
    parse_mode='HTML'
  )