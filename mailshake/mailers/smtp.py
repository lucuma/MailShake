"""
SMTP mailer.
"""
import smtplib
import ssl
import threading
import typing as t
from itertools import islice
from functools import cached_property
from os import PathLike

from ..message import EmailMessage
from ..utils import DNS_NAME
from .base import BaseMailer


StrOrBytesPath: t.TypeAlias = str | bytes | PathLike[str] | PathLike[bytes]


def batched(iterable, n):
    """Batch data from the iterable into tuples of length n.
    The last batch may be shorter than n."""
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        yield batch


class SMTPMailer(BaseMailer):
    """A wrapper that manages the SMTP network connection.

    `max_recipients`: Number of maximum recipients per mesage
        Mailshake send several messages instead of one, in order to stay inside
        that limit.

    """

    def __init__(
        self,
        host: str = "localhost",
        port: int =587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = False,
        use_ssl: bool = False,
        timeout: int | None = None,
        ssl_keyfile: StrOrBytesPath | None = None,
        ssl_certfile: StrOrBytesPath | None = None,
        max_recipients: int = 200,
        *args,
        **kwargs,
    ):
        super(SMTPMailer, self).__init__(*args, **kwargs)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = bool(use_tls)
        self.use_ssl = bool(use_ssl)
        self.ssl_keyfile = ssl_keyfile
        self.ssl_certfile = ssl_certfile
        self.timeout = timeout
        if self.use_ssl and self.use_tls:
            raise ValueError("use_ssl/use_tls are mutually exclusive")
        if max_recipients < 1:
            raise ValueError("max_recipients must be at least one")
        self.max_recipients = max_recipients

        self.connection = None
        self._lock = threading.RLock()

    @property
    def connection_class(self):
        return smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP

    @cached_property
    def ssl_context(self):
        if self.ssl_certfile:
            ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)
            return ssl_context
        else:
            return ssl.create_default_context()

    def open(self, local_hostname: str = ""):
        """Ensures we have a connection to the email server. Returns whether or
        not a new connection was required (True or False).
        """
        if self.connection:
            # Nothing to do if the connection is already open.
            return False

        # If local_hostname is not specified, socket.getfqdn() gets used.
        # For performance, we use the cached FQDN for local_hostname.
        connection_params: dict[str, t.Any] = {
            "local_hostname": local_hostname or DNS_NAME.get_fqdn()
        }
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
        if self.use_ssl:
            connection_params["context"] = self.ssl_context

        try:
            self.connection = self.connection_class(
                self.host, self.port, **connection_params
            )

            # TLS/SSL are mutually exclusive, so only attempt TLS over
            # non-secure connections.
            if not self.use_ssl and self.use_tls:
                self.connection.starttls(context=self.ssl_context)
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise

    def close(self):
        """Close the connection to the email server."""
        if self.connection is None:
            return
        try:
            try:
                self.connection.quit()
            except (ssl.SSLError, smtplib.SMTPServerDisconnected):
                # This happens when calling quit() on a TLS connection
                # sometimes, or when the connection was already disconnected
                # by the server.
                self.connection.close()
            except smtplib.SMTPException:
                if self.fail_silently:
                    return
                raise
        finally:
            self.connection = None

    def send_messages(self, *messages: EmailMessage):
        """
        Send one or more EmailMessage objects and return the number of email
        messages sent.
        """
        if not messages:
            return 0
        with self._lock:
            new_conn_created = self.open()
            if not self.connection or new_conn_created is None:
                # We failed silently on open().
                # Trying to send would be pointless.
                return 0
            num_sent = 0
            try:
                for message in messages:
                    sent = self._send(message)
                    if sent:
                        num_sent += 1
            finally:
                if new_conn_created:
                    self.close()
        return num_sent

    def _send(self, message: EmailMessage):
        """A helper method that does the actual sending."""

        recipients = message.get_recipients()
        if not recipients:
            return False

        from_addr = message.from_addr or self.default_from
        to_set = set(message.to)
        cc_set = set(message.cc)
        bcc_set = set(message.bcc)

        try:
            assert self.connection is not None
            # Your SMTP provider has limits!
            for group in batched(recipients, self.max_recipients):
                to_addrs = set(group)
                message.to = list(to_set.intersection(to_addrs))
                message.cc = list(cc_set.intersection(to_addrs))
                message.bcc = list(bcc_set.intersection(to_addrs))
                msg = message.render().as_bytes(linesep="\r\n")
                self.connection.sendmail(
                    from_addr=from_addr,
                    to_addrs=list(to_addrs),
                    msg=msg,
                )

            return True
        except Exception:
            if not self.fail_silently:
                raise
            return False
