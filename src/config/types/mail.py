# Important note: DO NOT rename this file to email.py. This messes with the import system as python has an internal email.py module
# That is imported by pydantic in it's implementation and naming this file email.py will override that.
from pydantic import BaseModel, Field, SecretStr, BeforeValidator
from pydantic import EmailStr
from typing import List, Annotated
from enum import Enum

class SMTPHosts(Enum):
    """
    Common SMTP server hosts. This is not an exhaustive list and can be expanded
    based on requirements. See https://www.arclab.com/en/kb/email/list-of-smtp-and-pop3-servers-mailserver-list.html
    """
    GMAIL = "smtp.gmail.com"
    OUTLOOK = "smtp.live.com"
    YAHOO = "smtp.mail.yahoo.com"
    AOL = "smtp.aol.com"
    OFFICE365 = "smtp.office365.com"

class SMTPPorts(Enum):
    """
    Standard SMTP ports:
    - TLS: Most common, uses STARTTLS for encryption
    - SSL: Legacy SSL/TLS encryption
    - ALT: Alternative port for specific configurations
    """
    TLS = 587
    SSL = 465
    ALT = 2525

# Custom error messages for incorrect values
EMAIL_ERROR_MESSAGES = {
    'unsupported_host': 'SMTP host {host} is not supported yet. Supported hosts are: {supported_hosts}',
    'unsupported_port': 'SMTP port {port} is not supported yet. Supported ports are: {supported_ports}',
    'invalid_combination': 'Invalid combination: {details}',
}

# Here we define the email configurations that are actually supported by the system
SUPPORTED_SMTP_HOSTS = [
    SMTPHosts.GMAIL
]

SUPPORTED_SMTP_PORTS = [
    SMTPPorts.TLS,
    SMTPPorts.SSL
]

# Validator functions for supported values
def validate_smtp_host(host: SMTPHosts) -> SMTPHosts:
    if host not in SUPPORTED_SMTP_HOSTS:
        raise ValueError(EMAIL_ERROR_MESSAGES['unsupported_host'].format(
            host=host.value,
            supported_hosts=', '.join(h.value for h in SUPPORTED_SMTP_HOSTS)
        ))
    return host

def validate_smtp_port(port: SMTPPorts) -> SMTPPorts:
    if port not in SUPPORTED_SMTP_PORTS:
        raise ValueError(EMAIL_ERROR_MESSAGES['unsupported_port'].format(
            port=port.value,
            supported_ports=', '.join(str(p.value) for p in SUPPORTED_SMTP_PORTS)
        ))
    return port

# These are the annotated types that we use in downstream code
SupportedSMTPHost = Annotated[SMTPHosts, BeforeValidator(validate_smtp_host)]
SupportedSMTPPort = Annotated[SMTPPorts, BeforeValidator(validate_smtp_port)]

class EmailConfig(BaseModel):
    """
    Configuration for email sending via SMTP.
    Only supports specific combinations of hosts and ports that have been tested and verified.
    """
    sending_address: EmailStr = Field(..., description="The email address that will appear as the sender.")
    username: EmailStr = Field(..., description="The username for authenticating with the SMTP server.")
    password: SecretStr = Field(..., description="The password for authenticating with the SMTP server.")
    host_address: SupportedSMTPHost = Field(..., description="The SMTP server host address (e.g., smtp.gmail.com).")
    smtp_port: SupportedSMTPPort = Field(..., description="The port number for the SMTP server (e.g., 587 for TLS, 465 for SSL).")
    recipients: List[EmailStr] = Field(..., description="A list of recipient email addresses.")

if __name__ == "__main__":
    try:
        # This should raise a validation error for unsupported host
        config = EmailConfig(
            sending_address="sender@example.com",
            username="user@example.com",
            password="supersecret",
            host_address=SMTPHosts.YAHOO,  # Not in supported hosts
            smtp_port=SMTPPorts.TLS,
            recipients=["recipient1@example.com", "recipient2@example.com"]
        )
    except Exception as e:
        print("Validation error:", e)