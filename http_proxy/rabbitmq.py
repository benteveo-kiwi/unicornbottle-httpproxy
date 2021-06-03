import pika

def new_connection():
    credentials = pika.PlainCredentials('httpproxy', 'SHJfakkjawkjhfkawjaw')
    connection = pika.BlockingConnection(
        pika.ConnectionParameters('localhost', 5672, '/', credentials=credentials))

    return connection
