import logging
import importlib
import mimetypes

from telethon import TelegramClient

import db, proxy_globals

logging.basicConfig(level=logging.INFO)
client = TelegramClient('bot', 6, 'eb06d4abfb49dc3eeb1aeb98ae0f581e')
mimetypes.add_type('application/x-tgsticker', '.tgs')


async def main():
  await db.init()
  await client.start()

  proxy_globals.client = client
  for module_name in ['p_tagging', 'p_search', 'p_cached', 'p_emoji_tag_suggester']:
    proxy_globals.logger = logging.getLogger(module_name)
    importlib.import_module(module_name)

  await client.run_until_disconnected()


client.loop.run_until_complete(main())