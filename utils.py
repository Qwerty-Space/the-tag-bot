import re
from enum import Enum
from dataclasses import dataclass, field

from telethon import tl


class MediaTypes(str, Enum):
  photo = 'photo'
  audio = 'audio'
  gif = 'gif'
  video = 'video'
  sticker = 'sticker'
  document = 'document'


def get_media_type(media):
  if isinstance(media, tl.types.Photo):
    return MediaTypes.photo
  if isinstance(media, tl.types.Document):
    for attr in media.attributes:
      if isinstance(attr, tl.types.DocumentAttributeAudio):
        return MediaTypes.audio
      if isinstance(attr, tl.types.DocumentAttributeAnimated):
        return MediaTypes.gif
      if isinstance(attr, tl.types.DocumentAttributeVideo):
        return MediaTypes.video
      if isinstance(attr, tl.types.DocumentAttributeSticker):
        return MediaTypes.sticker
  return MediaTypes.document


@dataclass
class ParsedTags:
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
  return parsed