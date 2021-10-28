import regex
from emoji import UNICODE_EMOJI_ENGLISH


EMOJI_MODIFIERS = set([
  # Skin tones
  '\U0001f3fb', '\U0001f3fc', '\U0001f3fd', '\U0001f3fe', '\U0001f3ff',
  # Joiner
  '\u200d'
])

# Emoji without any skintones or joins
PLAIN_EMOJI = set(
  c.strip('\ufe0f') for c in UNICODE_EMOJI_ENGLISH
  if not (set(c) & EMOJI_MODIFIERS)
)


def strip_emojis(text):
  """
  Strips all emojis from text, returns cleaned text and each "simple" emoji
  (splits joined emoji, strips skintones, etc)
  P.S: I hate Unicode
  """
  emojis = {}
  def emoji_repl(m):
    grapheme = m.group(0)

    if grapheme in PLAIN_EMOJI:
      emojis[grapheme] = None
      return ''

    has_emoji = False
    for c in grapheme:
      if c in PLAIN_EMOJI:
        emojis[c] = None
        has_emoji = True
    return '' if has_emoji else grapheme

  clean_text = regex.sub(r'\X', emoji_repl, text)
  return clean_text, list(emojis.keys())
