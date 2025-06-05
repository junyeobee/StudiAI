"""
Custom exceptions for the application
"""

class NotionAPIError(Exception):
    def __init__(self, detail: str):
        super().__init__(f"Notion API Error: {detail}")

class DatabaseError(Exception):
    def __init__(self, detail: str):
        super().__init__(f"Database Error: {detail}")

class WebhookError(Exception):
    def __init__(self, detail: str):
        super().__init__(f"Webhook Error: {detail}")

class NotFoundError(Exception):
    def __init__(self, detail: str):
        super().__init__(f"Not Found Error: {detail}")

class ValidationError(Exception):
    def __init__(self, detail: str):
        super().__init__(f"Validation Error: {detail}")

class LearningError(Exception):
    """학습 관련 예외 클래스"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class ParsingError(Exception):
    def __init__(self, message: str):
        super().__init__(f"Parsing Error: {message}")

class RedisError(Exception):
    def __init__(self, detail: str):
        super().__init__(f"Redis Error: {detail}")

class GithubAPIError(Exception):
    def __init__(self, detail: str):
        super().__init__(f"Github API Error: {detail}")

class WebhookOperationError(Exception):
    def __init__(self, detail: str):
        super().__init__(f"Webhook Operation Error: {detail}")
