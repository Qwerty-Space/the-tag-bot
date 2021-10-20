import logging
import importlib
import os
from itertools import chain
import mimetypes

from cachetools import LRUCache
from telethon import TelegramClient, events, tl, errors
from telethon.tl.functions.messages import GetStickerSetRequest

import db, utils, proxy_globals

logging.basicConfig(level=logging.INFO)
client = TelegramClient('bot', 6, 'eb06d4abfb49dc3eeb1aeb98ae0f581e')
mimetypes.add_type('application/x-tgsticker', '.tgs')


async def main():
  await db.init()
  await client.start()

  proxy_globals.client = client
  importlib.import_module('p_tagging')
  importlib.import_module('p_search')
  importlib.import_module('p_cached')
  importlib.import_module('p_emoji_tag_suggester')

  await client.run_until_disconnected()


client.loop.run_until_complete(main())