#!/usr/bin/env python
from typing import Dict, Optional, Any
import json
import pika

credentials = pika.PlainCredentials('httpproxy', 'SHJfakkjawkjhfkawjaw')
connection = pika.BlockingConnection(
    pika.ConnectionParameters('localhost', 5672, '/', credentials=credentials))

channel = connection.channel()

channel.queue_declare(queue='rpc_queue')

def on_request(ch : Any, method : Any, props : pika.spec.BasicProperties, body : bytes) -> None:

    ch.basic_ack(delivery_tag=method.delivery_tag)

    try:
        request = json.loads(body)
        print("[+] Got req %r" % body)
    except json.decoder.JSONDecodeError:
        print("[-] Couldn't decode a JSON object and am having a bad time. Body '%r'" % body)

    my_props = pika.BasicProperties(correlation_id = props.correlation_id)
    ch.basic_publish(exchange='', routing_key=props.reply_to,
                     properties=my_props,
                     body=str("""HTTP/1.1 200 OK
Date: Mon, 27 Jul 2009 12:28:53 GMT
Server: Apache/2.2.14 (Win32)
Last-Modified: Wed, 22 Jul 2009 19:15:56 GMT
Content-Length: 3
Content-Type: text/html
Connection: Closed

OK"""))


channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='rpc_queue', on_message_callback=on_request)

print(" [x] Awaiting RPC requests")
channel.start_consuming()
