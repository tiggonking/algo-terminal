import threading
import traceback
from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.header import Header
from email import encoders
from src.config.globals.log_setup import LOG
from src.config.globals.signals import SIGNALS
import os
from os.path import basename
import sys
from threading import Lock
import time as sleeper


class EmailHandler:

    # manages a queue of emails.
    # emails are added to the queue as [subject, body, attachments]
    # attachments are currently ignored

    def __init__(self, smtp_server, smtp_port, smtp_user, smtp_password, from_email, to_emails):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.to_emails = [e.strip() for e in to_emails]
        self.email_queue = []
        self.keep_alive = True
        self.last_emit_time = datetime.now()
        self._stop_signal = False
        self.email_lock = Lock()
        emailer_thread = threading.Thread(target=self.manage_logger_queue, name='Emailing Thread', daemon=False)
        emailer_thread.start()

    def send_email(self, subject, body, text_type, attachments_file_paths: list = None):

        assert text_type in ['html', 'plain']

        if attachments_file_paths is None:
            attachments_file_paths = []

        success, wait = False, 0
        while not success and not self.stop_signal():

            self.wait(wait)
            wait = min(wait + 1, 10)

            try:
                with self.email_lock:
                    # send email to all config recipients
                    for recipient in self.to_emails:

                        # set up email
                        msg = MIMEMultipart()
                        msg['From'] = f'QA OMS<{self.from_email}>'
                        msg['To'] = recipient
                        msg['Subject'] = str(Header(subject, 'utf-8'))
                        msg.attach(MIMEText(body, text_type, 'utf-8')) 

                        # add attachments
                        if attachments_file_paths:
                            for attachment_file_path in attachments_file_paths:
                                if isinstance(attachment_file_path, str) and os.path.isfile(attachment_file_path):
                                    try:
                                        ext = attachment_file_path.split('.')[-1]
                                        mime_type = ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                                                     if ext in ['xls', 'xlsx']
                                                     else 'application/octet-stream')
                                        with open(attachment_file_path, "rb") as file:
                                            attached_file = MIMEBase(*mime_type.split('/'))
                                            attached_file.set_payload(file.read())
                                        encoders.encode_base64(attached_file)
                                        attached_file.add_header('Content-Disposition', 'attachment',
                                                                 filename=os.path.basename(attachment_file_path))
                                        msg.attach(attached_file)
                                    except Exception as e:
                                        pass

                        # send email
                        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                            server.starttls()
                            server.login(self.smtp_user, self.smtp_password)
                            server.sendmail(self.from_email, recipient, msg.as_string())

                        # insert delay to avoid triggering spam filters
                        if len(self.to_emails) > 1:
                            self.wait(5)
                    success = True

                    self.wait(5)  # allow 5 seconds between sending emails, to avoid triggering spam filters

            except smtplib.SMTPDataError as e:
                if vars(e)['smtp_code'] == 554:
                    if wait >= 0:
                        self.handle_exception(e, vars(e)['smtp_error'])
                    else:
                        self.wait(10)
                else:
                    self.handle_exception(e, vars(e)['smtp_error'])

            except smtplib.SMTPServerDisconnected as e:
                if wait >= 0:
                    self.handle_exception(e, e.args[0])
                else:
                    self.wait(30)

            except Exception as e:
                LOG.error(msg=f'Unhandled error during emailing: {e.args[0]}')

            finally:
                try:
                    self.email_lock.release()
                except RuntimeError:
                    pass

    def wait(self, seconds):
        for _ in range(seconds * 10):
            if self.keep_alive:
                sleeper.sleep(0.1)
            else:
                break

    def stop_signal(self):
        while self._stop_signal:
            self.wait(1)
        if not self.keep_alive:
            sys.exit()
        else:
            return False

    def handle_exception(self, exception, error_text, level=2):
        trace = traceback.format_exception(exception)
        SIGNALS.exception.emit((level,
                                f'Error sending email: {error_text}. This error can occur when too many emails are '
                                f'sent. Wait a while and restart the OMS' if level == 2 else f'Error sending email: '
                                                                                             f'{error_text}.',
                                True,
                                trace))
        self._stop_signal = True
        self.stop_signal()

    def manage_logger_queue(self):

        # this manages the Logger message queue.
        # other individual messages can be sent directly using send_email

        self.last_emit_time = datetime.now()
        while self.keep_alive:
            try:
                while self.email_queue:

                    # collect log messages that are sent over a 10-second period
                    while datetime.now() < self.last_emit_time + timedelta(seconds=10):
                        self.wait(2)

                    # generate email subject and body from msg queue
                    if not self.email_queue and self.keep_alive:
                        # no log message
                        self.wait(1)
                        continue
                    elif len(self.email_queue) == 1:
                        # single log message
                        subject, email_body, attachments = self.email_queue.pop(0)
                    else:
                        # multiple log messages
                        email_body = ''
                        attachments = []
                        while self.email_queue:
                            next_msg = self.email_queue.pop(0)
                            email_body = email_body + str(next_msg[1]) + '\n'
                            if next_msg[2]:
                                attachments.append(next_msg[2])  # redundant, attachments aren't added to log messages
                        subject = 'QAOMS - Multiple Errors'

                    self.send_email(subject=subject, body=email_body, text_type='plain',
                                    attachments_file_paths=attachments)

                    self.last_emit_time = datetime.now()

            except Exception as e:
                self.handle_exception(e, e.args[0])

            self.wait(2)


# EMAIL_MANAGER variables are set during config
EMAIL_MANAGER = EmailHandler(smtp_server='', smtp_port='', smtp_user='', smtp_password='', from_email='', to_emails='')
