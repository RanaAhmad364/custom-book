from flask_cors import CORS
from flask_jwt_extended import JWTManager, get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def rate_limit_key() -> str:
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
    except JWTExtendedException:
        identity = None
    return f"user:{identity}" if identity else get_remote_address()


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
limiter = Limiter(key_func=rate_limit_key)
