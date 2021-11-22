import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from telethon import events

from proxy_globals import client, logger, me
from data_model import MediaTypes
import utils


# Expiry after the last interaction
SOFT_EXPIRY_TIME = 60 * 20
# Expiry since creation
HARD_EXPIRY_TIME = 60 * 60


async def async_do_nothing(*args, **kwargs):
  pass


@dataclass
class MediaHandler:
  name: str
  on_event: Callable[[Any], Awaitable[None]] = async_do_nothing
  on_done: Callable[[Any], Awaitable[None]] = async_do_nothing
  on_cancel: Callable[[Any], Awaitable[None]] = async_do_nothing
  on_start: Callable[[Any], Awaitable[None]] = async_do_nothing
  get_start_text: Callable[[Any], str] = lambda q, is_pm: None

  def register(self, callback_name):
    def wrapper(func):
      current_func = getattr(self, callback_name, None)
      default_func = self.__dataclass_fields__.get(callback_name, None)
      if not default_func:
        raise ValueError(f'Callback "{self.name}.{callback_name}" not found!')
      default_func = default_func.default
      if current_func is not default_func:
        raise ValueError(f'Callback "{self.name}.{callback_name}" already registered!')
      setattr(self, callback_name, func)
      return func
    return wrapper


@dataclass
class UserMediaHandler:
  base: MediaHandler
  extra_kwargs: dict = field(default_factory=dict)
  last_query: str = field(init=False, default='')
  expires_at: float = field(init=False, default=None)

  def __post_init__(self):
    self.refresh_expiry()

  def is_expired(self):
    return time.time() >= self.expires_at

  def refresh_expiry(self):
    self.expires_at = time.time() + SOFT_EXPIRY_TIME

  async def event(self, event, m_type, is_delete=False):
    r = await self.base.on_event(
      event=event,
      m_type=m_type,
      is_delete=is_delete,
      **self.extra_kwargs
    )
    if r is Cancel:
      await self.cancel()
      return r

  async def done(self):
    r = await self.base.on_done(**self.extra_kwargs)
    if r is Cancel:
      await self.cancel()
      return r

  # TODO: replace replaced_with_self with a on_reset method (also reset death time)
  async def cancel(self, replaced_with_self=False):
    await self.base.on_cancel(
      replaced_with_self=replaced_with_self,
      **self.extra_kwargs
    )

  async def inline_start(self, event):
    await self.base.on_start(
      event=event,
      query=self.last_query,
      **self.extra_kwargs
    )

  def get_inline_switch_pm(self, is_pm, query_str, parsed_query):
    text = self.base.get_start_text(parsed_query, is_pm)
    if not text:
      return None, None
    self.last_query = query_str
    return text, 'inline'


@dataclass
class UserMediaHandlerHardLimit(UserMediaHandler):
  dies_at: float = field(init=False, default=None)

  def __post_init__(self):
    super().__post_init__()
    self.dies_at = time.time() + HARD_EXPIRY_TIME

  def is_expired(self):
    cur_time = time.time()
    return cur_time >= self.expires_at or cur_time >= self.dies_at


# sentinel for cancelling the operation
Cancel = object()

default_handler = MediaHandler('default')
media_handlers: dict[str, MediaHandler] = {}

user_media_handlers: dict[int, UserMediaHandler] = defaultdict(
  lambda: UserMediaHandler(default_handler)
)
user_next_is_delete: set[int] = set()


def get_user_handler(user_id):
  return user_media_handlers[user_id]


def create_handler(name: str):
  if name in media_handlers:
    raise RuntimeError(f'Handler "{name}" already registered')
  media_handlers[name] = MediaHandler(name)
  return media_handlers[name]


async def set_user_handler(user_id, name, **kwargs):
  base = media_handlers[name]
  handler = user_media_handlers.get(user_id)
  if handler:
    await handler.cancel(replaced_with_self=handler.base is base)
  user_media_handlers[user_id] = UserMediaHandlerHardLimit(base, extra_kwargs=kwargs)


def set_delete_next(user_id, is_delete=True):
  """
  Sets or removes the flag to send the delete flag for the next
  taggable media which was sent via this bot
  """
  if is_delete:
    user_next_is_delete.add(user_id)
  else:
    user_next_is_delete.discard(user_id)


@client.on(events.NewMessage())
@utils.whitelist
async def on_taggable_media(event):
  if not event.file:
    return
  m_type = MediaTypes.from_media(event.file.media)
  if not m_type:
    return

  is_delete = event.sender_id in user_next_is_delete
  user_next_is_delete.discard(event.sender_id)
  is_delete = is_delete and event.message.via_bot_id == me.id

  handler = user_media_handlers[event.sender_id]
  handler.refresh_expiry()
  if await handler.event(event, m_type, is_delete) is Cancel:
    user_media_handlers.pop(event.sender_id, None)


@client.on(events.NewMessage(pattern=r'/done$'))
@utils.whitelist
async def on_done(event: events.NewMessage.Event):
  handler = user_media_handlers[event.sender_id]
  await handler.done()
  user_media_handlers.pop(event.sender_id, None)


@client.on(events.NewMessage(pattern=r'/cancel$'))
@utils.whitelist
async def on_cancel(event: events.NewMessage.Event):
  handler = user_media_handlers[event.sender_id]
  await handler.cancel()
  user_media_handlers.pop(event.sender_id, None)


@client.on(events.NewMessage(pattern=r'/start inline$'))
@utils.whitelist
async def on_start_inline(event: events.NewMessage.Event):
  handler = user_media_handlers[event.sender_id]
  await handler.inline_start(event)


async def expiry_loop():
  while 1:
    user_id, handler = next(
      ((uid, h) for uid, h in user_media_handlers.items() if h.is_expired()),
      (None, None)
    )
    if not handler:
      await asyncio.sleep(10)
      continue

    logger.info(f'Handler {handler.name} for #{user_id} has expired')
    user_media_handlers.pop(user_id, None)
    try:
      await handler.cancel()
      # try to avoid flood waits when sending a lot of cancellation messages
      if handler.name != 'default':
        await asyncio.sleep(0.5)
    except Exception as e:
      logger.exception(f'Unhandled exception on expired handler ({handler.name}) for #{user_id}', e)


asyncio.create_task(expiry_loop())