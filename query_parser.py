import regex
from dataclasses import dataclass
from collections import defaultdict, namedtuple

from emoji import UNICODE_EMOJI_ENGLISH

from utils import MediaTypes

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


@dataclass
class ParseWarning:
  name: str
  data: str
  pos: int = -1


@dataclass
class Field:
  name: str
  aliases: list[str]
  is_short: bool = False
  allow_negation: bool = True


FieldKey = namedtuple('FieldKey', ['name', 'is_neg'])


FIELDS = [
  Field('tags', ['s']),
  Field('file_name', ['fn']),
  Field('ext', ['ext', 'e']),
  Field('pack_name', ['pack', 'p']),
  Field('type', ['type', 't'], is_short=True, allow_negation=False),
  Field('animated', ['animated'], is_short=True)
]

ALIAS_TO_FIELD = {
  alias: field
  for field in FIELDS
  for alias in field.aliases
}


def parse_query(query):
  def set_current_field(field, span, is_neg=False):
    nonlocal current_field, current_field_start, negated_field, field_was_used
    if not field_was_used:
      warnings.append(ParseWarning(
        'Field unused',
        current_field.name,
        current_field_start
      ))
    current_field = field
    current_field_start = span[0]
    negated_field = field.allow_negation and bool(is_neg)
    field_was_used = False

  fields = defaultdict(list)
  warnings = []

  default_field = ALIAS_TO_FIELD.get('s')

  current_field = default_field
  current_field_start = 0
  negated_field = False
  field_was_used = True
  for m in regex.finditer(r'(?P<is_neg>[\!-]*)(?P<token>[^\s:]+)(?P<is_field>:?)|(\n)', query):
    token = m.group('token')
    token_is_neg = bool(m.group('is_neg'))

    # Newlines reset the field
    if m.group(0) == '\n':
      set_current_field(default_field, m.span())
      # prevent warning if field is changed
      field_was_used = True
      continue

    if m.group('is_field'):
      token = token.lower()
      field = ALIAS_TO_FIELD.get(token)
      if not field:
        warnings.append(ParseWarning('Unknown field', token, m.span()[0]))
        continue
      set_current_field(field, m.span(), token_is_neg)
      continue

    token, emojis = strip_emojis(token)
    key = FieldKey('emoji', token_is_neg)
    for emoji in emojis:
      fields[key].append(emoji)

    if not token:
      continue

    is_neg = negated_field ^ token_is_neg
    fields[FieldKey(current_field.name, is_neg)].append(token)
    field_was_used = True
    if current_field.is_short:
      current_field = default_field

  return fields, warnings


fields, warnings = parse_query('t:sticker 💀✌🏿🇺🇸mugi !2️⃣ p:p:bob k-on\n!yui !animated:yes bla:bla !fn:sticker.webp :weed:')

for field, data in fields.items():
  print(field, data)

for warning in warnings:
  print(warning)