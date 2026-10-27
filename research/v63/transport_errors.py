"""Transport error contract shared without importing numerical dependencies."""


class InfraFailure(Exception):
    def __init__(self, message, retryable=True, retry_after=0, partial_content=None, generation_attempted=True):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
        self.partial_content = partial_content
        self.generation_attempted = generation_attempted


class ProtocolViolation(Exception):
    def __init__(self, message, generation_attempted=False):
        super().__init__(message)
        self.generation_attempted = generation_attempted
