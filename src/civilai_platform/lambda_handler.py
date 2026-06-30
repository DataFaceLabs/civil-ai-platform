from mangum import Mangum

from civilai_platform.app import create_app

_handler = Mangum(create_app(), lifespan="off")


def handler(event, context):
    return _handler(event, context)
