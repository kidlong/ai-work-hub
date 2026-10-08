"""Xác thực người dùng với Active Directory on-prem.

- AUTH_MODE=ldap : bind LDAPS bằng UPN user@DOMAIN rồi đọc thông tin hồ sơ.
- AUTH_MODE=mock : dùng cho dev/demo, user nằm trong DEMO_USERS, mật khẩu "demo".

Mật khẩu người dùng KHÔNG được lưu ở bất kỳ đâu; chỉ dùng để bind một lần.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class Profile:
    username: str
    email: str
    display_name: str
    title: str = ""
    department: str = ""
    manager_email: str = ""


class AuthError(Exception):
    pass


DEMO_USERS: dict[str, Profile] = {
    "an.nguyen": Profile(
        username="an.nguyen",
        email="an.nguyen@bank.local",
        display_name="Nguyễn Văn An",
        title="Chuyên viên Phát triển ứng dụng",
        department="Khối Công nghệ - Phòng Core Banking",
        manager_email="minh.tran@bank.local",
    ),
    "lan.pham": Profile(
        username="lan.pham",
        email="lan.pham@bank.local",
        display_name="Phạm Thị Lan",
        title="Chuyên viên Quan hệ khách hàng doanh nghiệp",
        department="Khối Khách hàng doanh nghiệp",
        manager_email="hung.le@bank.local",
    ),
}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,64}$")


def authenticate(username: str, password: str) -> Profile:
    username = username.strip().lower()
    if "\\" in username:
        username = username.split("\\", 1)[1]
    if "@" in username:
        username = username.split("@", 1)[0]
    if not _USERNAME_RE.match(username) or not password:
        raise AuthError("Tên đăng nhập hoặc mật khẩu không đúng")

    s = get_settings()
    if s.auth_mode == "mock":
        profile = DEMO_USERS.get(username)
        if profile is None or password != "demo":
            raise AuthError("Tên đăng nhập hoặc mật khẩu không đúng")
        return profile
    return _ldap_authenticate(username, password)


def _ldap_authenticate(username: str, password: str) -> Profile:
    import ssl

    from ldap3 import ALL, Connection, Server, Tls
    from ldap3.core.exceptions import LDAPException
    from ldap3.utils.conv import escape_filter_chars

    s = get_settings()
    tls = Tls(
        validate=ssl.CERT_REQUIRED,
        ca_certs_file=s.ldap_ca_cert_file or None,
        version=ssl.PROTOCOL_TLS_CLIENT,
    )
    server = Server(s.ldap_url, use_ssl=s.ldap_url.startswith("ldaps"), tls=tls, get_info=ALL, connect_timeout=5)
    upn = f"{username}@{s.ldap_domain}"
    try:
        conn = Connection(server, user=upn, password=password, auto_bind=True, receive_timeout=10)
    except LDAPException as exc:
        raise AuthError("Tên đăng nhập hoặc mật khẩu không đúng") from exc

    try:
        conn.search(
            s.ldap_base_dn,
            f"(&(objectClass=user)(sAMAccountName={escape_filter_chars(username)}))",
            attributes=["mail", "displayName", "title", "department", "manager"],
        )
        if not conn.entries:
            raise AuthError("Không tìm thấy tài khoản trong thư mục")
        e = conn.entries[0]
        manager_email = ""
        if e.manager.value:
            conn.search(e.manager.value, "(objectClass=user)", attributes=["mail"])
            if conn.entries and conn.entries[0].mail.value:
                manager_email = str(conn.entries[0].mail.value)
        return Profile(
            username=username,
            email=str(e.mail.value or f"{username}@{s.ldap_domain.lower()}"),
            display_name=str(e.displayName.value or username),
            title=str(e.title.value or ""),
            department=str(e.department.value or ""),
            manager_email=manager_email,
        )
    finally:
        conn.unbind()
