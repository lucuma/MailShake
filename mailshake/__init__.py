from .mailers.base import BaseMailer  # noqa
from .mailers.console import ToConsoleMailer  # noqa
from .mailers.filebased import ToFileMailer  # noqa
from .mailers.memory import ToMemoryMailer  # noqa
from .mailers.smtp import SMTPMailer  # noqa
from .mailers.amazon_ses import AmazonSESMailer  # noqa
from .message import EmailMessage  # noqa

Mailer = ToConsoleMailer
