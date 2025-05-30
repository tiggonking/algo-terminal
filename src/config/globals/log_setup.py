from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from src.config.globals.addresses import ADDR
from src.config.globals.signals import SIGNALS
import logging
import logging.handlers
import os
import smtplib
from smtplib import SMTP
import sys
import threading
import time as sleeper
import traceback


class ColoredFormatter(logging.Formatter):
    """
    Color	Foreground Code	Background Code
    Black	\033[30m	\033[40m
    Red	    \033[31m	\033[41m
    Green	\033[32m	\033[42m
    Yellow	\033[33m	\033[43m
    Blue	\033[34m	\033[44m
    Magenta	\033[35m	\033[45m
    Cyan	\033[36m	\033[46m
    White	\033[37m	\033[47m
    """

    def format(self, record):
        # Add ANSI escape codes to color the log level
        if record.levelno == logging.DEBUG:
            prefix = '\033[0;30mDEBUG:\033[0;30m '
        elif record.levelno == logging.INFO:
            prefix = '\033[0;30mINFO: \033[0;30m '
        elif record.levelno == logging.WARNING:
            prefix = '\033[0;31mALERT:\033[0;31m '
        elif record.levelno == logging.ERROR:
            prefix = '\033[0;31mERROR:\033[0;31m '
        elif record.levelno == logging.CRITICAL:
            prefix = '\033[1;31mCRITICAL:\033[1;31m '
        else:
            prefix = ''
        # Call the parent class's format method to get the log message
        message = super().format(record)
        # Combine the prefix and message and return the result
        return prefix + message


class customSMTPHandler(logging.handlers.SMTPHandler):
    # This replaces a previous/deprecated customSMTPHandler class. To maintain integration with rest of code, this
    # is preserved as a SMPTHandler object, but no SMTPHandler functionality is used. Log records are instead sent
    # to the email_notifier object which manages sending the emails.

    def __init__(self, mailhost=None, fromaddr=None, toaddrs=None, subject=None,
                 credentials=None, secure=None, timeout=5.0):
        self.email_notifier = None  # added during setup/config
        super().__init__(mailhost, fromaddr, toaddrs, subject, credentials=credentials, secure=secure, timeout=timeout)

    def getSubject(self, record):
        return f'QAOMS Error - {record.msg[:80]}'

    def emit(self, record):
        # messages are added to the email_notifier object, as [subject, body, attachment]
        self.email_notifier.email_queue.append([self.getSubject(record), str(record.msg), None])


