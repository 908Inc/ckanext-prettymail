import collections
import os
from email.encoders import encode_base64
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from smtplib import SMTP

import ckan.logic as logic
import magic
import paste.deploy.converters
from ckan.common import config


@logic.side_effect_free
def send_mail(context, data_dict):
    """
    Send email with attachments and text and html formats
    :param context:
    :param data_dict:
    :return:
    """
    mail_from = config.get('smtp.mail_from')
    kwargs = {
        'from_': data_dict['from'],
        'to': data_dict['to'],
        'subject': data_dict['subject'],
        'message_text': data_dict.get('message_text', None),
        'message_html': data_dict.get('message_html', None),
        'message_encoding': data_dict.get('message_encoding', 'utf-8')

    }
    if 'attachments' in data_dict and isinstance(data_dict['attachments'], collections.Iterable):
        kwargs['attachments'] = [[os.path.basename(a), open(a, 'r').read(), magic.from_file(a, mime=True)] for a in
                                 data_dict['attachments']]

    msg = Email(**kwargs)
    with EmailConnection() as server:
        server.send(msg, mail_from)


class Email(object):
    def __init__(self, from_, to, subject, message_text=None, message_html=None,
                 attachments=None, cc=None, message_encoding='utf-8'):
        self.email = MIMEMultipart()
        self.email['From'] = from_
        self.email['To'] = Header(to, 'utf-8')
        self.email['Subject'] = Header(subject.encode('utf-8'), 'utf-8')
        if cc is not None:
            self.email['Cc'] = cc
        if message_text:
            text = MIMEText(message_text, 'plain', message_encoding)
            self.email.attach(text)
        if message_html:
            text = MIMEText(message_html, 'html', message_encoding)
            self.email.attach(text)
        if attachments is not None:
            for filename, content, mimetype in attachments:
                mimetype = mimetype.split('/', 1)
                attachment = MIMEBase(mimetype[0], mimetype[1])
                attachment.set_payload(content)
                encode_base64(attachment)
                attachment.add_header('Content-Disposition', 'attachment',
                                      filename=os.path.basename(filename))
                self.email.attach(attachment)

    def __str__(self):
        return self.email.as_string()


class EmailConnection(object):
    def __init__(self):
        if 'smtp.test_server' in config:
            # If 'smtp.test_server' is configured we assume we're running tests,
            # and don't use the smtp.server, starttls, user, password etc. options.
            self.server = config['smtp.test_server']
            self.starttls = False
            self.username = None
            self.password = None
        else:
            self.server = config.get('smtp.server', 'localhost')
            self.starttls = paste.deploy.converters.asbool(config.get('smtp.starttls'))
            self.username = config.get('smtp.user')
            self.password = config.get('smtp.password')
        self.connect()

    def connect(self):
        self.connection = SMTP(self.server)
        self.connection.ehlo()
        # If 'smtp.starttls' is on in CKAN config, try to put the SMTP
        # connection into TLS mode.
        if self.starttls:
            if self.connection.has_extn('STARTTLS'):
                self.connection.starttls()
                # Re-identify ourselves over TLS connection.
                self.connection.ehlo()
            else:
                raise Exception("SMTP server does not support STARTTLS")
        if self.username and self.password:
            self.connection.login(self.username, self.password)

    def send(self, message, from_=None, to=None):
        if type(message) == str:
            if from_ is None or to is None:
                raise ValueError('You need to specify `from_` and `to`')
            else:
                to_emails = [to]
        else:
            from_ = message.email['From']
            if 'Cc' not in message.email:
                message.email['Cc'] = ''
            to_emails = [message.email['To']] + message.email['Cc'].split(',')
            message = str(message)
        return self.connection.sendmail(from_, to_emails, message)

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
