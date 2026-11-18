# -*- coding: utf-8 -*-
"""
Servidor da rede local (Wi-Fi/cabo da loja).

O computador principal da loja guarda os dados e os outros computadores e os celulares conversam com ele, sem internet:
- imita o Firebase (árvore /lojas/<codigo>/...), então os outros computadores usam o mesmo código de sincronização de sempre;
- serve a página do líder/funcionário/entregas (pasta lider/);
- /ping.json  : os outros aparelhos acham o computador principal na rede;
- /parear     : troca o PIN de 6 dígitos pelo código da loja;
- /lojas/<codigo>/avisos.json: fila de avisos para o celular tocar/vibrar.

Roda em thread de fundo. Nunca mexe no Tk: fala com o programa pela fila cmd_q.
"""
import hashlib
import json
import os
import socket
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

PORTA_LOCAL = int(os.environ.get("CAIXA_PORTA_LOCAL", "8765"))
TIPOS = {".html": "text/html; charset=utf-8", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml",
         ".png": "image/png", ".js": "text/javascript", ".json": "application/json"}
SO_DIAS = ("estado", "dias", "pedidos", "validacoes")        # sub-árvores por dia (AAAA-MM-DD): guardamos só as últimas semanas


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


def _http(metodo, url, corpo=None, timeout=4):
    dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
    r = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        txt = resp.read().decode("utf-8")
    return json.loads(txt) if txt else None


def descobrir(codigo="", porta=PORTA_LOCAL, extra=()):
    """Procura o computador principal na rede (testa os endereços da mesma faixa). Com o código da loja, só aceita a mesma loja."""
    ip = ip_local()
    alvos = list(extra)
    if ip:
        pre = ".".join(ip.split(".")[:3]) + "."
        alvos += [pre + str(n) for n in range(1, 255) if pre + str(n) != ip]

    def testa(a):
        host = a if ":" in a else "%s:%d" % (a, porta)
        try:
            r = _http("GET", "http://%s/ping.json" % host, timeout=0.8)
            if not (r and r.get("caixa") and r.get("servidor")):
                return None
            if codigo:
                _http("GET", "http://%s/lojas/%s/meta.json" % (host, codigo), timeout=2)
            return host
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=64) as ex:
        return [h for h in ex.map(testa, alvos) if h]


def parear(host, pin):
    """Troca o PIN pelo código da loja. Devolve (codigo, nome_da_loja) ou levanta ValueError com a mensagem para o usuário."""
    import urllib.error
    try:
        r = _http("POST", "http://%s/parear" % host, {"pin": str(pin).strip()}, timeout=6)
        return r["codigo"], r.get("loja", "")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise ValueError("PIN incorreto. Veja o PIN no computador principal: Configurações > Rede da loja.")
        if e.code == 429:
            raise ValueError("Muitas tentativas. Espere 1 minuto.")
        raise ValueError("O computador principal respondeu com erro %d." % e.code)
    except Exception:
        raise ValueError("Não consegui falar com o computador principal (%s). Ele está ligado, com o programa aberto?" % host)


