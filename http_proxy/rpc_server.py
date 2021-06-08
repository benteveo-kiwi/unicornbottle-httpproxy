#!/usr/bin/env python3
from typing import Dict, Optional, Any
from http_proxy import rabbitmq, log
import json
import pika

logger = log.getLogger("rpc_server", server=True)

def on_request(ch : Any, method : Any, props : pika.spec.BasicProperties, body : bytes) -> None:

    try:
        request = json.loads(body)
        logger.info("Successfully received message from queue. Now processing.")
    except json.decoder.JSONDecodeError:
        logger.exception("Couldn't decode a JSON object and am having a bad time. Body '%r'." % body)
        raise

    my_props = pika.BasicProperties(correlation_id = props.correlation_id)
    ch.basic_publish(exchange='', routing_key=props.reply_to,
                     properties=my_props,
                     body="""HTTP/1.1 200 OK
Date: Mon, 27 Jul 2009 12:28:53 GMT
Server: Apache/2.2.14 (Win32)
Last-Modified: Wed, 22 Jul 2009 19:15:56 GMT
Content-Length: 2
Content-Type: text/html
Connection: Closed

OK""")

def listen():
    try:
        connection = rabbitmq.new_connection()
        channel = connection.channel()
        channel.queue_declare(queue='rpc_queue')

        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue='rpc_queue', on_message_callback=on_request, auto_ack=True)

        logger.info("[+] HTTP Server consumer started successfully. Listening for messages.")
        channel.start_consuming()
    except:
        logger.exception("Unhandled exception in server init thread.", exc_info=True)
    finally:
        connection.close()

