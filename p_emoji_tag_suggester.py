import json
from collections import OrderedDict

from telethon import events

from proxy_globals import client
import utils
import p_cached


with open('data/emoji_keywords.json') as f:
  emoji_to_keyword = json.load(f)


def get_emojis_keywords(emojis):
  ret = OrderedDict()
  for emoji in emojis:
    keywords = emoji_to_keyword.get(emoji, [])
    if keywords:
      ret[emoji] = ' '.join(keywords)
  return ret


@client.on(events.NewMessage(pattern=r'^/emoji_tags (.+)'))
async def on_emoji_tags(event):
  emojis = event.pattern_match.group(1)
  keywords = get_emojis_keywords(emojis)
  if not keywords:
    return await event.reply('No keywords found.')
  await event.reply(
    '\n'.join(f'{k} {utils.html_format_tags(v)}' for k, v in keywords.items()),
    parse_mode='HTML'
  )


@client.on(events.NewMessage(pattern=r'^/emoji_tags$'))
async def on_emoji_tags_from_sticker(event):
  m = event.message
  if not m.is_reply:
    return await event.reply('Reply to a sticker to use this command')
  reply = await event.get_reply_message()
  sticker_set = reply.file.sticker_set
  if not sticker_set:
    return await event.reply('This command only works on stickers from a pack')

  sticker_set = await p_cached.get_sticker_pack(sticker_set)
  emojis = reply.file.emoji
  if sticker_set:
    emojis = sticker_set.sticker_emojis.get(reply.file.media.id, emojis)
  keywords = get_emojis_keywords(emojis)

  if not keywords:
    return await event.reply("I don't have any keywords for that emoji")

  await event.reply(
    '\n'.join(f'{k} {utils.html_format_tags(v)}' for k, v in keywords.items()),
    parse_mode='HTML'
  )