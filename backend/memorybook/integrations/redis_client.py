from redis import Redis
from flask import Flask


def create_redis_client(app: Flask) -> Redis:
    return Redis.from_url(
        app.config["REDIS_URL"],
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
