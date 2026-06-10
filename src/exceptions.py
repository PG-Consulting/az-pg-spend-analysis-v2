"""Domain exceptions for Spend.AI."""


class SpendAnalysisError(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


class NotFoundError(SpendAnalysisError):
    """Resource not found (404)."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(f"{resource} '{identifier}' not found", status_code=404)
        self.resource = resource
        self.identifier = identifier


class ValidationError(SpendAnalysisError):
    """Invalid input (400)."""

    def __init__(self, message: str, field: str = None):
        super().__init__(message, status_code=400)
        self.field = field


class ConflictError(SpendAnalysisError):
    """Conflicting state (409)."""

    def __init__(self, message: str):
        super().__init__(message, status_code=409)


class ExternalServiceError(SpendAnalysisError):
    """External service failure (502)."""

    def __init__(self, service: str, message: str):
        super().__init__(f"{service}: {message}", status_code=502)
        self.service = service


class BillingError(ExternalServiceError):
    """Falha de billing/créditos em serviço externo (fatal — não retentar).

    Levantada quando a API LLM retorna 401/403 (créditos esgotados ou chave
    inválida). Retry não resolve; o job deve ser marcado ERROR imediatamente
    com a mensagem explícita para o consultor.
    """

    def __init__(self, message: str, service: str = "xAI"):
        # Bypassa o prefixo "{service}: " de ExternalServiceError — a mensagem
        # já é exibida diretamente ao consultor em PT-BR.
        SpendAnalysisError.__init__(self, message, status_code=502)
        self.service = service


class AuthenticationError(SpendAnalysisError):
    """Authentication required (401)."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, status_code=401)


class ForbiddenError(SpendAnalysisError):
    """Insufficient permissions (403)."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, status_code=403)
