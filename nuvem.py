# -*- coding: utf-8 -*-
"""
Sincronização com a nuvem (Firebase Realtime Database via REST) e avisos no celular (ntfy).

- O app do caixa envia o estado do dia (tarefas feitas, atrasos, pendências, pontos).
- A página do líder (celular ou PC) mostra isso ao vivo e grava a validação de cada tarefa.
- O app do caixa lê as validações e tira os pontos de tarefas que o líder marcou como "não feita".
- Avisos urgentes vão para o celular do líder pelo app ntfy (grátis, sem conta).

Tudo roda em uma thread de fundo: se a internet cair, o app do caixa continua normal e envia depois.
Nunca mexe na interface (Tk): fala com o app pela fila cmd_q.
"""
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request

NTFY = "https://ntfy.sh/"


def novo_codigo():
    """Código secreto da loja (vira parte do endereço no banco). Quem não tem o código não acha os dados."""
    return secrets.token_urlsafe(24).replace("_", "x").replace("-", "y")[:32]


def chave(texto):
    """Chaves do Firebase não aceitam . $ # [ ] /"""
    return re.sub(r"[^A-Za-z0-9_-]", "-", str(texto))


def chave_tarefa(tipo, id_, feito):
    return "%s_%s_%d" % (chave(tipo), chave(id_), int(feito))


def link_lider(cfg):
    base = (cfg.get("lider_url") or "").strip()
    url = (cfg.get("nuvem_url") or "").strip().rstrip("/")
    cod = (cfg.get("nuvem_codigo") or "").strip()
    if not (base and url and cod):
        return ""
    return "%s#u=%s&t=%s" % (base.split("#")[0], url, cod)


def _req(metodo, url, dados=None, timeout=15):
    corpo = None if dados is None else json.dumps(dados, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(url, data=corpo, method=metodo, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        txt = resp.read().decode("utf-8")
    return json.loads(txt) if txt else None


def erro_amigavel(e):
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (401, 403):
            return "O Firebase recusou o acesso (401/403). Confira as regras do banco de dados (veja o passo a passo)."
        if e.code == 404:
            return "Endereço do Firebase não encontrado. Confira a URL do banco."
        return "O Firebase respondeu com erro %d." % e.code
    if isinstance(e, (urllib.error.URLError, OSError)):
        return "Sem internet ou endereço do Firebase errado."
    if isinstance(e, ValueError):
        return "Resposta inesperada. Confira se a URL é a do Realtime Database."
    return "Não consegui conectar (%s)." % e.__class__.__name__


def testar_conexao(url, codigo):
    """Grava e lê um valor de teste. Levanta exceção se não funcionar."""
    url, codigo = (url or "").strip().rstrip("/"), (codigo or "").strip()
    if not url.startswith("https://") or not codigo:
        raise ValueError("Preencha a URL do Firebase (começa com https://) e gere o código da loja.")
    base = "%s/lojas/%s" % (url, codigo)
    _req("PUT", base + "/teste.json", {"ts": int(time.time())})
    if not _req("GET", base + "/teste.json"):
        raise ValueError("vazio")


def testar_ntfy(topico):
    _req("POST", NTFY, {"topic": topico.strip(), "title": "Painel do Caixa", "message": "Teste: se você recebeu isto, os avisos funcionam.",
                        "priority": 3, "tags": ["white_check_mark"]}, timeout=10)


class Nuvem:
    def __init__(self, get_cfg, cmd_q, log=lambda m: None, intervalo=15):
        self.get_cfg = get_cfg
        self.cmd_q = cmd_q
        self.log = log
        self.intervalo = intervalo
        self.lock = threading.Lock()
        self.pend = None            # (dia, snapshot) mais recente ainda não enviado
        self.avisos = []            # fila de avisos para o celular
        self.visto = {}             # validações já entregues ao app: chave -> ts
        self.ev = threading.Event()
        self.parar = False
        self.ultimo_erro = ""
        self.ultimo_ok = 0
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    # ----- chamadas pelo app (thread principal)
    def ativo(self):
        c = self.get_cfg()
        return bool(c.get("nuvem_ativa") and (c.get("nuvem_url") or "").strip() and (c.get("nuvem_codigo") or "").strip())

    def enviar(self, dia, snapshot):
        with self.lock:
            self.pend = (dia, snapshot)
        self.ev.set()

    def avisar(self, titulo, texto, prioridade=3):
        c = self.get_cfg()
        if not (c.get("ntfy_ativo") and (c.get("ntfy_topico") or "").strip()):
            return
        with self.lock:
            self.avisos.append((titulo, texto, prioridade))
            self.avisos = self.avisos[-20:]
        self.ev.set()

    def sair(self):
        self.parar = True
        self.ev.set()

    # ----- thread de fundo
    def _base(self):
        c = self.get_cfg()
        return "%s/lojas/%s" % ((c.get("nuvem_url") or "").strip().rstrip("/"), (c.get("nuvem_codigo") or "").strip())

    def _loop(self):
        ultima_poll = 0
        while not self.parar:
            self.ev.wait(timeout=self.intervalo)
            self.ev.clear()
            if self.parar:
                return
            try:
                self._ciclo(time.time() - ultima_poll >= self.intervalo - 1)
                if time.time() - ultima_poll >= self.intervalo - 1:
                    ultima_poll = time.time()
            except Exception as e:
                self.ultimo_erro = erro_amigavel(e)
                self.log("nuvem: %r" % (e,))
                time.sleep(3)

    def _ciclo(self, ler):
        # avisos para o celular
        while True:
            with self.lock:
                if not self.avisos:
                    break
                titulo, texto, prio = self.avisos[0]
            c = self.get_cfg()
            try:
                _req("POST", NTFY, {"topic": (c.get("ntfy_topico") or "").strip(), "title": titulo, "message": texto,
                                    "priority": prio, "tags": ["bell"]}, timeout=10)
            except Exception as e:
                self.log("ntfy: %r" % (e,))
            with self.lock:
                if self.avisos:
                    self.avisos.pop(0)
        if not self.ativo():
            return
        base = self._base()
        with self.lock:
            pend, self.pend = self.pend, None
        if pend:
            dia, snap = pend
            try:
                _req("PUT", "%s/dias/%s.json" % (base, dia), snap)
                _req("PATCH", base + "/meta.json", {"ultimo": dia, "atualizado": int(time.time() * 1000),
                                                    "loja": snap.get("loja", "")})
            except Exception:
                with self.lock:                  # tenta de novo no próximo ciclo
                    if self.pend is None:
                        self.pend = pend
                raise
            self.ultimo_ok = time.time()
            self.ultimo_erro = ""
        if ler:
            dia = time.strftime("%Y-%m-%d")
            val = _req("GET", "%s/validacoes/%s.json" % (base, dia)) or {}
            novas = {k: v for k, v in val.items() if isinstance(v, dict) and self.visto.get(k) != v.get("ts")}
            if novas:
                self.cmd_q.put(("validacoes", dia, novas))
            self.ultimo_ok = time.time()
            self.ultimo_erro = ""

    def confirmar(self, novas):
        """O app avisa que já aplicou estas validações."""
        for k, v in novas.items():
            self.visto[k] = v.get("ts")