# Deprecated version - this integrated Email management with the SMTP handler
# 21/6/24 - Email management split into separate class
@DeprecationWarning
class customSMTPHandler_deprecated(logging.handlers.SMTPHandler):

    def __init__(self, mailhost, fromaddr, toaddrs, subject, credentials=None, secure=None, timeout=5.0):
        self.email_queue = list()
        self.last_emit_time = datetime.now()
        self.keep_alive = True
        self._stop_signal = False
        emailer_thread = threading.Thread(target=self.manage_email_queue, name='Emailing Thread', daemon=False)
        emailer_thread.start()
        super().__init__(mailhost, fromaddr, toaddrs, subject, credentials=credentials, secure=secure, timeout=timeout)

    def getSubject(self, record):
        return f'QAOMS Error - {record.msg[:80]}'

    def emit(self, record):
        self.email_queue.append(record)

    def wait(self, seconds):
        for n in range(1, seconds):
            if self.keep_alive:
                sleeper.sleep(1)

    def stop_signal(self):
        # waits until the stop_signal flag is cleared, or the oms is forced to exit
        while self._stop_signal:
            sleeper.sleep(1)
        if not self.keep_alive:
            sys.exit()
        else:
            return False

    def handle_exception(self, exception, error_text, level=2):
        trace = traceback.format_exception(exception)
        if level == 2:
            SIGNALS.exception.emit((2,
                                    f'Error sending email: {error_text}. This error can occur when too '
                                    f'many emails are sent. Wait a while and restart the OMS',
                                    True,
                                    trace))
        else:
            SIGNALS.exception.emit((level,
                                    f'Error sending email: {error_text}.',
                                    True,
                                    trace))
        self._stop_signal = True
        self.stop_signal()

    def manage_email_queue(self):
        # this is a fairly crude management of the email queue, to combine messages where possible, and to avoid
        # yahoo spam limitations

        self.last_emit_time = datetime.now()

        while self.keep_alive:
            try:
                while self.email_queue:

                    while datetime.now() < self.last_emit_time + timedelta(seconds=10):
                        # throttle emails to avoid yahoo spam limitations
                        sleeper.sleep(2)

                    if not self.email_queue:
                        # no new messages to send
                        sleeper.sleep(1)
                        continue

                    elif len(self.email_queue) == 1:
                        # one message to send
                        record = self.email_queue.pop(0)
                        subject = self.getSubject(record)
                        email_body = str(record.msg)

                    else:
                        # multiple messages to send - combine into single email
                        email_body = ''
                        while self.email_queue:
                            r = self.email_queue.pop(0)
                            email_body = email_body + str(r.msg) + '\n'
                        subject = 'QAOMS - Multiple Errors'

                    # send email
                    success, wait = False, 0
                    while not success and not self.stop_signal():
                        self.wait(wait)
                        wait = min(wait + 1, 10)  # to avoid yahoo spam limitations
                        try:
                            msg = MIMEMultipart()
                            msg['From'] = formataddr((str(Header('QA OMS Info', 'utf-8')), self.fromaddr))
                            msg['To'] = ','.join(self.toaddrs)
                            msg['Subject'] = subject
                            msg.attach(MIMEText(email_body, 'plain'))
                            server = SMTP(self.mailhost, self.mailport)
                            server.starttls()
                            server.login(self.username, self.password)
                            server.sendmail(self.fromaddr, ','.join(self.toaddrs), msg.as_string())
                            server.quit()
                            success = True
                            self.last_emit_time = datetime.now()
                        except smtplib.SMTPDataError as e:
                            if vars(e)['smtp_code'] == 554:
                                if wait >= 0:
                                    self.handle_exception(e, vars(e)['smtp_error'])
                                else:
                                    # too many messages
                                    self.wait(10)
                            else:
                                self.handle_exception(e, vars(e)['smtp_error'])
                        except smtplib.SMTPServerDisconnected as e:
                            if wait >= 0:
                                self.handle_exception(e, e.args[0])
                            else:
                                # disconnection can be because of too many messages
                                self.wait(30)
                self.wait(10)
            except Exception as e:
                self.handle_exception(e, e.args[0])


LOG = logging.getLogger('OMS')

if not LOG.handlers:

    # FROM OTHER CODE
    # LOG.setLevel(logging.DEBUG)
    # stream_handler = logging.StreamHandler()
    # stream_handler.setLevel(logging.DEBUG)
    # stream_handler.name = 'Stream Handler'
    # formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    # stream_handler.setFormatter(formatter)
    # LOG.addHandler(stream_handler)

    default_sender_address = ''
    default_recipient_addresses = ''
    default_username = ''
    default_password = ''
    default_smtp_port = 0

    LOG.setLevel(logging.DEBUG)

    # GLOBAL LOG FILE HANDLER - All logging levels saved to global log file
    if not os.path.isdir(f'{ADDR.folder_log_files}\\Global Log\\'):
        os.mkdir(f'{ADDR.folder_log_files}\\Global Log\\')
    global_handler = logging.handlers.TimedRotatingFileHandler(filename=f'{ADDR.folder_log_files}\\Global Log\\'
                                                                        f'Global Debug Log.txt',
                                                               when='midnight',
                                                               backupCount=7)
    global_handler.setLevel(logging.DEBUG)
    global_handler.setFormatter(logging.Formatter('%(asctime)s - %(threadName)s:%(funcName)s:%(lineno)s - '
                                                  '%(levelname)s - %(message)s'))
    global_handler.name = 'Global Debug Log'
    global_handler.suffix = '%Y-%m-%d.txt'

    # CONSOLE HANDLER - Info and above - format red for Warning and above
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(ColoredFormatter('%(asctime)s - %(message)s'))
    stream_handler.name = 'Stream Handler'

    # EMAIL HANDLER - Email ERROR and above

    smtp_handler = customSMTPHandler(mailhost=(default_username, default_smtp_port),
                                     fromaddr=default_sender_address,
                                     toaddrs=[default_recipient_addresses],
                                     subject='QAOMS Error',
                                     credentials=(default_username, default_password),
                                     secure=())
    smtp_handler.name = 'SMTP Handler'
    smtp_handler.setLevel(logging.ERROR)

    # add all handlers to log
    LOG.addHandler(global_handler)
    LOG.addHandler(stream_handler)
    LOG.addHandler(smtp_handler)

    LOG.debug(f'Logging Initiated')
