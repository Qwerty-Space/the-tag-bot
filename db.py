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
  ngram_fields = lambda fs: [
    fmt.format(f) for fmt in ['{}', '{}._2gram', '{}._3gram'] for f in fs
  ]
  ngram_query = lambda fs, vals: MultiMatch(
    query=' '.join(vals),
    type='bool_prefix',
    fields=ngram_fields(fs)
  )
  field_queries = {
    'tags': lambda f, v: ngram_query([f, 'title'], v),
    'file_name': lambda f, v: ngram_query([f, 'title'], v),
    'ext': lambda f, v: ngram_query([f], v),
    'pack_name': lambda f, v: ngram_query([f], v),
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