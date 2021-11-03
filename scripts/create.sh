read -p "This will delete the tagbot index and recreate it, are you sure? " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
  exit 1
fi

curl -X DELETE "localhost:9200/tagbot?pretty"
curl -X PUT "localhost:9200/tagbot?pretty" -H 'Content-Type: application/json' --data "@./settings.json"