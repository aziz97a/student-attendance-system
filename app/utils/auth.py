from functools import wraps
from flask_jwt_extended import verify_jwt_in_request, get_jwt

def roles_required(*allowed_roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            role = get_jwt().get("role")
            if role not in allowed_roles:
                return {"error": "forbidden"}, 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
