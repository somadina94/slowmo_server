from fastapi import HTTPException, status


class AppError(HTTPException):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)


class UnauthorizedError(AppError):
    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)


class ForbiddenError(AppError):
    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class NotFoundError(AppError):
    def __init__(self, detail: str = "Not found") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ConflictError(AppError):
    def __init__(self, detail: str = "Conflict") -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)


class ValidationAppError(AppError):
    def __init__(self, detail: str = "Invalid request") -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)


class RateLimitError(AppError):
    def __init__(self, detail: str = "Too many requests") -> None:
        super().__init__(status.HTTP_429_TOO_MANY_REQUESTS, detail)
