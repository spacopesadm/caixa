# -*- coding: utf-8 -*-
"""
Servidor da rede local (Wi-Fi da loja).

O celular (app Android) fala direto com o computador do caixa, sem internet:
- serve a mesma página do líder/funcionário (pasta lider/);
- imita o pedaço do Firebase que a página usa (/lojas/<codigo>/...), então a página funciona igual;
- /ping.json  : o app do celular acha o computador na rede;
- /parear     : troca o PIN de 6 dígitos pelo código da loja (celular novo);
- /avisos.json: fila de avisos para o celular tocar/vibrar.

Roda em thread de fundo. Nunca mexe no Tk: fala com o programa pela fila cmd_q.
"""
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

PORTA_LOCAL = int(os.environ.get("CAIXA_PORTA_LOCAL", "8765"))
TIPOS = {".html": "text/html; charset=utf-8", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml",
         ".png": "image/png", ".js": "text/javascript", ".json": "application/json"}


def pasta_pagina():
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "lider")


def ip_local():
    """IP deste computador na rede (para o endereço do celular)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


class Local:
    def __init__(self, get_cfg, cmd_q, log=lambda m: None, porta=None):
        self.get_cfg = get_cfg
        self.cmd_q = cmd_q
        self.log = log
        self.lock = threading.Lock()
        self.snap = None
        self.dia = ""
        self.val = {}                 # dia -> {chave: validação}
        self.avisos = []              # (id, titulo, texto, prio, ts)
        self.seq = 0
        self.erros_pin = []           # horários das tentativas erradas
        self.httpd = None
        self.porta = 0
        self.erro = ""
        for p in range(porta or PORTA_LOCAL, (porta or PORTA_LOCAL) + 10):
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", p), self._handler())
                self.porta = p
                break
            except OSError as e:
                self.erro = str(e)
        if self.httpd:
            self.erro = ""
            threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    # ----- chamadas pelo app
    def definir(self, dia, snap):
        with self.lock:
            self.dia, self.snap = dia, snap

    def avisar(self, titulo, texto, prio=3):
        with self.lock:
            self.seq += 1
            self.avisos.append((self.seq, titulo, texto, prio, int(time.time() * 1000)))
            self.avisos = self.avisos[-40:]

    def sair(self):
        try:
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception:
            pass

    def endereco(self):
        ip = ip_local()
        return "http://%s:%d" % (ip, self.porta) if ip and self.porta else ""

    # ----- dados
    def codigo(self):
        c = self.get_cfg()
        return (c.get("nuvem_codigo") or c.get("local_codigo") or "").strip()

    def _meta(self):
        c = self.get_cfg()
        with self.lock:
            snap, dia = self.snap, self.dia
        meta = {"ultimo": dia or time.strftime("%Y-%m-%d"), "atualizado": int(time.time() * 1000),
                "loja": (snap or {}).get("loja", c.get("nome_loja", ""))}
        pin = str(c.get("pin_lider") or "").strip()
        if pin:
            import hashlib
            meta["pin"] = hashlib.sha256((pin + self.codigo()).encode()).hexdigest()
        return meta

    def _handler(self):
        srv = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _enviar(self, codigo, corpo, tipo="application/json; charset=utf-8"):
                if not isinstance(corpo, (bytes, bytearray)):
                    corpo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(corpo)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(corpo)

            def do_OPTIONS(self):
                self._enviar(204, b"")

            def _corpo(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n > 20000:
                    return None
                try:
                    return json.loads(self.rfile.read(n).decode("utf-8") or "null")
                except Exception:
                    return None

            def _caminho(self):
                u = urlparse(self.path)
                return unquote(u.path), parse_qs(u.query)

            def do_GET(self):
                try:
                    self._get()
                except Exception as e:
                    srv.log("local GET: %r" % (e,))
                    try:
                        self._enviar(500, {"erro": "interno"})
                    except Exception:
                        pass

            def do_PUT(self):
                try:
                    self._put()
                except Exception as e:
                    srv.log("local PUT: %r" % (e,))
                    try:
                        self._enviar(500, {"erro": "interno"})
                    except Exception:
                        pass

            do_POST = do_PUT

            def _get(self):
                p, q = self._caminho()
                if p == "/ping.json":
                    c = srv.get_cfg()
                    return self._enviar(200, {"caixa": 1, "loja": c.get("nome_loja", "")})
                if p.startswith("/lojas/"):
                    partes = p[1:].split("/")
                    if len(partes) < 3 or partes[1] != srv.codigo() or not srv.codigo():
                        return self._enviar(403, {"erro": "codigo"})
                    rest = "/".join(partes[2:])
                    if rest.endswith(".json"):
                        rest = rest[:-5]
                    return self._dados(rest, q)
                nome = "index.html" if p in ("/", "") else p.lstrip("/")
                if "/" in nome or "\\" in nome or nome.startswith("."):
                    return self._enviar(404, {"erro": "nao"})
                arq = os.path.join(pasta_pagina(), nome)
                if not os.path.isfile(arq):
                    return self._enviar(404, {"erro": "nao"})
                with open(arq, "rb") as f:
                    return self._enviar(200, f.read(), TIPOS.get(os.path.splitext(nome)[1], "application/octet-stream"))

            def _dados(self, rest, q):
                if rest == "meta":
                    return self._enviar(200, srv._meta())
                if rest == "avisos":
                    try:
                        desde = int((q.get("desde") or ["0"])[0])
                    except ValueError:
                        desde = 0
                    with srv.lock:
                        itens = [{"id": a[0], "titulo": a[1], "texto": a[2], "prio": a[3], "ts": a[4]} for a in srv.avisos if a[0] > desde]
                        ultimo = srv.seq
                    return self._enviar(200, {"ultimo": ultimo, "itens": itens})
                if rest == "dias":
                    with srv.lock:
                        return self._enviar(200, {srv.dia: True} if srv.dia else None)
                if rest.startswith("dias/"):
                    with srv.lock:
                        return self._enviar(200, srv.snap if rest[5:] == srv.dia else None)
                if rest.startswith("validacoes/"):
                    with srv.lock:
                        return self._enviar(200, srv.val.get(rest[11:]) or None)
                return self._enviar(200, None)

            def _put(self):
                p, q = self._caminho()
                if p == "/parear":
                    return self._parear()
                if not p.startswith("/lojas/"):
                    return self._enviar(404, {"erro": "nao"})
                partes = p[1:].split("/")
                if len(partes) < 4 or partes[1] != srv.codigo() or not srv.codigo():
                    return self._enviar(403, {"erro": "codigo"})
                rest = "/".join(partes[2:])
                if rest.endswith(".json"):
                    rest = rest[:-5]
                corpo = self._corpo()
                if not isinstance(corpo, dict):
                    return self._enviar(400, {"erro": "corpo"})
                sp = rest.split("/")
                if sp[0] == "pedidos" and len(sp) == 3:
                    srv.cmd_q.put(("pedidos", sp[1], {sp[2]: corpo}))
                    return self._enviar(200, corpo)
                if sp[0] == "validacoes" and len(sp) == 3:
                    with srv.lock:
                        srv.val.setdefault(sp[1], {})[sp[2]] = corpo
                    srv.cmd_q.put(("validacoes", sp[1], {sp[2]: corpo}))
                    return self._enviar(200, corpo)
                return self._enviar(404, {"erro": "nao"})

            def _parear(self):
                agora = time.time()
                srv.erros_pin = [t for t in srv.erros_pin if agora - t < 60]
                if len(srv.erros_pin) >= 5:
                    return self._enviar(429, {"erro": "muitas tentativas"})
                corpo = self._corpo() or {}
                pin = str(corpo.get("pin", "")).strip()
                certo = str(srv.get_cfg().get("local_pin") or "").strip()
                if not certo or pin != certo:
                    srv.erros_pin.append(agora)
                    return self._enviar(403, {"erro": "pin"})
                return self._enviar(200, {"codigo": srv.codigo(), "loja": srv.get_cfg().get("nome_loja", "")})

        return H
