import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from telethon import events

from proxy_globals import client, logger
from data_model import MediaTypes
import utils


@dataclass
class MediaHandler:
  EXPIRY_TIME = 60 * 10

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


# sentinel for cancelling the operation
Cancel = object()
user_media_handlers: dict[int, MediaHandler] = {}


async def set_user_handler(user_id, *args, **kwargs):
  handler = user_media_handlers.get(user_id)
  if handler:
    await handler.on_cancel(**handler.extra_kwargs)
  user_media_handlers[user_id] = MediaHandler(*args, **kwargs)


@client.on(events.NewMessage())
@utils.whitelist
async def on_taggable_media(event):
  if not event.file:
    return
  m_type = MediaTypes.from_media(event.file.media)
  if not m_type:
    return
  handler = user_media_handlers.get(event.sender_id)
  if not handler or handler.is_expired():
    return
  handler.refresh_expiry()
  r = await handler.on_event(event, m_type, **handler.extra_kwargs)
  if id(r) == id(Cancel):
    await handler.on_cancel(**handler.extra_kwargs)
    del user_media_handlers[event.sender_id]


@client.on(events.NewMessage(pattern=r'/done$'))
@utils.whitelist
async def on_done(event: events.NewMessage.Event):
  handler = user_media_handlers.get(event.sender_id)
  if handler:
    await handler.on_done(**handler.extra_kwargs)
    del user_media_handlers[event.sender_id]


@client.on(events.NewMessage(pattern=r'/cancel$'))
@utils.whitelist
async def on_cancel(event: events.NewMessage.Event):
  handler = user_media_handlers.get(event.sender_id)
  if handler:
    await handler.on_cancel(**handler.extra_kwargs)
    del user_media_handlers[event.sender_id]


async def expiry_loop():
  while 1:
    await asyncio.sleep(10)

    user_id, handler = next(
      ((uid, h) for uid, h in user_media_handlers.items() if h.is_expired()),
      (None, None)
    )
    if not handler:
      continue

    logger.info(f'Handler {handler.on_event} for #{user_id} has expired')
    del user_media_handlers[user_id]
    try:
      await handler.on_cancel(**handler.extra_kwargs)
      # try to avoid flood waits when sending a lot of cancellation messages
      await asyncio.sleep(0.5)
    except Exception as e:
      logger.exception(f'Unhandled exception on expired handler ({handler.on_event}) for #{user_id}', e)


asyncio.create_task(expiry_loop())