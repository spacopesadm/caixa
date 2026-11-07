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
import hashlib
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request

NTFY = "https://ntfy.sh/"


ALFABETO = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"     # sem 0/O, 1/I/L para não confundir


def novo_codigo():
    """Código secreto da loja (parte do endereço no banco). Quem não tem o código não acha os dados."""
    return "".join(secrets.choice(ALFABETO) for _ in range(24))


def normalizar_codigo(txt):
    t = re.sub(r"[\s-]", "", str(txt or ""))
    return t.upper() if len(t) == 24 else t


def formatar_codigo(c):
    c = str(c or "")
    return "-".join(c[i:i + 4] for i in range(0, len(c), 4)) if len(c) == 24 else c


def topico(codigo):
    """Tópico do ntfy derivado do código (o líder recebe o endereço pela própria página)."""
    return "caixa-" + hashlib.sha1(("ntfy" + str(codigo)).encode()).hexdigest()[:16]


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


def verificar_loja(url, codigo):
    """Devolve os dados da loja (meta) se o código existir, senão None. Levanta exceção se não conseguir falar com o Firebase."""
    url, codigo = (url or "").strip().rstrip("/"), (codigo or "").strip()
    return _req("GET", "%s/lojas/%s/meta.json" % (url, codigo))


def testar_ntfy(topico):
    _req("POST", NTFY, {"topic": topico.strip(), "title": "Painel do Caixa", "message": "Teste: se você recebeu isto, os avisos funcionam.",
                        "priority": 3, "tags": ["white_check_mark"]}, timeout=10)


class Nuvem:
    """Thread de fundo. Envia o estado e recebe o que os outros computadores e o líder fizeram."""

    def __init__(self, get_cfg, cmd_q, log=lambda m: None, intervalo=5):
        self.get_cfg = get_cfg
        self.cmd_q = cmd_q
        self.log = log
        self.intervalo = intervalo
        self.lock = threading.Lock()
        self.pend = None            # (dia, snapshot do líder) mais recente ainda não enviado
        self.escritas = []          # [(caminho, valor)] a gravar (estado compartilhado entre computadores)
        self.avisos = []            # fila de avisos para o celular
        self.visto = {}             # validações já entregues ao app
        self.ultimo = {}            # última resposta de cada leitura (só avisa o app quando muda)
        self.ev = threading.Event()
        self.parar = False
        self.ultimo_erro = ""
        self.ultimo_ok = 0
        self.ciclos = 0
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    # ----- chamadas pelo app (thread principal)
    def ativo(self):
        c = self.get_cfg()
        return bool((c.get("nuvem_url") or "").strip() and (c.get("nuvem_codigo") or "").strip())

    def enviar(self, dia, snapshot):
        with self.lock:
            self.pend = (dia, snapshot)
        self.ev.set()

    def escrever(self, itens):
        if not itens:
            return
        with self.lock:
            self.escritas.extend(itens)
        self.ev.set()

    def avisar(self, titulo, texto, prioridade=3):
        c = self.get_cfg()
        if not (c.get("ntfy_ativo") and (c.get("nuvem_codigo") or "").strip()):
            return
        with self.lock:
            self.avisos.append((titulo, texto, prioridade))
            self.avisos = self.avisos[-20:]
        self.ev.set()

    def sair(self):
        self.parar = True
        self.ev.set()

    def confirmar(self, novas):
        for k, v in novas.items():
            self.visto[k] = v.get("ts")

    # ----- thread de fundo
    def _base(self):
        c = self.get_cfg()
        return "%s/lojas/%s" % ((c.get("nuvem_url") or "").strip().rstrip("/"), (c.get("nuvem_codigo") or "").strip())

    def _loop(self):
        while not self.parar:
            self.ev.wait(timeout=self.intervalo)
            self.ev.clear()
            if self.parar:
                return
            try:
                self._ciclo()
            except Exception as e:
                self.ultimo_erro = erro_amigavel(e)
                self.log("nuvem: %r" % (e,))
                time.sleep(3)

    def _novo(self, nome, valor):
        """True se a leitura mudou desde a última vez."""
        txt = json.dumps(valor, sort_keys=True)
        if self.ultimo.get(nome) == txt:
            return False
        self.ultimo[nome] = txt
        return True

    def _ciclo(self):
        c = self.get_cfg()
        # avisos para o celular
        while True:
            with self.lock:
                if not self.avisos:
                    break
                titulo, texto, prio = self.avisos[0]
            try:
                _req("POST", NTFY, {"topic": topico(c.get("nuvem_codigo", "")), "title": titulo, "message": texto,
                                    "priority": prio, "tags": ["bell"]}, timeout=10)
            except Exception as e:
                self.log("ntfy: %r" % (e,))
            with self.lock:
                if self.avisos:
                    self.avisos.pop(0)
        if not self.ativo():
            return
        self.ciclos += 1
        base = self._base()
        dia = time.strftime("%Y-%m-%d")
        # gravações do estado compartilhado
        while True:
            with self.lock:
                if not self.escritas:
                    break
                caminho, valor = self.escritas[0]
            _req("PUT", "%s/%s.json" % (base, caminho), valor)
            with self.lock:
                if self.escritas:
                    self.escritas.pop(0)
        # painel do líder
        with self.lock:
            pend, self.pend = self.pend, None
        if pend:
            d, snap = pend
            try:
                _req("PUT", "%s/dias/%s.json" % (base, d), snap)
                meta = {"ultimo": d, "atualizado": int(time.time() * 1000), "loja": snap.get("loja", "")}
                if c.get("ntfy_ativo"):
                    meta["ntfy"] = topico(c.get("nuvem_codigo", ""))
                _req("PATCH", base + "/meta.json", meta)
            except Exception:
                with self.lock:
                    if self.pend is None:
                        self.pend = pend
                raise
        # presença deste computador (para decidir qual deles gera o relatório)
        maq = (c.get("maquina_id") or "").strip()
        if maq and self.ciclos % 6 == 1:
            _req("PUT", "%s/maquinas/%s.json" % (base, maq), {"ts": int(time.time() * 1000), "nome": c.get("maquina_nome", "")})
        # leituras
        estado = _req("GET", "%s/estado/%s.json" % (base, dia)) or {}
        maquinas = _req("GET", base + "/maquinas.json") if self.ciclos % 3 == 1 else None
        if self._novo("estado", estado) or (maquinas is not None and self._novo("maquinas", maquinas)):
            self.cmd_q.put(("remoto", dia, estado, maquinas if maquinas is not None else json.loads(self.ultimo.get("maquinas", "{}") or "{}")))
        if self.ciclos % 6 == 1:
            cfg_r = _req("GET", base + "/config.json")
            if cfg_r and self._novo("config", cfg_r):
                self.cmd_q.put(("config_remota", cfg_r))
        val = _req("GET", "%s/validacoes/%s.json" % (base, dia)) or {}
        novas = {k: v for k, v in val.items() if isinstance(v, dict) and self.visto.get(k) != v.get("ts")}
        if novas:
            self.cmd_q.put(("validacoes", dia, novas))
        self.ultimo_ok = time.time()
        self.ultimo_erro = ""
