from flask_jwt_extended import get_jwt
from .models import TokenBlocklist

def is_token_revoked(jwt_header, jwt_payload) -> bool:
    jti = jwt_payload["jti"]
    return TokenBlocklist.query.filter_by(jti=jti).first() is not None
