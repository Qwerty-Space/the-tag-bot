import asyncio
import re
from collections import OrderedDict
import logging
import json

from telethon import TelegramClient

from telethon import tl
from telethon.tl.functions.messages import GetEmojiKeywordsRequest

logging.basicConfig(level=logging.INFO)


def dict_filter(f, d):
  accept = OrderedDict()
  reject = OrderedDict()
  for k, v in d.items():
    if f(k, v):
      accept[k] = v
    else:
      reject[k] = v
  return accept, reject


def shortest_strings(l):
  l = l[:]
  for s in l[:]:
    for i, s2 in reversed(tuple(enumerate(l))):
      if s in s2 and s != s2:
        del l[i]
  return l


async def main():
  client = TelegramClient('user', 6, "eb06d4abfb49dc3eeb1aeb98ae0f581e")
  await client.start()

  l: tl.types.EmojiKeywordsDifference = await client(GetEmojiKeywordsRequest('en'))

  keyword_to_emoji = OrderedDict()
  for keyword in l.keywords:
    keyword_to_emoji.setdefault(keyword.keyword, []).extend(keyword.emoticons)

  # reject containing strange chars
  keyword_to_emoji, rejects = dict_filter(
    lambda k, v: not re.search(r'[^a-z\d -]', k),
    keyword_to_emoji
  )

  # who ever created these is retarded
  keyword_to_emoji, rejects = dict_filter(
    lambda k, v: 'family ' not in k,
    keyword_to_emoji
  )

  # length
  keyword_to_emoji, rejects = dict_filter(
    lambda k, v: 2 <= len(k) <= 12,
    keyword_to_emoji
  )

  emoji_to_keyword = OrderedDict()
  for keyword, emojis in keyword_to_emoji.items():
    keyword = re.sub('[- ]', '_', keyword)
    for emoji in emojis:
      emoji_to_keyword.setdefault(emoji, []).append(keyword)

  # turn lists like ['hug', 'hugging', 'tiger', 'tiger_face'] into ['hug', 'tiger']
  for emoji, keywords in emoji_to_keyword.items():
    emoji_to_keyword[emoji] = shortest_strings(keywords)

  with open('emoji_keywords.json', 'w') as f:
    json.dump(emoji_to_keyword, f)


asyncio.run(main())