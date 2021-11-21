from elasticsearch_dsl import Search
from elasticsearch_dsl.query import MultiMatch, Terms, Bool, Term

from query_parser import ParsedQuery

fuzzy_match = lambda fields, values: MultiMatch(
  query=' '.join(values),
  type='most_fields',
  fields=fields,
  operator='and',
  fuzziness='AUTO:4,6',  # disable fuzzy for trigrams
  prefix_length=1
)

fuzzy_ngram = lambda fields, values: fuzzy_match(
  [
    f for field in fields for f in
    [f'{field}^3', f'{field}.prefix_ngram^2', f'{field}.trigram']
  ],
  values
)

field_queries = {
  'tags': lambda f, v: fuzzy_ngram([f, 'title'], v),
  'filename': lambda f, v: fuzzy_ngram([f, 'title'], v),
  'pack_name': lambda f, v: fuzzy_ngram([f], v),
  'ext': lambda f, v: fuzzy_match([f], v),
  'is_animated': lambda f, v: Bool(filter=[Term(is_animated=v[0] == 'yes')]),
  'marked': lambda f, v: Bool(filter=[Term(marked=v[0] == 'yes')]),
  'emoji': lambda f, v: Terms(emoji=v)
}

def gen_search_query(
  owner,
  query: ParsedQuery,
  initial_q=None,
  sort=True,
  includes=[],
):
  q = initial_q if initial_q else Search()

  q = q.filter('term', owner=owner)
  if sort:
    q = q.sort('_score', '-last_used')
  if includes:
    q = q.source(includes=includes)

  search_type = query.get_first('type')
  if search_type == 'document':
    q = q.exclude('term', type='photo')
  else:
    q = q.filter('term', type=search_type)

  for (field, is_neg), values in query.fields.items():
    func = field_queries.get(field)
    if not func:
      continue
    sub_q = func(field, values)
    if is_neg:
      sub_q = ~sub_q
    q = q.query(sub_q)

  return q
