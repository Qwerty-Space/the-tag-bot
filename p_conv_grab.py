# Wraps Conversation._on_new_message and sets a custom attribute if a conversation
# could handle the update

from proxy_globals import client

import functools

from telethon import events
from telethon.tl.custom import Conversation


HANDLED_BY_CONV_ATTR = '_handled_by_conv'


@client.on(events.NewMessage)
async def on_msg(event):
  if getattr(event.original_update, HANDLED_BY_CONV_ATTR, False):
    raise events.StopPropagation


def attr_setter_wrapper(func):
  @functools.wraps(func)
  def wrapper(self, response):
    func(self, response)
    response_msg = response.message
    if response_msg.chat_id != self.chat_id or response_msg.out:
      return
    setattr(response.original_update, HANDLED_BY_CONV_ATTR, True)
  return wrapper


Conversation._on_new_message = attr_setter_wrapper(Conversation._on_new_message)