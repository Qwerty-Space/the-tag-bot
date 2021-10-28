from dataclasses import dataclass
from collections import defaultdict

from telethon import errors
from telethon.tl.types.messages import StickerSet
from telethon.tl.functions.messages import GetStickerSetRequest
from cachetools import LRUCache, TTLCache

from proxy_globals import client, logger
from utils import acached
from emoji_extractor import strip_emojis


# StickerSet without unused data
@dataclass
class CachedStickerSet:
  sticker_emojis: defaultdict[int, list[str]]
  title: str
  short_name: str

  def __init__(self, sticker_set: StickerSet):
    self.sticker_emojis = defaultdict(list)
    for pack in sticker_set.packs:
      for doc_id in pack.documents:
        self.sticker_emojis[doc_id].append(pack.emoticon)

    for doc_id, emojis in self.sticker_emojis.items():
      plain_emojis = []
      for emoji in emojis:
        _, extracted = strip_emojis(emoji)
        if not extracted:
          logger.warning(f'No emoji extracted from "{emoji.encode("unicode-escape")}"')
        plain_emojis.extend(extracted)
      self.sticker_emojis[doc_id] = plain_emojis

    self.title = sticker_set.set.title
    self.short_name = sticker_set.set.short_name


@acached(TTLCache(1024, ttl=60 * 20), key=lambda ss: getattr(ss, 'id', 0))
async def get_sticker_pack(sticker_set):
  if not sticker_set:
    return
  try:
    return CachedStickerSet(await client(GetStickerSetRequest(sticker_set)))
  except errors.StickersetInvalidError:
    return
