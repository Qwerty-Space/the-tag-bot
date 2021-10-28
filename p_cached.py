from dataclasses import dataclass
from collections import defaultdict

from telethon import errors
from telethon.tl.types.messages import StickerSet
from telethon.tl.functions.messages import GetStickerSetRequest
from cachetools import LRUCache, TTLCache

from proxy_globals import client
from utils import acached


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
