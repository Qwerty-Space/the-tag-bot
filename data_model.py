from enum import Enum
import struct
from base64 import urlsafe_b64encode, urlsafe_b64decode
import dataclasses
from dataclasses import dataclass, field
import time
from boltons.setutils import IndexedSet

from telethon import tl


class DocumentID:
  "Represents a document id inside elasticsearch"
  PACKED_FMT = '!QQ'

  @staticmethod
  def pack(owner: int, id: int):
    return urlsafe_b64encode(struct.pack('!QQ', owner, id))

  @staticmethod
  def unpack(str_id):
    return struct.unpack(DocumentID.PACKED_FMT, urlsafe_b64decode(str_id))


@dataclass
class InlineResultID:
  PACKED_FMT = '!Q?'

  id: int
  skip_update: bool = False

  @classmethod
  def unpack(cls, str_id):
    args = struct.unpack(
      cls.PACKED_FMT,
      urlsafe_b64decode(str_id)
    )
    return cls(*args)

  def pack(self):
    return urlsafe_b64encode(struct.pack(
      self.PACKED_FMT, *dataclasses.astuple(self)
    ))


class MediaTypes(str, Enum):
  photo = 'photo'
  audio = 'audio'
  voice = 'voice'
  gif = 'gif'
  video = 'video'
  sticker = 'sticker'
  file = 'file'
  # special type that means "not photo"
  document = 'document'

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
  marked: bool = False

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
      if val is TaggedDocumentInvalidValue:
        raise ValueError('Can\'t serialize TaggedDocument with invalid value')
      if isinstance(val, IndexedSet):
        val = list(val)
      d[field.name] = val
    return d
