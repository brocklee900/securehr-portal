"""Is an employee an HR admin? Asks LDAP, the source of the hr_admin role (LDAP group -> Keycloak realm role).

The database only knows employee numbers, not roles, so this is how the API stops HR admins from changing
another HR admin's salary. It reads LDAP live on every check, so a promotion or removal applies at once.
Any failure (LDAP down, wrong password, not configured) raises HrLookupUnavailable and the change is refused:
the check fails closed."""
from ldap3 import BASE, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from .config import settings


class HrLookupUnavailable(Exception):
    """The directory could not answer, so nobody can tell whether the employee is an HR admin."""


def _connect() -> Connection:
    if not settings.ldap_bind_password:
        raise HrLookupUnavailable("LDAP_BIND_PASSWORD is not set")
    server = Server(settings.ldap_url, connect_timeout=5)
    return Connection(server, user=settings.ldap_bind_dn, password=settings.ldap_bind_password,
                      receive_timeout=5, raise_exceptions=True)


def is_hr_admin(emp_no: int, connect=_connect) -> bool:
    """True if any LDAP person with this employeeNumber is a direct member of the HR admin group."""
    try:
        with connect() as conn:
            conn.search(settings.ldap_people_dn, f"(employeeNumber={escape_filter_chars(str(int(emp_no)))})",
                        search_scope=SUBTREE, attributes=[])
            people = [entry.entry_dn for entry in conn.entries]
            for dn in people:
                conn.search(settings.ldap_hr_group_dn, f"(member={escape_filter_chars(dn)})",
                            search_scope=BASE, attributes=[])
                if conn.entries:
                    return True
            return False
    except HrLookupUnavailable:
        raise
    except LDAPException as exc:
        raise HrLookupUnavailable(exc.__class__.__name__) from exc
