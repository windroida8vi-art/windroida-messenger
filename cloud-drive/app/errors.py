"""Uniform API errors: every error has a stable code plus Persian and English messages."""


class ApiError(Exception):
    def __init__(self, code, fa, en=None, status=400, **extra):
        super().__init__(code)
        self.code, self.fa, self.en, self.status, self.extra = code, fa, en or code, status, extra


def fail(code, fa, en=None, status=400, **extra):
    raise ApiError(code, fa, en, status, **extra)
