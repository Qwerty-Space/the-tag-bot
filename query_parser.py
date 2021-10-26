from dataclasses import dataclass
from collections import defaultdict

from lark import Lark, Transformer, v_args
import emoji

from utils import MediaTypes


@dataclass
class Field:
  name: str
  content: list[str]
  is_neg: bool


@dataclass
class FieldError:
  name: str
  data: str
  column: int = -1
  end_column: int = -1


class QueryFlattener(Transformer):
  DEFAULT_FIELD = 'tags'

  def WORD(self, token):
    return token.value

  def _parse_word(self, t, is_neg):
    return Field(self.DEFAULT_FIELD, t, is_neg)

  word = lambda self, t: self._parse_word(t, False)
  word_neg = lambda self, t: self._parse_word(t, True)

  @v_args(meta=True)
  def error_unknown_field(self, t, meta):
    return FieldError('Unknown field', t[0], meta.column, meta.end_column)

  @v_args(meta=True)
  def error_no_value(self, t, meta):
    return FieldError('No value found', t[0].data, meta.column, meta.end_column)

  @v_args(meta=True)
  def error_stray_colon(self, t, meta):
    return FieldError('Stray colon', '', meta.column, meta.end_column)

  def _parse_field(self, t, is_neg):
    if isinstance(t[0], FieldError):
      return t[0]
    field_name = t[0].data
    return Field(field_name, t[1:], is_neg)

  field = lambda self, t: self._parse_field(t, False)
  field_neg = lambda self, t: self._parse_field(t, True)

  def query(self, t):
    return t


with open('query.lark') as f:
  query_parser = Lark(
    f.read(),
    start='query',
    parser='lalr',
    propagate_positions=True
  )

query_flattener = QueryFlattener()


def parse_query(query):
  fields = query_flattener.transform(query_parser.parse(query))
  positive_fields = defaultdict(list)
  negative_fields = defaultdict(list)
  errors = defaultdict(list)

  for field in fields:
    if isinstance(field, FieldError):
      errors[field.name].append(field)
      continue
    d = negative_fields if field.is_neg else positive_fields
    name = field.name
    # TODO: extract emoji
    d[name].extend(field.content)

  # TODO: remove negative/multiple types

  return positive_fields, negative_fields, errors

r = parse_query('t:sticker 💀 mugi p:p:bob k-on\n!yui !animated:yes bla:bla !fn:sticker.webp :partial :')
print(r)
