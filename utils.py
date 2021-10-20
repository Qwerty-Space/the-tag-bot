import re
from enum import Enum
import functools
from dataclasses import dataclass, field

from telethon import tl
from cachetools import keys


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
    for attr in media.attributes:
      if isinstance(attr, tl.types.DocumentAttributeAudio):
        if attr.voice:
          return MediaTypes.voice
        return MediaTypes.audio
      if isinstance(attr, tl.types.DocumentAttributeAnimated):
        return MediaTypes.gif
      if isinstance(attr, tl.types.DocumentAttributeVideo):
        return MediaTypes.video
      if isinstance(attr, tl.types.DocumentAttributeSticker):
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
  return re.sub(r'[^\w:]', '_', tag.lower().replace("'", '')).strip('_')


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
