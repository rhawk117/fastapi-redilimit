from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from .utils import get_request_ip, get_client_info, get_client_user_agent

if TYPE_CHECKING:
    from fastapi import Request


class AbstractKeyGenerator(ABC):
    def __init__(self, prefix: str = "ratelimit") -> None:
        self.prefix: str = prefix

    @abstractmethod
    async def __call__(self, request: Request) -> str: ...


class IPKeyGenerator(AbstractKeyGenerator):
    async def __call__(self, request: Request) -> str:
        ip_address = get_request_ip(request)
        return f"{self.prefix}:ip:{ip_address}"


class ClientKeyGenerator(AbstractKeyGenerator):
    def __init__(self, prefix: str = "ratelimit") -> None:
        self.prefix = prefix

    async def __call__(self, request: Request) -> str:
        fingerprint = await get_client_info(request)
        return (
            f"{self.prefix}:fp:{fingerprint.ip_address}:{fingerprint.user_agent.uaid}"
        )


class UserAgentKeyGenerator(AbstractKeyGenerator):
    async def __call__(self, request: Request) -> str:
        user_agent = get_client_user_agent(request)
        return f"{self.prefix}:ua:{user_agent.uaid}"
