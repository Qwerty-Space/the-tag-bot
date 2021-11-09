import functools

from cachetools import keys


WHITELISTED_IDS = {232787997, 151462131}


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