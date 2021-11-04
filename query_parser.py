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
class _ParseField:
  name: str
  aliases: list[str]
  allowed_values: list[str] = None
  default: str = None


class ParsedQuery:
  def __init__(self):
    self.fields = defaultdict(list)

  def append(self, name, value, is_neg=False):
    self.fields[name, is_neg].append(value)

  def has(self, name, is_neg=False):
    return (name, is_neg) in self.fields

  def get(self, name, is_neg=False):
    return self.fields[name, is_neg]

  def get_first(self, name, is_neg=False):
    return self.fields[name, is_neg][0]

  def replace(self, name, value, is_neg=False):
    self.fields[name, is_neg] = value

  def remove(self, name, is_neg=False):
    del self.fields[name, is_neg]


FIELDS = [
  _ParseField('tags', ['s']),
  _ParseField('file_name', ['fn']),
  _ParseField('ext', ['ext', 'e']),
  _ParseField('pack_name', ['pack', 'p']),
  _ParseField('type', ['type', 't'], allowed_values=MediaTypeList, default='sticker'),
  _ParseField('animated', ['animated'], allowed_values=['yes', 'no'])
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

  parsed = ParsedQuery()
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
    for emoji in emojis:
      parsed.append('emoji', emoji, is_neg=token_is_neg)

    if not token:
      continue

    # only allow negation if the field can have any value
    is_neg = not current_field.allowed_values and (negated_field ^ token_is_neg)
    parsed.append(current_field.name, token, is_neg=is_neg)
    field_was_used = True
    if current_field.allowed_values:
      set_current_field(default_field, m.span())

  # Use first valid (prefix match) value for fields with .allowed_values
  # if no valid value, use .default if present otherwise delete the field
  for field in FIELDS:
    if not field.allowed_values:
      continue
    if not parsed.has(field.name):
      if field.default:
        parsed.replace(field.name, [field.default])
      continue
    values = parsed.get(field.name)

    if len(values) > 1:
      add_warning(f'{field.name} specified more than once, using first valid')

    value = None
    for s in values:
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
      parsed.replace(field.name, [value or field.default])
    else:
      parsed.remove(field.name)

  return parsed, warnings
