CREATE OR REPLACE FUNCTION concat_tags(TEXT[]) 
RETURNS TEXT IMMUTABLE AS $$
  SELECT array_to_string($1, ' ')
$$ language sql;

CREATE TABLE IF NOT EXISTS media (
  id BIGINT NOT NULL,
  owner BIGINT NOT NULL,
  PRIMARY KEY (id, owner),
  access_hash BIGINT NOT NULL,
  type media_type NOT NULL,
  title TEXT NOT NULL,
  metatags TEXT NOT NULL,
  tags TEXT,
  all_tags TEXT NOT NULL GENERATED ALWAYS AS
    (concat_tags(string_to_array(metatags, ' ') || string_to_array(tags, ' ')))
  STORED,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS index_media_all_tags_on_split ON media USING gin (string_to_array(all_tags, ' '));
ALTER INDEX index_media_all_tags_on_split ALTER COLUMN 1 SET STATISTICS 3000;


CREATE TABLE IF NOT EXISTS tags (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  owner BIGINT NOT NULL DEFAULT 0,
  type media_type,
  count INTEGER NOT NULL DEFAULT 1,
  UNIQUE(name, owner, type)
);
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;
CREATE INDEX IF NOT EXISTS index_tags_on_name_trgm ON tags USING gist (name gist_trgm_ops);


CREATE OR REPLACE FUNCTION split_tags(a TEXT)
RETURNS TABLE (tag TEXT) AS $$
  SELECT UNNEST(string_to_array(a, ' '))
$$
language sql;


-- Calculates the tag count changes between old and new tags
CREATE OR REPLACE FUNCTION _get_tag_diff(
  tg_op_p TEXT,
  old_p ANYELEMENT,
  new_p ANYELEMENT
) RETURNS TABLE (tag TEXT, count INT) AS
$$
BEGIN
  CASE tg_op_p
    WHEN 'INSERT' THEN
      RETURN QUERY
      SELECT *, 1 AS count FROM split_tags(new_p.all_tags);
    WHEN 'DELETE' THEN
      RETURN QUERY
      SELECT *, -1 AS count FROM split_tags(new_p.all_tags);
    WHEN 'UPDATE' THEN
      RETURN QUERY
      SELECT * FROM (
        SELECT COALESCE(atags, btags) AS tag, COALESCE(acount, 0) + COALESCE(bcount, 0) AS diff
        FROM
        (SELECT *, -1 AS acount FROM split_tags(old_p.all_tags) AS t(atags)) a
        FULL JOIN
        (SELECT *, 1 AS bcount FROM split_tags(new_p.all_tags) AS t(btags)) b
        ON atags = btags
      ) r WHERE diff != 0;
  END CASE;
END
$$
LANGUAGE PLPGSQL;

CREATE OR REPLACE FUNCTION func_media_tags() RETURNS trigger AS 
$$
DECLARE
    old_v RECORD;
    new_v RECORD;
BEGIN
  CASE TG_OP
    WHEN 'INSERT' THEN
      old_v = NEW;
      new_v = NEW;
    WHEN 'UPDATE' THEN
      old_v = OLD;
      new_v = NEW;
    WHEN 'DELETE' THEN
      old_v = OLD;
      new_v = OLD;
  END CASE;

  WITH tag_diff AS (
    SELECT * FROM _get_tag_diff(TG_OP, old_v, new_v)
  )
  INSERT INTO tags (name, owner, type, count)
  (
    SELECT tag, new_v.owner AS owner, new_v.type as type, count FROM tag_diff
  )
  ON CONFLICT (name, owner, type) DO UPDATE
  SET count = GREATEST(tags.count + EXCLUDED.count, 0);

  RETURN NULL;
END
$$
LANGUAGE PLPGSQL;

DROP TRIGGER IF EXISTS trigger_media_tags ON media;

CREATE TRIGGER trigger_media_tags
AFTER INSERT OR UPDATE OR DELETE
ON media 
FOR EACH ROW EXECUTE PROCEDURE func_media_tags();


CREATE OR REPLACE FUNCTION func_delete_tag_if_zero_count() RETURNS TRIGGER AS
$$
BEGIN
	DELETE FROM tags WHERE id = NEW.id AND count = 0;
	RETURN NULL;
END
$$
LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_delete_zero_count_tags ON tags;

CREATE TRIGGER trigger_delete_zero_count_tags
AFTER UPDATE ON tags
FOR EACH ROW EXECUTE PROCEDURE func_delete_tag_if_zero_count()
