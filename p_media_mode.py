import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from telethon import events

from proxy_globals import client, logger, me
from data_model import MediaTypes
import utils


@dataclass
class MediaHandler:
  EXPIRY_TIME = 60 * 10

  name: str
  on_event: Callable[[events.NewMessage.Event], Awaitable[None]]
  on_done: Callable[[Any], Awaitable[None]]
  on_cancel: Callable[[Any], Awaitable[None]]
  extra_kwargs: dict = field(default_factory=dict)
  expires_at: float = None

  def __post_init__(self):
    if not self.expires_at:
      self.refresh_expiry()

  def is_expired(self):
    return time.time() >= self.expires_at

  def refresh_expiry(self):
    self.expires_at = time.time() + MediaHandler.EXPIRY_TIME

  async def event(self, event, m_type):
    r = await self.on_event(event, m_type, **self.extra_kwargs)
    if r is Cancel:
      await self.cancel()
      return r

  async def done(self):
    r = await self.on_done(**self.extra_kwargs)
    if r is Cancel:
      await self.cancel()
      return r

  async def cancel(self, replaced_with_self=False):
    await self.on_cancel(
      replaced_with_self=replaced_with_self,
      **self.extra_kwargs
    )


# sentinel for cancelling the operation
Cancel = object()
user_media_handlers: dict[int, MediaHandler] = {}
user_ignore_next_via_self: set[int] = set()


async def set_user_handler(name, user_id, *args, **kwargs):
  handler = user_media_handlers.get(user_id)
  if handler:
    await handler.cancel(replaced_with_self=handler.name == name)
  user_media_handlers[user_id] = MediaHandler(*args, name=name, **kwargs)


def set_ignore_next(user_id, should_ignore=True):
  """Sets or removes the flag to ignore the next thing sent via this bot"""
  if should_ignore:
    user_ignore_next_via_self.add(user_id)
  else:
    user_ignore_next_via_self.discard(user_id)


def unset_ignore_next(user_id):
  """Removes the flag to ignore the next thing sent via this bot"""
  user_ignore_next_via_self.discard(user_id)


@client.on(events.NewMessage())
@utils.whitelist
async def on_taggable_media(event):
  if not event.file:
    return
  m_type = MediaTypes.from_media(event.file.media)
  if not m_type:
    return

  should_ignore = event.sender_id in user_ignore_next_via_self
  if event.message.via_bot_id == me.id:
    unset_ignore_next(event.sender_id)
    if should_ignore:
      return

  handler = user_media_handlers.get(event.sender_id)
  if not handler or handler.is_expired():
    return
  handler.refresh_expiry()
  if await handler.event(event, m_type) is Cancel:
    user_media_handlers.pop(event.sender_id, None)


@client.on(events.NewMessage(pattern=r'/done$'))
@utils.whitelist
async def on_done(event: events.NewMessage.Event):
  handler = user_media_handlers.get(event.sender_id)
  if handler:
    await handler.done()
    user_media_handlers.pop(event.sender_id, None)


@client.on(events.NewMessage(pattern=r'/cancel$'))
@utils.whitelist
async def on_cancel(event: events.NewMessage.Event):
  handler = user_media_handlers.get(event.sender_id)
  if handler:
    await handler.cancel()
    user_media_handlers.pop(event.sender_id, None)


async def expiry_loop():
  while 1:
    await asyncio.sleep(10)

    user_id, handler = next(
      ((uid, h) for uid, h in user_media_handlers.items() if h.is_expired()),
      (None, None)
    )
    if not handler:
      continue

    logger.info(f'Handler {handler.name} for #{user_id} has expired')
    user_media_handlers.pop(user_id, None)
    try:
      await handler.cancel()
      # try to avoid flood waits when sending a lot of cancellation messages
      await asyncio.sleep(0.5)
    except Exception as e:
      logger.exception(f'Unhandled exception on expired handler ({handler.name}) for #{user_id}', e)


asyncio.create_task(expiry_loop())