class Local:
    def __init__(self, get_cfg, cmd_q, log=lambda m: None, porta=None, arquivo=None):
        self.get_cfg = get_cfg
        self.cmd_q = cmd_q
        self.log = log
        self.lock = threading.Lock()
        self.arvore = {}              # tudo que fica em /lojas/<codigo>/
        self.arquivo = arquivo
        self.sujo = False
        self.avisos = []              # (id, titulo, texto, prio, ts)
        self.seq = 0
        self.erros_pin = []
        self.httpd = None
        self.porta = 0
        self.erro = ""
        self.parar = False
        self._carregar()
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
            threading.Thread(target=self._salvar_loop, daemon=True).start()

    # ----- persistência (se o programa fechar, os outros computadores continuam de onde pararam)
    def _carregar(self):
        try:
            if self.arquivo and os.path.isfile(self.arquivo):
                with open(self.arquivo, encoding="utf-8") as f:
                    self.arvore = json.load(f)
        except Exception:
            self.arvore = {}
        self._podar()

    def _podar(self):
        corte = time.strftime("%Y-%m-%d", time.localtime(time.time() - 14 * 86400))
        for k in SO_DIAS:
            sub = self.arvore.get(k)
            if isinstance(sub, dict):
                for d in [d for d in sub if isinstance(d, str) and len(d) == 10 and d < corte]:
                    del sub[d]

    def _salvar_loop(self):
        while not self.parar:
            time.sleep(5)
            if self.sujo and self.arquivo:
                try:
                    with self.lock:
                        self.sujo = False
                        self._podar()
                        txt = json.dumps(self.arvore, ensure_ascii=False)
                    tmp = self.arquivo + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write(txt)
                    os.replace(tmp, self.arquivo)
                except Exception as e:
                    self.log("rede local: salvar: %r" % (e,))

    # ----- chamadas pelo app
    def avisar(self, titulo, texto, prio=3):
        with self.lock:
            self.seq += 1
            self.avisos.append((self.seq, titulo, texto, prio, int(time.time() * 1000)))
            self.avisos = self.avisos[-40:]

    def sair(self):
        self.parar = True
        try:
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception:
            pass

    def endereco(self):
        ip = ip_local()
        return "http://%s:%d" % (ip, self.porta) if ip and self.porta else ""

    def url_local(self):
        return "http://127.0.0.1:%d" % self.porta

    def codigo(self):
        """Código da rede local (estável, não muda se a loja também usar a internet)."""
        return (self.get_cfg().get("local_codigo") or "").strip()

    def codigos(self):
        c = self.get_cfg()
        return {x for x in ((c.get("local_codigo") or "").strip(), (c.get("nuvem_codigo") or "").strip()) if x}

    # ----- árvore (parecida com o Firebase)
    def _no(self, caminho, criar=False):
        no = self.arvore
        for k in [x for x in caminho.split("/") if x]:
            if not isinstance(no, dict):
                return None
            if k not in no:
                if not criar:
                    return None
                no[k] = {}
            no = no[k]
        return no

    def ler(self, caminho):
        with self.lock:
            return json.loads(json.dumps(self._no(caminho)))

    def gravar(self, caminho, valor):
        partes = [x for x in caminho.split("/") if x]
        if not partes:
            return
        with self.lock:
            pai = self._no("/".join(partes[:-1]), criar=valor is not None)
            if isinstance(pai, dict):
                if valor is None:
                    pai.pop(partes[-1], None)
                else:
                    pai[partes[-1]] = valor
                self.sujo = True

    def mesclar(self, caminho, dados):
        for k, v in dados.items():
            self.gravar("%s/%s" % (caminho, k), v)

    def _meta(self, codigo):
        c = self.get_cfg()
        meta = dict(self.ler("meta") or {})
        meta.setdefault("ultimo", time.strftime("%Y-%m-%d"))
        meta.setdefault("loja", c.get("nome_loja", ""))
        pin = str(c.get("pin_lider") or "").strip()
        meta.pop("pin", None)
        if pin:
            meta["pin"] = hashlib.sha256((pin + codigo).encode()).hexdigest()
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
                self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, PATCH, DELETE, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(corpo)

            def do_OPTIONS(self):
                self._enviar(204, b"")

            def _corpo(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n > 400000:
                    return None
                try:
                    return json.loads(self.rfile.read(n).decode("utf-8") or "null")
                except Exception:
                    return None

            def _caminho(self):
                u = urlparse(self.path)
                return unquote(u.path), parse_qs(u.query)

            def _seguro(self, f):
                try:
                    f()
                except Exception as e:
                    srv.log("rede local: %r" % (e,))
                    try:
                        self._enviar(500, {"erro": "interno"})
                    except Exception:
                        pass

            def do_GET(self):
                self._seguro(self._get)

            def do_PUT(self):
                self._seguro(self._escrever)

            do_POST = do_PUT
            do_PATCH = do_PUT

            def do_DELETE(self):
                self._seguro(self._escrever)

            def _loja(self, p):
                """Valida /lojas/<codigo>/... e devolve (codigo, resto sem .json) ou None."""
                partes = p[1:].split("/")
                if len(partes) < 3 or partes[1] not in srv.codigos():
                    self._enviar(403, {"erro": "codigo"})
                    return None
                rest = "/".join(partes[2:])
                if rest.endswith(".json"):
                    rest = rest[:-5]
                return partes[1], rest

            def _get(self):
                p, q = self._caminho()
                if p == "/ping.json":
                    return self._enviar(200, {"caixa": 1, "servidor": 1, "loja": srv.get_cfg().get("nome_loja", "")})
                if p.startswith("/lojas/"):
                    r = self._loja(p)
                    if r is None:
                        return
                    cod, rest = r
                    if rest == "meta":
                        return self._enviar(200, srv._meta(cod))
                    if rest == "avisos":
                        try:
                            desde = int((q.get("desde") or ["0"])[0])
                        except ValueError:
                            desde = 0
                        with srv.lock:
                            itens = [{"id": a[0], "titulo": a[1], "texto": a[2], "prio": a[3], "ts": a[4]} for a in srv.avisos if a[0] > desde]
                            ultimo = srv.seq
                        return self._enviar(200, {"ultimo": ultimo, "itens": itens})
                    v = srv.ler(rest)
                    if (q.get("shallow") or [""])[0] == "true" and isinstance(v, dict):
                        v = {k: True for k in v}
                    return self._enviar(200, v)
                nome = "index.html" if p in ("/", "") else p.lstrip("/")
                if "/" in nome or "\\" in nome or nome.startswith("."):
                    return self._enviar(404, {"erro": "nao"})
                arq = os.path.join(pasta_pagina(), nome)
                if not os.path.isfile(arq):
                    return self._enviar(404, {"erro": "nao"})
                with open(arq, "rb") as f:
                    return self._enviar(200, f.read(), TIPOS.get(os.path.splitext(nome)[1], "application/octet-stream"))

            def _escrever(self):
                p, q = self._caminho()
                if p == "/parear":
                    return self._parear()
                if not p.startswith("/lojas/"):
                    return self._enviar(404, {"erro": "nao"})
                r = self._loja(p)
                if r is None:
                    return
                _, rest = r
                if not rest or rest.split("/")[0] == "avisos":
                    return self._enviar(400, {"erro": "caminho"})
                metodo = self.command
                if metodo == "DELETE":
                    srv.gravar(rest, None)
                    return self._enviar(200, None)
                corpo = self._corpo()
                if metodo == "PATCH":
                    if not isinstance(corpo, dict):
                        return self._enviar(400, {"erro": "corpo"})
                    srv.mesclar(rest, corpo)
                else:
                    srv.gravar(rest, corpo)
                sp = rest.split("/")
                if len(sp) == 3 and isinstance(corpo, dict):        # o programa deste computador recebe na hora
                    if sp[0] == "pedidos":
                        srv.cmd_q.put(("pedidos", sp[1], {sp[2]: corpo}))
                    elif sp[0] == "validacoes":
                        srv.cmd_q.put(("validacoes", sp[1], {sp[2]: corpo}))
                return self._enviar(200, corpo)

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
