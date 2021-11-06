from enum import Enum
import dataclasses
from dataclasses import dataclass, field
import time
from boltons.setutils import IndexedSet

from telethon import tl



class MediaTypes(str, Enum):
  photo = 'photo'
  audio = 'audio'
  voice = 'voice'
  gif = 'gif'
  video = 'video'
  sticker = 'sticker'
  file = 'file'

  @staticmethod
  def from_media(media):
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

MediaTypeList = [e.value for e in MediaTypes]

TaggedDocumentInvalidValue = object()

@dataclass
class TaggedDocument:
  owner: int = TaggedDocumentInvalidValue
  id: int = TaggedDocumentInvalidValue
  access_hash: int = TaggedDocumentInvalidValue
  type: MediaTypes = TaggedDocumentInvalidValue
  ext: str = ''
  is_animated: bool = False
  pack_name: str = ''
  pack_link: str = ''
  filename: str = ''
  title: str = ''
  created: int = 0
  last_used: int = 0
  tags: IndexedSet[str] = field(default_factory=IndexedSet)
  emoji: IndexedSet[str] = field(default_factory=IndexedSet)

  def __post_init__(self):
    t = round(time.time())
    if not self.created:
      self.created = t
    if not self.last_used:
      self.last_used = t
    if isinstance(self.type, str):
      self.type = MediaTypes(self.type)
    if isinstance(self.tags, list):
      self.tags = IndexedSet(self.tags)
    if isinstance(self.emoji, list):
      self.emoji = IndexedSet(self.emoji)

  def merge(self, **changes):
    return dataclasses.replace(self, **changes)

  def to_dict(self):
    d = {}
    for field in dataclasses.fields(self):
      val = getattr(self, field.name)
      if val == TaggedDocumentInvalidValue:
        raise ValueError('Can\'t serialize TaggedDocument with invalid value')
      if isinstance(val, IndexedSet):
        val = list(val)
      d[field.name] = val
    return d
