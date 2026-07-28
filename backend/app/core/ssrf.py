"""SSRF-защита: цель монитора не должна вести во внутреннюю сеть.

Без этой проверки арендатор может навести монитор на служебные адреса
(postgres:5432, 169.254.169.254 — метаданные облака, 127.0.0.1) и заставить
воркер ходить по внутренней инфраструктуре. Блокируем непубличные адреса.

Два режима использования:
- resolve=True (воркеры): резолвим hostname и проверяем каждый адрес — реальная
  защита в момент запроса, ловит и DNS, указывающий на приватный диапазон.
- resolve=False (API): без сети — быстрый фидбек на литеральный приватный IP или
  localhost при создании монитора; полную проверку делает воркер.

on-prem-инсталляции, где мониторить внутренние сервисы легитимно, снимают
проверку через allow_private_targets.
"""
import ipaddress
import socket
from urllib.parse import urlparse

# hostname-и, которые нельзя резолвить в публичный адрес по определению
_BLOCKED_HOSTNAMES = {"localhost"}


class BlockedTargetError(ValueError):
    """URL монитора ведёт на непубличный адрес — блокируется SSRF-защитой."""


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _reject_private_ip(ip_str: str) -> None:
    # IPv4-mapped IPv6 (::ffff:127.0.0.1) проверяем по вложенному v4-адресу
    ip = ipaddress.ip_address(ip_str)
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if not _ip_is_public(ip):
        raise BlockedTargetError(f"target resolves to non-public address {ip_str}")


def resolve_public_address(url: str, *, allow_private: bool = False, resolve: bool = True) -> str | None:
    """Проверяет URL и возвращает адрес, к которому РАЗРЕШЕНО подключаться.

    None — привязывать соединение к адресу не нужно (проверка снята
    allow_private) или невозможно (resolve=False, режим API без обращения к сети).

    Возврат адреса позволяет вызывающему подключиться именно к проверенному IP.
    Иначе между проверкой и соединением остаётся окно: хост под контролем
    арендатора отдаёт публичный адрес на проверку и приватный — на подключение
    (DNS rebinding), и клиент, резолвящий имя заново, уходит во внутреннюю сеть.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedTargetError(
            f"unsupported URL scheme '{parsed.scheme}': only http and https are allowed"
        )
    host = parsed.hostname
    if not host:
        raise BlockedTargetError("URL is missing a host")
    # .port — ленивое свойство: на порту вне 0-65535 или нечисловом оно бросает
    # ValueError, а не возвращает None. Раньше это исключение улетало из функции
    # мимо BlockedTargetError, и вызывающие его не ловили: одна push-подписка на
    # адрес с таким портом валила рассылку всей организации, не доходя до
    # остальных подписок. Разбираем порт здесь, до любых веток, чтобы негодный
    # URL одинаково отвергался и в API (resolve=False), и в воркере
    try:
        port = parsed.port
    except ValueError as exc:
        raise BlockedTargetError(f"invalid port in URL: {exc}") from exc
    if allow_private:
        return None

    lowered = host.lower()
    if lowered in _BLOCKED_HOSTNAMES or lowered.endswith(".localhost"):
        raise BlockedTargetError(f"target host '{host}' is not allowed")

    # литеральный IP проверяем всегда — без обращения к сети
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        _reject_private_ip(host)
        return host

    if not resolve:
        return None

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedTargetError(f"cannot resolve host '{host}'") from exc
    for info in infos:
        # проверяем КАЖДЫЙ адрес: имя, часть адресов которого приватная, блокируем
        # целиком — иначе выбор адреса решал бы, сработает защита или нет
        _reject_private_ip(info[4][0])
    return infos[0][4][0]


def validate_public_url(url: str, *, allow_private: bool = False, resolve: bool = True) -> None:
    """Бросает BlockedTargetError, если URL нельзя мониторить. Иначе возвращает None."""
    resolve_public_address(url, allow_private=allow_private, resolve=resolve)
