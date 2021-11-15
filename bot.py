import logging
import importlib
import mimetypes

from telethon import TelegramClient

import proxy_globals

logging.basicConfig(level=logging.INFO)
client = TelegramClient('bot', 6, 'eb06d4abfb49dc3eeb1aeb98ae0f581e')
mimetypes.add_type('application/x-tgsticker', '.tgs')


async def main():
  await client.start()

  proxy_globals.client = client
  load_callbacks = []
  for module_name in ['p_cached', 'p_help', 'p_tagging', 'p_search', 'p_stats']:
    proxy_globals.logger = logging.getLogger(module_name)
    module = importlib.import_module(module_name)
    init = getattr(module, 'on_done_loading', None)
    if init:
      load_callbacks.append(init)

  for cb in load_callbacks:
    await cb()

  await client.run_until_disconnected()


client.loop.run_until_complete(main())