import re
from dataclasses import dataclass
from collections import defaultdict

from utils import MediaTypeList, prefix_matches
from emoji_extractor import strip_emojis


@dataclass
class ParseWarning:
  name: str
  data: str = ''
  pos: int = -1


@dataclass
class Field:
  name: str
  aliases: list[str]
  allowed_values: list[str] = None
  default: str = None


@dataclass(frozen=True)
class FieldKey:
  name: str
  is_neg: bool = False


FIELDS = [
  Field('tags', ['s']),
  Field('file_name', ['fn']),
  Field('ext', ['ext', 'e']),
  Field('pack_name', ['pack', 'p']),
  Field('type', ['type', 't'], allowed_values=MediaTypeList, default='sticker'),
  Field('animated', ['animated'], allowed_values=['yes', 'no'])
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
      add_warning('Field empty', current_field.name, current_field_start)
    current_field = field
    current_field_start = span[0]
    negated_field = not field.allowed_values and is_neg
    field_was_used = False

  fields = defaultdict(list)
  warnings = []
  add_warning = lambda *a, **kw: warnings.append(ParseWarning(*a, **kw))

  default_field = ALIAS_TO_FIELD.get('s')

  current_field = default_field
  current_field_start = 0
  negated_field = False
  field_was_used = True
  for m in re.finditer(r'(?P<is_neg>[\!-]*)(?P<token>[^\s:]+)(?P<is_field>:?)|(\n)', query):
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
        add_warning('Unknown field', token, m.span()[0])
        continue
      set_current_field(field, m.span(), token_is_neg)
      continue

    token, emojis = strip_emojis(token)
    key = FieldKey('emoji', token_is_neg)
    for emoji in emojis:
      fields[key].append(emoji)

    if not token:
      continue

    # only allow negation if the field can have any value
    is_neg = not current_field.allowed_values and (negated_field ^ token_is_neg)
    fields[FieldKey(current_field.name, is_neg)].append(token)
    field_was_used = True
    if current_field.allowed_values:
      set_current_field(default_field, m.span())

  # Use first valid (prefix match) value for fields with .allowed_values
  # if no valid value, use .default if present otherwise delete the field
  for field in FIELDS:
    if not field.allowed_values:
      continue
    key = FieldKey(field.name)
    if key not in fields:
      continue

    if len(fields[key]) > 1:
      add_warning(f'{field.name} specified more than once, using first valid')

    value = None
    for s in fields[key]:
      matches = prefix_matches(s, field.allowed_values)
      if not matches:
        add_warning(f'Value "{s}" for {field.name} is invalid')
        continue
      if len(matches) > 1:
        add_warning(f'Value "{s}" for {field.name} is ambiguous ({",".join(matches)})')
        continue
      if value:
        continue
      value = matches[0]

    if value or field.default:
      fields[key] = [value or field.default]
    else:
      del fields[key]

  return fields, warnings


fields, warnings = parse_query('t:sticker 💀✌🏿🇺🇸mugi !2️⃣ p:p:bob k-on\n!yui !animated:yes bla:bla !fn:sticker.webp :weed:')

for field, data in fields.items():
  print(field, data)

for warning in warnings:
  print(warning)