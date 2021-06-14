import pika
import os

class MissingEnvironmentVariablesException(Exception):
    pass

def new_connection() -> pika.BlockingConnection:
    hostname = os.getenv("RABBIT_HOSTNAME")
    username = os.getenv("RABBIT_USERNAME")
    password = os.getenv("RABBIT_PASSWORD")
    
    if hostname is None or username is None or password is None:
        msg = "Could not connect to rabbit because the required environment variables are missing"
        raise MissingEnvironmentVariablesException(msg)

    credentials = pika.PlainCredentials(username, password)

    connection_parameters = pika.ConnectionParameters(hostname, 5672, '/',
        credentials=credentials)
    connection = pika.BlockingConnection(connection_parameters)

    return connection
