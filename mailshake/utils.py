"""
Adapted from Django (http://djangoproject.com).
The original code was BSD licensed (see LICENSE)
"""
from datetime import datetime
from email.charset import Charset
from email.utils import formataddr, parseaddr
import os
import socket
import threading
import warnings


class CachedDnsName:
    """Cache the hostname, but do it lazily: socket.getfqdn() can take a
    couple of seconds, which slows down the restart of the server.
    """

    def __str__(self):
        return self.get_fqdn()

    def get_fqdn(self):
        if not hasattr(self, "_fqdn"):
            self._fqdn = socket.getfqdn()
        return self._fqdn


DNS_NAME = CachedDnsName()


def punycode(domain):
    """Return the Punycode of the given domain if it's non-ASCII."""
    return domain.encode("idna").decode("ascii")


def encode_address(addr, charset):
    """Encode a pair of (name, address) or an email address string.

    When non-ascii characters are present in the name or local part, they're
    MIME-word encoded. The domain name is idna-encoded if it contains
    non-ascii characters.
    """
    if not isinstance(addr, tuple):
        addr = parseaddr(force_str(addr))
    name, addr = addr
    if isinstance(charset, str):
        charset = Charset(charset)
    if "@" in addr:
        localpart, domain = addr.rsplit("@", 1)
        # Try to get the simplest encoding - ascii if possible so that
        # to@example.com doesn't become =?utf-8?q?to?=@example.com. This
        # makes unit testing a bit easier and more readable.
        try:
            localpart.encode("ascii")
        except UnicodeEncodeError:
            localpart = charset.header_encode(localpart)
        addr = localpart + "@" + domain.encode("idna").decode("ascii")
        del localpart, domain
    else:
        try:
            addr.encode("ascii")
        except UnicodeEncodeError:
            addr = charset.header_encode(addr)
    return formataddr((name, addr), charset=charset)


def sanitize_address(addr, encoding):
    warnings.warn(
        "the sanitize_address function has been replaced by encode_address",
        DeprecationWarning,
    )
    return encode_address(addr, encoding)


thread_lock = threading.Lock()


def make_msgid(idstring=None, host_id=DNS_NAME):
    """Returns a string suitable for RFC 2822 compliant Message-ID, e.g:

    <20200818100350.554898.7effb56bc790.44@mail.example.com>

    The optional idstring argument is used to strengthen the uniqueness of the
    message id.

    The optional host_id argument allows you to specify the last part of the
    message ID. It must be a globally unique ID, preferably a valid domain name.
    By default the name returned by `socket.getfqdn()` is used, however it isn't
    guaranteed to be globally unique.
    """
    utcdate = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    try:
        pid = os.getpid()
    except AttributeError:
        pid = 1
    function_id = id(make_msgid)
    with thread_lock:
        try:
            make_msgid.counter += 1
        except AttributeError:
            make_msgid.counter = 1
        sequence_id = make_msgid.counter
    if idstring is None:
        idstring = ""
    else:
        idstring = "." + idstring
    return "<{}.{}.{:x}.{}{}@{}>".format(
        utcdate, pid, function_id, sequence_id, idstring, host_id
    )


def forbid_multi_line_headers(name, val):
    """Forbids multi-line headers, to prevent header injection."""
    if "\n" in val or "\r" in val:
        raise ValueError(
            "Header values can't contain newlines "
            "(got {val} for header {name})".format(val=val, name=name)
        )


def force_str(s, encoding="utf-8", errors="strict"):
    """Force a string to be the native text_type"""
    if isinstance(s, str):
        return s
    return str(s, encoding, errors)
