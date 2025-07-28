from __future__ import annotations
import dataclasses
import uuid
import user_agents
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request


def get_request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip = forwarded_for.split(",")[0]
    else:
        ip = request.client.host if request.client else "unknown"

    return ip


def get_client_user_agent(request: Request) -> ClientUserAgent:
    return ClientUserAgent.from_request(request)


@dataclasses.dataclass(slots=True)
class ClientUserAgent:
    user_agent: str
    browser: str
    browser_version: str
    os: str
    os_version: str
    device: str

    @classmethod
    def from_request(cls, request: Request) -> ClientUserAgent:
        user_agent = request.headers.get("User-Agent", "")
        parsed_ua = user_agents.parse(user_agent)
        return cls(
            user_agent=user_agent,
            browser=parsed_ua.browser.family,
            browser_version=parsed_ua.browser.version_string,
            os=parsed_ua.os.family,
            os_version=parsed_ua.os.version_string,
            device=parsed_ua.device.family,
        )

    @property
    def uaid(self) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, self.user_agent))

    def __str__(self) -> str:
        return f"{self.browser} {self.browser_version} on {self.os} {self.os_version} ({self.device})"


@dataclasses.dataclass(slots=True)
class ClientInfo:
    ip_address: str
    user_agent: ClientUserAgent

    def __str__(self) -> str:
        return f"IP: {self.ip_address}, User-Agent: {self.user_agent}"

    def __repr__(self) -> str:
        return f"ClientInfo<ip_address={self.ip_address}, user_agent={self.user_agent}>"


async def get_client_info(request: Request) -> ClientInfo:
    ip_address = get_request_ip(request)
    user_agent = get_client_user_agent(request)
    return ClientInfo(ip_address=ip_address, user_agent=user_agent)
