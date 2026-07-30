class AIProviderError(RuntimeError):
    """Base exception for provider failures safe to map at the API boundary."""


class AIProviderConfigurationError(AIProviderError):
    pass


class AIProviderTimeoutError(AIProviderError):
    pass


class AIProviderResponseError(AIProviderError):
    pass


class AIProviderUnavailableError(AIProviderError):
    pass
