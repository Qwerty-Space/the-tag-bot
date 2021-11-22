import functools

from cachetools import keys
from telethon.tl.custom.button import Button

from data_model import MediaTypes


WHITELISTED_IDS = {232787997, 151462131}


def inline_pm_button(text, query=''):
  return Button.switch_inline(text, f'{query} ', same_peer=True)


def html_format_tags(tags):
  if isinstance(tags, str):
    tags = tags.split(' ')
  return '\u2800'.join(f'<code>{tag}</code>' for tag in tags)


def prefix_matches(needle: str, haystack: list[str]):
  return [item for item in haystack if item.startswith(needle)]


# Abridged version of https://github.com/hephex/asyncache
def acached(cache, key=keys.hashkey):
  def decorator(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
      k = key(*args, **kwargs)
      try:
        return cache[k]
      except KeyError:
        pass  # key not found
      val = await func(*args, **kwargs)
      try:
        cache[k] = val
      except ValueError:
        pass  # val too large
      return val
    return wrapper
  return decorator


def whitelist(handler):
  @functools.wraps(handler)
  async def wrapper(event, *args, **kwargs):
    if event.sender_id not in WHITELISTED_IDS:
      return
    return await handler(event, *args, **kwargs)
  return wrapper


def extract_taggable_media(handler):
  @functools.wraps(handler)
  async def wrapper(event, *args, **kwargs):
    reply = await event.get_reply_message()
    m_type = MediaTypes.from_media(reply.file.media) if reply and reply.file else None
    ret = await handler(event, reply=reply, m_type=m_type, *args, **kwargs)
    if isinstance(ret, str):
      await event.respond(ret)
    return ret
  return wrapper
