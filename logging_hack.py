# inherits some classes from elasticsearch to make logging output the user id who
# caused the request
# it's a "hack" because it might break between minor versions of the library

# currently logging comes from the Connection abstract class
# AsyncElasticsearch uses AsyncTransport
# AsyncTransport initializes connections using the class from the connection_class parameter
# the default connection class is AIOHttpConnection, which is a Connection

import logging
from functools import partial
import re
from urllib.parse import unquote

from elasticsearch import AsyncElasticsearch as es, AsyncTransport, AIOHttpConnection

from data_model import DocumentID


logger = logging.getLogger('es_req')


def extract_user_id(path, body):
  doc_id = re.search(r'/([a-zA-Z\d\-_]{22}==)', unquote(path))
  if doc_id:
    doc_id = DocumentID.unpack(doc_id[1])
    return doc_id.owner
  if not body:
    return
  print(body)
  # TODO: maybe don't use regex to search json
  user_id = re.search(r'"owner":(\d+)', body)
  if user_id:
    return user_id[1]
  return


class AIOHttpConnectionLogUID(AIOHttpConnection):
  def log_request_success(
    self, method, full_url, path, body, status_code, response, duration
  ):
    #TODO: do we care about the response?
    if body is not None:
      try:
        body = body.decode("utf-8", "ignore")
      except AttributeError:
        pass

    user_id = extract_user_id(path, body)
    logger.info(
      f'{method} {path} [u:{user_id or "NA"} s:{status_code} t:{duration:.3f}s]'
    )

  def log_request_fail(
    self, method, full_url, path, body, duration,
    status_code=None, response=None, exception=None,
  ):
    if method == "HEAD" and status_code == 404:
      return

    if body:
      try:
        body = body.decode("utf-8", "ignore")
      except AttributeError:
        pass

    user_id = extract_user_id(path, body)
    logger.warning(
      f'{method} {path} [u:{user_id or "NA"} s:{status_code or "NA"} t:{duration:.3f}s]',
      exc_info=exception is not None,
    )


class AsyncTransportLogUID(AsyncTransport):
  DEFAULT_CONNECTION_CLASS = AIOHttpConnectionLogUID

  def __init__(self, *args, **kwargs):
    super().__init__(*args, connection_class=AIOHttpConnectionLogUID, **kwargs)

AsyncElasticsearch = partial(es, transport_class=AsyncTransportLogUID)
