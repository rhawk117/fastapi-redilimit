from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from .utils import get_request_ip, get_client_info, get_client_user_agent

if TYPE_CHECKING:
    from fastapi import Request


class AbstractKeyGenerator(ABC):
    '''
    Produces a unique key for each request based on the request's
    context such as IP address, user agent, or client fingerprint.
    '''
    def __init__(self, prefix: str = "ratelimit") -> None:
        self.prefix: str = prefix

    @abstractmethod
    async def __call__(self, request: Request) -> str: ...


class IPKeyGenerator(AbstractKeyGenerator):
    '''
    Produces a unique key based on the request's IP address,
    **warning** this may not be viable in all cases, such as when
    the request is behind a proxy or load balancer.
    '''
    async def __call__(self, request: Request) -> str:
        ip_address = get_request_ip(request)
        return f"{self.prefix}:ip:{ip_address}"


class ClientKeyGenerator(AbstractKeyGenerator):
    '''
    **Reccomended**
    Produces a unique key based on the request's client fingerprint,
    which includes both the IP address and user agent.
    '''
    def __init__(self, prefix: str = "ratelimit") -> None:
        self.prefix = prefix

    async def __call__(self, request: Request) -> str:
        fingerprint = await get_client_info(request)
        return (
            f"{self.prefix}:fp:{fingerprint.ip_address}:{fingerprint.user_agent.uaid}"
        )


class UserAgentKeyGenerator(AbstractKeyGenerator):
    '''
    Produces a unique key based on the request's user agent.
    '''
    async def __call__(self, request: Request) -> str:
        user_agent = get_client_user_agent(request)
        return f"{self.prefix}:ua:{user_agent.uaid}"
