class ConnectionManager:
    def __init__(self, redis_client):
        self.redis = redis_client
