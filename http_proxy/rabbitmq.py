import pika
import os

def new_connection() -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(os.getenv("RABBIT_USERNAME"),
        os.getenv("RABBIT_PASSWORD"))

    connection_parameters = pika.ConnectionParameters(os.getenv("RABBIT_HOSTNAME"), 5672, '/',
        credentials=credentials)
    connection = pika.BlockingConnection(connection_parameters)

    return connection
