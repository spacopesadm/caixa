# -*- coding: utf-8 -*-
"""
Envio do relatório por e-mail (SMTP).
Usado pelo caixa.pyw. Funciona com Gmail, Outlook, Yahoo e qualquer provedor que aceite SMTP.

Gmail: ligue a "verificação em duas etapas" na conta e crie uma "senha de app"
(Conta Google > Segurança > Senhas de app). Use essa senha aqui, não a senha normal.
"""
import mimetypes
import os
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

PROVEDORES = {
    "Gmail": ("smtp.gmail.com", 465, "ssl"),
    "Outlook / Hotmail": ("smtp-mail.outlook.com", 587, "starttls"),
    "Yahoo": ("smtp.mail.yahoo.com", 465, "ssl"),
}


def destinatarios(texto):
    return [x for x in re.split(r"[,;\s]+", str(texto or "")) if x]


def montar(cfg, assunto, corpo, anexos):
    user = (cfg.get("email_usuario") or "").strip()
    de = (cfg.get("email_de") or "").strip()
    para = destinatarios(cfg.get("email_para"))
    # "de" pode ser só um nome (ex.: CheckList Caixa) ou um endereço
    if "@" in de:
        remetente, nome = de, ""
    else:
        remetente, nome = user, de
    if not remetente or not para:
        raise ValueError("Preencha o e-mail de quem envia e o e-mail de quem recebe.")
    msg = EmailMessage()
    msg["From"] = formataddr((nome, remetente)) if nome else remetente
    msg["To"] = ", ".join(para)
    msg["Subject"] = assunto
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(corpo)
    for caminho in anexos or []:
        tipo, _ = mimetypes.guess_type(caminho)
        maintype, subtype = (tipo or "application/octet-stream").split("/", 1)
        with open(caminho, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(caminho))
    return msg, remetente, para


def enviar(cfg, assunto, corpo, anexos=None):
    """Envia o e-mail. Levanta uma exceção se não conseguir."""
    host = (cfg.get("email_servidor") or "").strip()
    if not host:
        raise ValueError("Preencha o servidor de e-mail (SMTP).")
    porta = int(cfg.get("email_porta") or 465)
    seg = (cfg.get("email_seguranca") or "ssl").lower()
    user = (cfg.get("email_usuario") or "").strip()
    senha = (cfg.get("email_senha") or "").replace(" ", "")   # senha de app do Gmail vem com espaços
    msg, de, para = montar(cfg, assunto, corpo, anexos)
    ctx = ssl.create_default_context()
    if seg == "ssl":
        srv = smtplib.SMTP_SSL(host, porta, timeout=30, context=ctx)
    else:
        srv = smtplib.SMTP(host, porta, timeout=30)
    with srv:
        srv.ehlo()
        if seg == "starttls":
            srv.starttls(context=ctx)
            srv.ehlo()
        if user:
            srv.login(user, senha)
        srv.send_message(msg, from_addr=de, to_addrs=para)


def erro_amigavel(e):
    """Traduz o erro para uma frase que dá para entender."""
    if isinstance(e, ValueError):
        return str(e)
    if isinstance(e, smtplib.SMTPServerDisconnected):
        return ("O servidor fechou a conexão. Confira o e-mail de quem envia e a senha de app. "
                "Se continuar, o antivírus ou o firewall pode estar bloqueando a porta 465 (tente Segurança STARTTLS, porta 587).")
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "O e-mail ou a senha foram recusados. No Gmail use uma \"senha de app\", não a senha normal."
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "O e-mail de destino foi recusado. Confira o endereço de quem recebe."
    if isinstance(e, smtplib.SMTPSenderRefused):
        return "O e-mail de quem envia foi recusado pelo servidor."
    if isinstance(e, (socket.gaierror, ConnectionError)):
        return "Sem internet ou servidor de e-mail errado."
    if isinstance(e, (socket.timeout, TimeoutError)):
        return "O servidor de e-mail demorou demais para responder."
    if isinstance(e, ssl.SSLError):
        return "Falha de segurança na conexão. Confira a porta e o tipo de segurança (SSL ou STARTTLS)."
    if isinstance(e, FileNotFoundError):
        return "O arquivo do relatório não foi encontrado."
    if isinstance(e, smtplib.SMTPException):
        return "O servidor de e-mail recusou o envio (%s)." % e.__class__.__name__
    return "Não consegui enviar o e-mail (%s)." % e.__class__.__name__
