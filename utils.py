import re
from enum import Enum
import functools
from dataclasses import dataclass, field

from telethon import tl
from cachetools import keys


WHITELISTED_IDS = {232787997}


class MediaTypes(str, Enum):
  photo = 'photo'
  audio = 'audio'
  voice = 'voice'
  gif = 'gif'
  video = 'video'
  sticker = 'sticker'
  file = 'file'


def get_media_type(media):
  if isinstance(media, tl.types.Photo):
    return MediaTypes.photo

  if isinstance(media, tl.types.Document):
    attr_types = {type(attr): attr for attr in media.attributes}

    if tl.types.DocumentAttributeAudio in attr_types:
      if attr_types[tl.types.DocumentAttributeAudio].voice:
        return MediaTypes.voice
      return MediaTypes.audio

    if tl.types.DocumentAttributeAnimated in attr_types:
      return MediaTypes.gif

    if tl.types.DocumentAttributeVideo in attr_types:
      return MediaTypes.video

    if tl.types.DocumentAttributeSticker in attr_types:
      return MediaTypes.sticker

    return MediaTypes.file


@dataclass
class ParsedTags:
  type: str = ''
  pos: set[str] = field(default_factory=set)
  neg: set[str] = field(default_factory=set)

  def is_empty(self):
    return not self.pos and not self.neg


def sanitise_tag(tag):
  tag = re.sub(r'[^\w:]', '_', tag.lower().replace("'", '')).strip('_')
  prefix_match = re.match(r'(\w+?):(.+)$', tag)
  if prefix_match:
    tag = f'{prefix_match[1]}:{prefix_match[2].replace(":", "_").strip("_")}'
  tag = re.sub(r'_{2,}', '_', tag)
  return tag


def parse_tags(tags):
  tags = tags.split(' ')
  parsed = ParsedTags()

  for tag in tags:
    m = re.match(r'(\W)?(.*)$', tag)
    if not m[2]:
      continue
    clean_tag = sanitise_tag(m[2])
    if not clean_tag:
      continue
    if m[1] in {'!', '-'}:
      parsed.neg.add(clean_tag)
      continue
    parsed.pos.add(clean_tag)
  parsed.pos, parsed.neg = parsed.pos - parsed.neg, parsed.neg - parsed.pos

  type_re = re.compile(r't:(\w*)$')

  type_tag = next(filter(lambda x: x, (type_re.match(t) for t in parsed.pos)), None)
  parsed.type = type_tag.group(1) if type_tag else MediaTypes.sticker.value
  parsed.neg = set(t for t in parsed.neg if not type_re.match(t))
  parsed.pos = set(t for t in parsed.pos if not type_re.match(t))

  return parsed


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