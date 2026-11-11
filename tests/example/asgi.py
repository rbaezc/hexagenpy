"""ASGI entry point of the example app: granian --interface asgi tests.example.asgi:http"""

from hexagenpy.transports.http import HttpApp
from tests.example.app import create_app

http = HttpApp(create_app(), title="Example shop")
