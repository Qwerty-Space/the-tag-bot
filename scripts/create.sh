curl -X PUT "localhost:9200/tagbot"
curl -X PUT "localhost:9200/tagbot/_mapping?pretty" -H 'Content-Type: application/json' --data "@./mapping.json"