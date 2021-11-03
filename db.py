import asyncio

from elasticsearch import AsyncElasticsearch
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import MultiMatch, Terms, Bool, Term

from query_parser import ParsedQuery


es = AsyncElasticsearch()
INDEX_NAME = 'tagbot'


async def search_user_media(
  owner: int, query: ParsedQuery
):
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
      [f'{field}', f'{field}.prefix_ngram^2', f'{field}.trigram']
    ],
    values
  )
  field_queries = {
    'tags': lambda f, v: fuzzy_ngram([f, 'title'], v),
    'file_name': lambda f, v: fuzzy_ngram([f, 'title'], v),
    'pack_name': lambda f, v: fuzzy_ngram([f], v),
    'ext': lambda f, v: fuzzy_match([f], v),
    'animated': lambda f, v: Bool(filter=[Term(is_animated=v[0] == 'yes')]),
    'emoji': lambda f, v: Terms(emoji=v)
  }

  q = (
    Search()
    .filter('term', owner=owner)
    .filter('term', type=query.get_first('type'))
    .sort('_score', '-last_used')
    .source(includes=['id', 'access_hash', 'tags', 'file_name', 'title'])
  )

  for (field, is_neg), values in query.fields.items():
    func = field_queries.get(field)
    if not func:
      continue
    sub_q = func(field, values)
    if is_neg:
      sub_q = ~sub_q
    q = q.query(sub_q)

  r = await es.search(
    index=INDEX_NAME,
    size=50,
    **q.to_dict()
  )
  return [o['_source'] for o in r['hits']['hits']]


import query_parser

query, _ = query_parser.parse_query('greg')

print(query.fields)

v = asyncio.run(search_user_media(232787997, query))
print(v)