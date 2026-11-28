# -*- coding: utf-8 -*-
"""
Painel do Caixa (Windows)
-------------------------
Fica oculto, inicia com o Windows e mostra avisos por cima de qualquer programa.
- Avisos aleatórios em 5 formatos diferentes (para não virar rotina).
- Pendências (caixa de hora em hora, conferências) voltam cada vez mais chamativas
  até serem marcadas como concluídas.
- Ícone perto do relógio do Windows para abrir o checklist, pausar avisos ou sair.

Para mudar textos e horários, edite o arquivo config.json (criado na primeira execução).
"""
import ctypes
import datetime as dt
import json
import math
import os
import queue
import re
import uuid
import random
import socket
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk

try:
    import winsound
except ImportError:  # fora do Windows
    winsound = None

try:
    import relatorio
except Exception:
    relatorio = None

try:
    import envio
except Exception:
    envio = None
try:
    import nuvem
except Exception:
    nuvem = None
try:
    import agenda
except Exception:
    agenda = None
import tema
try:
    import redelocal as rede_local
except Exception:
    rede_local = None

NUVEM_URL_PADRAO = "https://caixa-spaco-pes-default-rtdb.firebaseio.com"
LIDER_URL_PADRAO = "https://spacopesadm.github.io/caixa/"
PORTA = int(os.environ.get("CAIXA_PORTA", "47653"))
FROZEN = bool(getattr(sys, "frozen", False))      # True quando roda como PainelDoCaixa.exe
if FROZEN:
    BASE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PainelDoCaixa")   # dados ficam aqui
    try:
        os.makedirs(BASE, exist_ok=True)
    except OSError:
        BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("CAIXA_DADOS"):        # só para testes
    BASE = os.environ["CAIXA_DADOS"]
    os.makedirs(BASE, exist_ok=True)
CONFIG_FILE = os.path.join(BASE, "config.json")
STATE_FILE = os.path.join(BASE, "estado.json")
LOG_FILE = os.path.join(BASE, "erro.log")
PLACAR_FILE = os.path.join(BASE, "placar.json")
ENVIOS_FILE = os.path.join(BASE, "envios_pendentes.json")
AGENDA_FILE = os.path.join(BASE, "agenda.json")
IMPRESSOS_FILE = os.path.join(BASE, "impressos.json")
ARVORE_FILE = os.path.join(BASE, "rede_arvore.json")
PRAZO_MIN, LEVE_MIN = 5, 15          # até 5 min: no prazo; até 15 min: atraso leve
NIVEIS = [(0, "Aprendiz"), (100, "Dedicado"), (300, "Craque do Caixa"), (700, "Mestre do Caixa"), (1500, "Lenda da Loja")]

# ---------------------------------------------------------------- configuração
def _dia_padrao(aberto=True):
    return {"aberto": aberto, "ao_chegar": ["09:00", "10:30"], "tarde": ["13:00", "19:00"],
            "horas": [13, 14, 15, 16, 17, 18]}


DEFAULT_DIAS = {str(i): _dia_padrao(i != 6) for i in range(7)}   # 0 = segunda ... 6 = domingo (fechado)

DEFAULT_CONFIG = {
    "tema_nome": "Azul claro",
    "tema_cor1": "#EAF0FA",
    "tema_cor2": "#C9D9F2",
    "tema_degrade": "vertical",
    "aviso_aleatorio_min_minutos": 5,
    "aviso_aleatorio_max_minutos": 10,
    "pausa_atendimento_minutos": 4,
    "repetir_conferencia_minutos": 120,
    "adiar_minutos": 5,
    "escalonar_apos_minutos": [4, 8],
    "repetir_urgente_minutos": 3,
    "intervalo_entre_conferencias_minutos": 10,
    "som": True,
    "nome_loja": "",
    "nome_caixa": "",
    "pasta_relatorios": "",
    "gerar_relatorio_no_fim": True,
    "chance_aviso_alegre": 25,
    "mostrar_pontos": True,
    "pontos_no_prazo": 2,
    "pontos_atraso_leve": 1,
    "pontos_atrasado": 0,
    "bonus_combo_max": 0,
    "limite_pontos_conferencia_dia": 4,
    "versao_pontos": 2,
    "nuvem_url": NUVEM_URL_PADRAO,
    "nuvem_codigo": "",
    "lider_url": LIDER_URL_PADRAO,
    "ntfy_ativo": True,
    "pin_lider": "885682",
    "pin_padrao_v1": False,
    "maquina_id": "",
    "maquina_nome": "",
    "vendedores_entrega": [],
    "bairros_extra": [],
    "janelas_entrega": ["09:00-11:00", "12:00-13:00", "15:00-16:00", "18:00-19:00"],
    "dias_entrega": [0, 1, 2, 3, 4],
    "entrega_antes": 15,
    "impressora": "",
    "impressora_colunas": 48,
    "imprimir_auto": False,
    "modo_cliente": False,
    "local_ativo": True,
    "local_pin": "",
    "local_codigo": "",
    "cfg_rev": 0,
    "bonus_dia_completo": 5,
    "meta_semana_pontos": 150,
    "premio_semana": "Prêmio da semana: combine com o patrão!",
    "senha_config": "",
    "lembretes_fixos": [
        ["10:15", "Carregar a maquininha", "Confira a bateria da maquininha e, se precisar, coloque para carregar"],
        ["14:30", "Carregar a maquininha", "Maquininha com bateria? Aproveite um tempo livre e coloque para carregar"],
        ["18:30", "Maquininha para carregar", "Antes de fechar: deixe a maquininha carregando para amanhã"],
    ],
    "mensagens_alegres": [
        "Boa! Mais uma conferência em dia.",
        "Isso aí, continue assim!",
        "Feito! Obrigado pela atenção.",
        "Caixa em ordem. Parabéns!",
        "Mandou bem!",
        "Show! O patrão vai gostar.",
        "Muito bem, {nome}!",
        "Tarefa cumprida. Que capricho!",
        "Mais uma no bolso!",
        "É assim que se faz!",
        "Atenção de campeão!",
        "Perfeito! Pode seguir tranquilo.",
        "Orgulho de você!",
        "Mais um passo para a meta da semana!",
        "Que beleza de trabalho!",
        "Arrasou! Próxima!",
        "Isso é profissionalismo!",
        "Tudo certo por aqui. Valeu!",
    ],
    "mensagens_dia_completo": [
        "Parabéns! Você cumpriu todas as tarefas de hoje.",
        "Dia completo! Caixa em ordem e tudo conferido.",
        "Missão cumprida! Bom descanso e até amanhã.",
        "Que dia! Nada ficou para trás. Parabéns, {nome}!",
        "Tudo feito, tudo certo. A loja agradece!",
        "Você foi incrível hoje. Descanse, você merece!",
    ],
    "avisos_alegres": [
        "Seu sorriso muda o dia de quem chega na loja!",
        "Respire fundo, ombros para trás e sorria. Você está indo muito bem!",
        "Cliente bem atendido volta sempre. Você é o cartão de visitas da loja!",
        "Um minutinho para se alongar? Gire os ombros e estique o pescoço.",
        "Beba um golinho de água. Cuidar de você também faz parte do trabalho!",
        "Cada tarefa feita é uma preocupação a menos. Continue assim!",
        "Bom trabalho, {nome}! A loja agradece.",
        "Hoje está rendendo, hein? Orgulho de você!",
        "Pense em algo bom que aconteceu hoje e sorria por dentro.",
        "Quem atende com atenção vende com confiança!",
        "A equipe conta com você, e você pode contar com a equipe.",
        "Um cliente feliz é a melhor propaganda da loja. Capriche no sorriso!",
        "Pequenos cuidados, grandes resultados. Você está caprichando!",
        "Que tal um elogio sincero ao próximo cliente? Muda o clima da loja.",
        "Você faz diferença aqui. Obrigado pelo seu esforço!",
        "Ritmo bom! Mantenha o foco e a boa energia.",
        "Se o dia está corrido, respire: uma coisa de cada vez.",
        "Caixa em ordem, cabeça tranquila. Boa, {nome}!",
        "Seu cuidado com o dinheiro da loja é muito valorizado.",
        "Atenção hoje evita dor de cabeça amanhã. Você sabe disso!",
        "Mais um passo para a meta da semana. Vamos!",
        "Cada ponto conta. Você está construindo uma ótima semana!",
        "Pausa rápida: solte a mandíbula e os ombros. Pronto, melhor assim!",
        "Gentileza não custa nada e vale muito. Bom atendimento!",
        "Hoje é um ótimo dia para bater seu recorde de pontos!",
    ],
    "dias_semana": DEFAULT_DIAS,
    "excecoes": [],
    "funcionarios": [],
    "penalidade_ativa": True,
    "penalidade_pontos": 1,
    "penalidade_a_cada_minutos": 10,
    "penalidade_apos_minutos": 15,
    "penalidade_max_por_tarefa": 3,
    "penalidade_nao_feito": 2,
    "conferencia_espera_minutos": 30,
    "email_ativo": False,
    "email_servidor": "smtp.gmail.com",
    "email_porta": 465,
    "email_seguranca": "ssl",
    "email_usuario": "",
    "email_senha": "",
    "email_de": "",
    "email_para": "",
    "email_assunto": "Relatório do Caixa - {data}",
    "ao_chegar_horario": ["09:00", "10:30"],
    "tarde_horario": ["13:00", "19:00"],
    "horas_caixa": [13, 14, 15, 16, 17, 18],
    "ao_chegar": [
        ["pc", "Ligar o computador"],
        ["som", "Ligar o som e a TV"],
        ["caixa", "Conferir o caixa"],
        ["zap", "Olhar o WhatsApp"],
        ["prest", "Conferir as prestações"],
    ],
    "conferencias": [
        ["pix", "Conferir Pix de clientes", "Se for em outro banco, pergunte ao patrão ou ao gerente"],
        ["vendas", "Conferir vendas em aberto", "Vendas e condicional"],
        ["entregas", "Conferir entregas", ""],
        ["prom", "Conferir promissórias", ""],
    ],
    "durante_atendimento": [
        "Sorria para o cliente",
        "Confira os pares antes de entregar: pares trocados ou com defeito?",
        "Confirme com o cliente se é aquela mercadoria mesmo",
        "Antes de cobrar, confirme se a compra é mesmo desse cliente",
        "Atenção ao receber",
        "Atenção ao cobrar",
        "Confira o troco: do cliente e das compras da loja",
        "Confira as notas",
        "A caixa está suja? Limpe antes de entregar ao cliente",
    ],
    "quando_livre": [
        "Tem mercadoria para tirar etiquetas?",
        "Limpe o balcão e o caixa",
        "Caixa organizado? Sem promissórias ou papéis espalhados",
        "Cobrança em dia? Veja quem está atrasado",
        "Tem WhatsApp sem resposta?",
        "Sem cliente agora? Confira as entregas pendentes",
    ],
}

# cores
PINK, ORANGE, RED, BLUE = "#E0246F", "#E8730C", "#C8102E", "#1F46D1"
ROXO = "#6D28D9"          # entregas, condicionais e trocas: cor própria para chamar atenção
INK, PAPER, GREY, GREEN = "#14202E", "#FFFFFF", "#5B6878", "#13805A"
BG = "#E9EDF2"
FONT = "Segoe UI"


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        log("falha ao salvar " + path + "\n" + traceback.format_exc())


_BAIRROS = None


def bairros():
    """Tabela de bairros/zonas (lider/bairros.json), por nome em minúsculas."""
    global _BAIRROS
    if _BAIRROS is None:
        _BAIRROS = {}
        try:
            pasta = rede_local.pasta_pagina() if rede_local else os.path.join(os.path.dirname(os.path.abspath(__file__)), "lider")
            for b in load_json(os.path.join(pasta, "bairros.json"), {}).get("bairros", []):
                for nome in [b["bairro"]] + list(b.get("alias") or []):
                    _BAIRROS[agenda.chave_bairro(nome)] = b
        except Exception:
            pass
    return _BAIRROS


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    raw = load_json(CONFIG_FILE, {})
    if not isinstance(raw, dict):
        raw = {}
    cfg.update(raw)
    if not cfg.get("nuvem_url"):
        cfg["nuvem_url"] = NUVEM_URL_PADRAO
    if not cfg.get("lider_url"):
        cfg["lider_url"] = LIDER_URL_PADRAO
    if not cfg.get("maquina_id"):
        cfg["maquina_id"] = uuid.uuid4().hex[:10]
        cfg["maquina_nome"] = os.environ.get("COMPUTERNAME", "") or socket.gethostname()
        if raw:
            save_json(CONFIG_FILE, cfg)
    if not cfg.get("local_pin") or not cfg.get("local_codigo"):
        import secrets as _sec
        cfg["local_pin"] = cfg.get("local_pin") or "%06d" % _sec.randbelow(1000000)
        cfg["local_codigo"] = cfg.get("local_codigo") or "".join(_sec.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(24))
        if raw:
            save_json(CONFIG_FILE, cfg)
    if not raw.get("pin_padrao_v1"):
        cfg["pin_padrao_v1"] = True
        if not str(cfg.get("pin_lider") or "").strip():
            cfg["pin_lider"] = "885682"
        if raw:
            save_json(CONFIG_FILE, cfg)
    if raw.get("versao_pontos", 1) < 2:      # sistema de pontos antigo (valores altos e combo): troca pelo novo
        for k in ("pontos_no_prazo", "pontos_atraso_leve", "pontos_atrasado", "bonus_combo_max", "bonus_dia_completo",
                  "meta_semana_pontos", "penalidade_pontos", "penalidade_max_por_tarefa", "penalidade_nao_feito",
                  "limite_pontos_conferencia_dia", "versao_pontos"):
            cfg[k] = DEFAULT_CONFIG[k]
        if raw:
            save_json(CONFIG_FILE, cfg)
    if "dias_semana" not in raw:     # config de versão antiga: usa os horários antigos em todos os dias
        cfg["dias_semana"] = {str(i): {"aberto": i != 6, "ao_chegar": list(cfg["ao_chegar_horario"]),
                                       "tarde": list(cfg["tarde_horario"]), "horas": list(cfg["horas_caixa"])}
                              for i in range(7)}
    if not os.path.exists(CONFIG_FILE):
        save_json(CONFIG_FILE, cfg)
    return cfg


def today():
    return dt.date.today().isoformat()


def chave_log(e):
    """Identificador estável de uma tarefa feita (igual em todos os computadores e na página do líder)."""
    c = lambda t: re.sub(r"[^A-Za-z0-9_-]", "-", str(t))
    return "%s_%s_%d" % (c(e["k"]), c(e["id"]), int(e["done"]))


def fresh_state():
    return {"date": today(), "am": {}, "cx": {}, "last": {}, "shown": 0, "ok": 0,
            "log": [], "pausas": 0, "celebrado": False, "lem": {}, "pontos": 0, "combo": 0,
            "marco50": False, "bonus_dia": False, "val_vistas": {}, "rejeitadas": [], "bonus": {}, "removidas": [],
            "pts_func": {}, "penal": [], "func_manual": None, "relatorio_gerado": False, "sched": {}}


def load_state():
    st = load_json(STATE_FILE, None)
    if not isinstance(st, dict) or st.get("date") != today():
        st = fresh_state()
    for k, v in fresh_state().items():
        st.setdefault(k, v)
    return st


def hm_to_min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def hm(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%H:%M")


def ago_txt(seconds):
    n = max(0, int(seconds // 60))
    if n < 60:
        return "%d min" % n
    return "%d h %02d min" % (n // 60, n % 60)


def lembretes_cfg(cfg):
    """Lembretes fixos: (id, minuto, nome com hora, texto do aviso, nome curto)."""
    out = []
    for row in cfg.get("lembretes_fixos", []):
        try:
            hora, nome, texto = (list(row) + ["", ""])[:3]
            hora = hora.strip()
            out.append(("lem" + hora.replace(":", ""), hm_to_min(hora), "%s (%s)" % (nome, hora), texto or nome, nome))
        except Exception:
            log("lembrete inválido: %r" % (row,))
    return out


def nivel_de(total):
    """Devolve (nível atual, próximo nível ou None, pontos que faltam)."""
    atual, prox, falta = NIVEIS[0][1], None, 0
    for i, (lim, nome) in enumerate(NIVEIS):
        if total >= lim:
            atual = nome
            if i + 1 < len(NIVEIS):
                prox, falta = NIVEIS[i + 1][1], NIVEIS[i + 1][0] - total
            else:
                prox, falta = None, 0
    return atual, prox, falta


# ---------------------------------------------------------------- janelas
def noactivate(win):
    """Faz a janela não roubar o foco do programa de vendas."""
    if sys.platform != "win32":
        return
    try:
        win.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x00000080
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:
        log("noactivate: " + traceback.format_exc())


def work_area(root):
    if sys.platform == "win32":
        try:
            import ctypes.wintypes as wt
            rect = wt.RECT()
            ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


class Pop:
    """Um aviso na tela (pode ter várias janelas, como a borda piscando)."""

    def __init__(self, app, win, w, h, corner, extra=None):
        self.app, self.win, self.w, self.h, self.corner = app, win, w, h, corner
        self.extra = extra or []
        self.after_id = None
        self.closed = False
        self.on_close = None

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.after_id:
            try:
                self.app.root.after_cancel(self.after_id)
            except Exception:
                pass
        for w in [self.win] + self.extra:
            try:
                w.destroy()
            except Exception:
                pass
        if self in self.app.pops:
            self.app.pops.remove(self)
        self.app.relayout()
        if self.on_close:
            self.on_close()


# ---------------------------------------------------------------- app
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Painel do Caixa")
        self.cfg = load_config()
        prev = load_json(STATE_FILE, None)      # dia anterior que ficou sem relatório (computador desligado)
        self.catchup = None
        if (isinstance(prev, dict) and prev.get("date") not in (None, today()) and not prev.get("relatorio_gerado")
                and (prev.get("log") or prev.get("shown"))):
            self.catchup = prev
        self.state = load_state()
        if not self.state.get("pts_func") and self.state.get("pontos"):
            self.state["pts_func"] = {"_": self.state["pontos"]}
        self.day_open = True
        self.envio_busy = False
        self.envio_lock = threading.Lock()
        self.apply_day()
        self.pops = []
        self.pend = {}          # pendências abertas
        self.fired = set()
        self.conf_gate_until = 0
        self.recent = []
        self.queue_hold = []
        self.last_shown = 0
        self.last_fmt = None
        self.last_min = -1
        self.hold_until = 0
        self.cmd_q = queue.Queue()
        self.nuvem = None
        self.ov = None            # marcação feita pelo celular: horário e funcionário reais
        self.enviado = set()
        self.maquinas = {}
        self.fim_alvo = None
        self.snap_agendado = False
        try:
            if nuvem is not None:
                self.nuvem = nuvem.Nuvem(lambda: self.cfg, self.cmd_q, log)
        except Exception:
            log("nuvem: " + traceback.format_exc())
        self.agenda = []
        self.ag_est = {}          # estado dos avisos da agenda neste computador: id -> {next, pre, n, pop}
        self.ag_win = None
        self.impressos = set(load_json(IMPRESSOS_FILE, []))
        try:
            if agenda is not None:
                self.agenda = agenda.limpar(agenda.mesclar([], load_json(AGENDA_FILE, [])))
        except Exception:
            log("agenda: " + traceback.format_exc())
        self.local = None
        self.bridge = False
        self.redescobrindo = False
        try:
            if rede_local is not None and self.cfg.get("local_ativo", True) and not self.cfg.get("modo_cliente"):
                self.local = rede_local.Local(lambda: self.cfg, self.cmd_q, log, arquivo=ARVORE_FILE)
                if self.local.erro:
                    log("rede local: " + self.local.erro)
                elif nuvem is not None:
                    # computador principal: também sincroniza com a própria rede da loja (os outros computadores e os celulares falam com ele)
                    lan = nuvem.Nuvem(lambda: dict(self.cfg, nuvem_url=self.local.url_local(), nuvem_codigo=self.local.codigo(), ntfy_ativo=False),
                                      self.cmd_q, log, intervalo=3)
                    self.nuvem = nuvem.Multi([self.nuvem, lan])
                    self.bridge = True
                    threading.Timer(2.0, self.empurrar_config_forte).start()      # os computadores que se conectarem recebem estas configurações
        except Exception:
            log("rede local: " + traceback.format_exc())
        self.win = None
        self.w = {}
        self.tray = None
        self.settings_win = None
        self.last_award = None
        self.defaults = json.loads(json.dumps(DEFAULT_CONFIG))
        self.placar = load_json(PLACAR_FILE, {})
        if not isinstance(self.placar, dict):
            self.placar = {}
        self.placar.setdefault("dias", {})
        self.placar.setdefault("premios", {})
        self.next_random = self.sched_random()
        self.start_tray()
        self.root.after(1000, self.tick)
        self.root.after(8000, self.startup_tasks)
        self.root.after(1500, self.primeira_execucao)
        self.root.after(3000, self.push_snapshot)

    # ---- tempo / fases
    def ranges(self):
        a = [hm_to_min(x) for x in self.cfg["ao_chegar_horario"]]
        p = [hm_to_min(x) for x in self.cfg["tarde_horario"]]
        return a, p

    def phase(self, m):
        if not self.day_open:
            return "closed"
        a, p = self.ranges()
        if m < a[0]:
            return "pre"
        if m < a[1]:
            return "am"
        if m < p[0]:
            return "lunch"
        if m < p[1]:
            return "pm"
        return "end"

    def in_work(self, m):
        return self.phase(m) in ("am", "pm")

    def holding(self):
        return time.time() < self.hold_until

    def save(self):
        save_json(STATE_FILE, self.state)
        self.sync_soon()

    # ---- nuvem: líder vê as tarefas ao vivo e valida
    def sync_soon(self):
        if self.snap_agendado or not self.sync_ativo():
            return
        self.snap_agendado = True
        try:
            self.root.after(2500, self.push_snapshot)
        except Exception:
            self.snap_agendado = False

    def sync_ativo(self):
        return bool(self.local is not None or (self.nuvem is not None and self.nuvem.ativo()))

    def push_snapshot(self):
        self.snap_agendado = False
        if not self.sync_ativo():
            return
        try:
            snap = self.build_snapshot()
            if self.nuvem is not None and self.nuvem.ativo():
                self.nuvem.enviar(self.state["date"], snap)
                self.empurrar_estado()
        except Exception:
            log("snapshot: " + traceback.format_exc())

    # ---- vários computadores na mesma loja: cada um grava só o que é novo e lê o que os outros fizeram
    def empurrar_estado(self):
        st, dia = self.state, self.state["date"]
        base, itens, sent = "estado/%s" % dia, [], self.enviado

        def novo(chave, caminho, valor):
            if chave not in sent:
                sent.add(chave)
                itens.append((caminho, valor))
        for e in st["log"]:
            k = chave_log(e)
            novo(("log", dia, k), "%s/log/%s" % (base, k), e)
        for k in st.get("removidas", []):
            novo(("rm", dia, k), "%s/removidas/%s" % (base, k), True)
        for p in st.get("penal", []):
            if not p.get("id"):
                p["id"] = "p" + uuid.uuid4().hex[:10]
            novo(("pn", dia, p["id"]), "%s/penal/%s" % (base, p["id"]), p)
        for f, n in st.get("bonus", {}).items():
            novo(("bn", dia, f, n), "%s/bonus/%s" % (base, nuvem.chave(f)), n)
        for f in ("bonus_dia", "celebrado", "relatorio_gerado", "marco50"):
            if st.get(f):
                novo(("fl", dia, f), "%s/flags/%s" % (base, f), True)
        for r in st.get("rejeitadas", []):
            if r.get("key"):
                novo(("rj", dia, r["key"]), "%s/rejeitadas/%s" % (base, r["key"]), r)
        for k, t in st.get("val_vistas", {}).items():
            novo(("vv", dia, k), "%s/val/%s" % (base, k), t if t is not None else 0)
        self.nuvem.escrever(itens)

    def reflag(self):
        """Refaz os marcadores 'feito' (am/cx/lem/last) a partir do registro."""
        st = self.state
        bucket = {"am": "am", "cx": "cx", "lem": "lem", "conf": "last"}
        mx = {}
        for e in st["log"]:
            b = bucket.get(e["k"])
            if b:
                mx[(b, str(e["id"]))] = max(mx.get((b, str(e["id"])), 0), e["done"])
        for (b, i), t in mx.items():
            if (st[b].get(i) or 0) < t:
                st[b][i] = t
        inv = {v: k for k, v in bucket.items()}
        for b in ("am", "cx", "lem", "last"):
            for i, v in list(st[b].items()):
                if v and (b, str(i)) not in mx:
                    pref = "%s_%s_" % (inv[b], re.sub(r"[^A-Za-z0-9_-]", "-", str(i)))
                    if any(rk.startswith(pref) for rk in st.get("removidas", [])):
                        st[b][i] = 0

    def merge_remoto(self, dia, rem, maquinas):
        novo = dict(getattr(self, "maquinas", None) or {})
        for m, v in (maquinas or {}).items():          # juntando o que vem da rede da loja e da internet: vale a presença mais recente
            if isinstance(v, dict) and (m not in novo or float(v.get("ts", 0)) > float((novo[m] or {}).get("ts", 0))):
                novo[m] = v
        self.maquinas = novo
        if dia != self.state["date"] or not isinstance(rem, dict):
            return
        st, sent, mudou = self.state, self.enviado, False
        rm = st.setdefault("removidas", [])
        for k in (rem.get("removidas") or {}):
            if k not in rm:
                rm.append(k)
                mudou = True
            if not self.bridge:
                sent.add(("rm", dia, k))
        rms = set(rm)
        antes = len(st["log"])
        st["log"] = [e for e in st["log"] if chave_log(e) not in rms]
        mudou = mudou or len(st["log"]) != antes
        tem = {chave_log(e) for e in st["log"]}
        for k, e in (rem.get("log") or {}).items():
            if k in rms or k in tem or not isinstance(e, dict) or "k" not in e or "done" not in e:
                continue
            st["log"].append(e)
            if not self.bridge:
                sent.add(("log", dia, k))
            mudou = True
        st["log"].sort(key=lambda x: x["done"])
        ids = {p.get("id") for p in st.get("penal", [])}
        for i, p in (rem.get("penal") or {}).items():
            if isinstance(p, dict) and i not in ids:
                p.setdefault("id", i)
                st.setdefault("penal", []).append(p)
                if not self.bridge:
                    sent.add(("pn", dia, i))
                mudou = True
        for f, n in (rem.get("bonus") or {}).items():
            try:
                if int(n) > int(st["bonus"].get(f, 0)):
                    st["bonus"][f] = int(n)
                    mudou = True
            except Exception:
                pass
        gerado_antes = bool(st.get("relatorio_gerado"))
        for f in (rem.get("flags") or {}):
            if f in ("bonus_dia", "celebrado", "relatorio_gerado", "marco50") and not st.get(f):
                st[f] = True
                mudou = True
        rj = st.setdefault("rejeitadas", [])
        for k, r in (rem.get("rejeitadas") or {}).items():
            if isinstance(r, dict) and not any(x.get("key") == k for x in rj):
                r.setdefault("key", k)
                rj.append(r)
                mudou = True
        for k, t in (rem.get("val") or {}).items():
            if k not in st["val_vistas"]:
                st["val_vistas"][k] = t
                mudou = True
        if not mudou:
            return
        self.reflag()
        self.recalc_points()
        self.update_placar()
        if st.get("relatorio_gerado") and not gerado_antes:      # outro computador já fechou o dia
            for pid, p in list(self.pend.items()):
                self.close_pending_pop(p)
                self.pend.pop(pid, None)
        save_json(STATE_FILE, st)
        self.refresh()
        self.sync_soon()

    # ---- ligar este computador a uma loja (primeiro computador cria; os outros entram com o código)
    def conectar_loja(self, codigo, criar):
        self.cfg["nuvem_codigo"] = nuvem.normalizar_codigo(codigo)
        self.cfg["cfg_rev"] = int(time.time() * 1000) if criar else 0     # quem entra recebe as configurações da loja
        save_json(CONFIG_FILE, self.cfg)
        self.enviado.clear()
        if criar:
            self.empurrar_config()
        self.push_snapshot()

    # ---- este computador como "cliente": usa a rede da loja do computador principal (pelo PIN)
    def conectar_servidor(self, host, codigo):
        self.cfg["nuvem_url"] = "http://%s" % host
        self.cfg["nuvem_codigo"] = codigo
        self.cfg["modo_cliente"] = True
        self.cfg["local_ativo"] = False
        self.cfg["cfg_rev"] = 0                      # recebe as configurações do computador principal
        save_json(CONFIG_FILE, self.cfg)
        if self.local is not None:
            try:
                self.local.sair()
            except Exception:
                pass
            self.local = None
        if self.bridge and isinstance(self.nuvem, nuvem.Multi):      # volta a uma só sincronização (a primeira é a "internet", agora apontando para o principal)
            for extra in self.nuvem.itens[1:]:
                extra.sair()
            self.nuvem = self.nuvem.itens[0]
        self.bridge = False
        if self.nuvem is not None:
            self.nuvem.ultimo.clear()
        self.enviado.clear()
        self.push_snapshot()

    def desconectar_servidor(self):
        """Volta a ser um computador independente (com a internet/Firebase do jeito de antes, se houver código)."""
        self.cfg["modo_cliente"] = False
        self.cfg["nuvem_url"] = NUVEM_URL_PADRAO
        self.cfg["nuvem_codigo"] = ""
        self.cfg["local_ativo"] = True
        save_json(CONFIG_FILE, self.cfg)

    def redescobrir_servidor(self):
        """O computador principal mudou de endereço na rede? Procura de novo pelo código da loja."""
        if self.redescobrindo or rede_local is None:
            return
        self.redescobrindo = True
        cod = self.cfg.get("nuvem_codigo", "")

        def run():
            try:
                achou = rede_local.descobrir(cod)
                if achou:
                    self.cmd_q.put(("servidor_achado", achou[0]))
            finally:
                self.redescobrindo = False
        threading.Thread(target=run, daemon=True).start()

    def open_conectar_servidor(self):
        """Janela: conectar este computador ao computador principal da loja pelo PIN."""
        if rede_local is None:
            return
        w = tk.Toplevel(self.root)
        w.title("Conectar ao computador principal")
        w.configure(bg=BG)
        w.attributes("-topmost", True)
        w.geometry("+%d+%d" % (max(40, self.root.winfo_screenwidth() // 2 - 240), 90))
        tk.Label(w, text="Conectar ao computador principal", font=(FONT, 15, "bold"), bg=BG, fg=INK).pack(padx=26, pady=(18, 4), anchor="w")
        tk.Label(w, text="No computador principal, abra Configurações > Rede da loja e veja o PIN de 6 números.\n"
                         "Os dois computadores precisam estar na mesma rede (Wi-Fi ou cabo).", font=(FONT, 10), bg=BG, fg=GREY, justify="left").pack(padx=26, anchor="w")
        pin = tk.StringVar()
        manual = tk.StringVar()
        tk.Label(w, text="PIN:", font=(FONT, 11), bg=BG, fg=INK).pack(padx=26, pady=(14, 0), anchor="w")
        e1 = tk.Entry(w, textvariable=pin, font=(FONT, 20, "bold"), width=8, justify="center")
        e1.pack(padx=26, anchor="w")
        tk.Label(w, text="Endereço do principal (só se não achar sozinho, ex.: 192.168.0.10:8765):", font=(FONT, 9), bg=BG, fg=GREY).pack(padx=26, pady=(10, 0), anchor="w")
        tk.Entry(w, textvariable=manual, font=(FONT, 10), width=30).pack(padx=26, anchor="w")
        msg = tk.Label(w, text="", font=(FONT, 10), bg=BG, fg=RED, justify="left", wraplength=420)
        msg.pack(padx=26, pady=(10, 0), anchor="w")
        res = {}

        def conectar():
            p = pin.get().strip()
            if len(p) != 6 or not p.isdigit():
                msg.config(text="Digite o PIN de 6 números.", fg=RED)
                return
            btn.config(state="disabled")
            msg.config(text="Procurando o computador principal na rede...", fg=GREY)
            m = manual.get().strip().replace("http://", "").rstrip("/")

            def run():
                try:
                    host = (m if ":" in m or not m else m + ":%d" % rede_local.PORTA_LOCAL)
                    if not host:
                        achados = rede_local.descobrir()
                        if not achados:
                            raise ValueError("Não achei o computador principal. Confira se ele está ligado, com o programa aberto, na mesma rede. "
                                             "Se o Windows perguntou sobre o Firewall, ele precisa ter permitido (Redes privadas).")
                        host = achados[0]
                    cod, loja = rede_local.parear(host, p)
                    res["ok"] = (host, cod)
                except ValueError as ex:
                    res["erro"] = str(ex)
                except Exception as ex:
                    res["erro"] = "Erro: %s" % ex
            t = threading.Thread(target=run, daemon=True)
            t.start()

            def espera():
                if t.is_alive():
                    w.after(300, espera)
                    return
                btn.config(state="normal")
                if res.get("ok"):
                    self.conectar_servidor(*res["ok"])
                    msg.config(text="Conectado! Este computador agora usa os dados do computador principal.", fg=GREEN)
                    btn.config(text="Fechar", command=w.destroy)
                else:
                    msg.config(text=res.get("erro", "Não deu certo."), fg=RED)
                res.clear()
            w.after(300, espera)
        btn = tk.Button(w, text="Conectar", command=conectar, font=(FONT, 12, "bold"), bg=INK, fg="white", bd=0, padx=18, pady=8)
        btn.pack(padx=26, pady=(12, 18), anchor="w")
        e1.focus_set()

    def arquivo_loja(self):
        for pasta in (os.path.dirname(sys.executable) if FROZEN else None, BASE, os.getcwd()):
            if pasta and os.path.isfile(os.path.join(pasta, "loja.txt")):
                try:
                    with open(os.path.join(pasta, "loja.txt"), encoding="utf-8-sig") as f:
                        return nuvem.normalizar_codigo(f.read().strip())
                except OSError:
                    pass
        return ""

    def primeira_execucao(self):
        if nuvem is None or self.cfg.get("nuvem_codigo") or self.cfg.get("wizard_adiado"):
            return
        cod = self.arquivo_loja()
        if cod:
            def ver():
                try:
                    ok = nuvem.verificar_loja(self.cfg["nuvem_url"], cod) is not None
                except Exception:
                    ok = False
                self.cmd_q.put(("loja_arquivo", cod, ok))
            threading.Thread(target=ver, daemon=True).start()
            return
        self.open_wizard()

    def open_wizard(self):
        if nuvem is None:
            return
        if getattr(self, "wiz", None) is not None:
            try:
                if self.wiz.winfo_exists():
                    self.wiz.lift()
                    return
            except tk.TclError:
                pass
        w = self.wiz = tk.Toplevel(self.root)
        w.title("Conectar este computador à loja")
        w.configure(bg=BG)
        w.attributes("-topmost", True)
        w.geometry("+%d+%d" % (max(40, self.root.winfo_screenwidth() // 2 - 260), 90))
        tk.Label(w, text="Conectar à loja", font=(FONT, 16, "bold"), bg=BG, fg=INK).pack(padx=28, pady=(20, 4), anchor="w")
        tk.Label(w, text="Assim o líder vê tudo no celular e os computadores da loja ficam sincronizados:\n"
                         "o que for marcado em um aparece nos outros.", font=(FONT, 10), bg=BG, fg=GREY, justify="left").pack(padx=28, anchor="w")
        msg = tk.StringVar(value="")

        def criar():
            cod = nuvem.novo_codigo()
            self.conectar_loja(cod, True)
            msg.set("Loja criada! Código: %s\nNos outros computadores escolha \"Entrar com o código\". Em Configurações > Loja e líder tem o QR code do celular." % nuvem.formatar_codigo(cod))
            tk.Button(w, text="Fechar", command=w.destroy, font=(FONT, 11, "bold"), bg=INK, fg="white", bd=0, padx=16, pady=8).pack(pady=(0, 18))
            b1.config(state="disabled")
            b2.config(state="disabled")
        b1 = tk.Button(w, text="Este é o primeiro computador: criar a loja", command=criar, font=(FONT, 12, "bold"), bg=INK, fg="white",
                       bd=0, padx=16, pady=10)
        b1.pack(padx=28, pady=(16, 6), fill="x")
        tk.Button(w, text="Este é outro computador: conectar ao principal pelo PIN", command=lambda: (w.destroy(), self.open_conectar_servidor()),
                  font=(FONT, 12, "bold"), bg=PINK, fg="white", bd=0, padx=16, pady=10).pack(padx=28, pady=(6, 6), fill="x")
        tk.Label(w, text="Já existe outro computador? Digite o código da loja (ou copie e cole):", font=(FONT, 10), bg=BG, fg=INK).pack(padx=28, pady=(12, 2), anchor="w")
        var = tk.StringVar()
        ent = tk.Entry(w, textvariable=var, font=(FONT, 12), width=44)
        ent.pack(padx=28, anchor="w")

        def entrar():
            cod = nuvem.normalizar_codigo(var.get())
            if len(cod) < 20:
                msg.set("Código muito curto. Copie o código inteiro do outro computador.")
                return
            msg.set("Procurando a loja...")
            res = []

            def run():
                try:
                    res.append(nuvem.verificar_loja(self.cfg["nuvem_url"], cod) is not None)
                except Exception as e:
                    res.append(nuvem.erro_amigavel(e))
            threading.Thread(target=run, daemon=True).start()

            def espera():
                if not res:
                    w.after(300, espera)
                elif res[0] is True:
                    self.conectar_loja(cod, False)
                    self.show("Conectado", "Este computador entrou na loja. As configurações vêm do outro computador em instantes.", "tag", 9000, True)
                    w.destroy()
                else:
                    msg.set("Loja não encontrada. Confira o código." if res[0] is False else res[0])
            espera()
        b2 = tk.Button(w, text="Entrar com o código", command=entrar, font=(FONT, 11, "bold"), bg=PINK, fg="white", bd=0, padx=14, pady=8)
        b2.pack(padx=28, pady=(8, 0), anchor="w")
        tk.Label(w, textvariable=msg, font=(FONT, 10), bg=BG, fg=INK, wraplength=440, justify="left").pack(padx=28, pady=(10, 4), anchor="w")

        def adiar():
            self.cfg["wizard_adiado"] = True
            save_json(CONFIG_FILE, self.cfg)
            w.destroy()
        tk.Button(w, text="Agora não (usar só neste computador)", command=adiar, font=(FONT, 9), bg=BG, fg=GREY, bd=0).pack(pady=(0, 14))

    # ---- configurações iguais em todos os computadores
    CFG_LOCAIS = {"nuvem_url", "nuvem_codigo", "lider_url", "maquina_id", "maquina_nome", "cfg_rev", "pasta_relatorios", "local_ativo", "local_pin", "local_codigo", "impressora", "impressora_colunas", "imprimir_auto", "modo_cliente", "tema_nome", "tema_cor1", "tema_cor2", "tema_degrade"}

    def empurrar_config_forte(self):
        """Ao abrir, o principal publica as configurações dele com revisão nova, para sobrescrever qualquer cópia antiga no online."""
        self.cfg["cfg_rev"] = max(int(time.time() * 1000), int(self.cfg.get("cfg_rev", 0)) + 1)
        save_json(CONFIG_FILE, self.cfg)
        self.empurrar_config()

    def empurrar_config(self):
        if self.nuvem is None or not self.nuvem.ativo():
            return
        dados = {k: v for k, v in self.cfg.items() if k not in self.CFG_LOCAIS}
        self.nuvem.escrever([("config", {"rev": int(self.cfg.get("cfg_rev", 0)), "json": json.dumps(dados, ensure_ascii=False)})])

    def config_remota(self, c):
        if self.bridge:
            return                  # computador principal: as configurações daqui valem; quem manda é este computador
        try:
            rev = int(c.get("rev", 0))
            self.rev_visto = max(getattr(self, "rev_visto", 0), rev)
            if rev <= int(self.cfg.get("cfg_rev", 0)):
                return
            dados = json.loads(c.get("json") or "{}")
        except Exception:
            return
        novo = dict(self.cfg)
        novo.update({k: v for k, v in dados.items() if k not in self.CFG_LOCAIS})
        novo["cfg_rev"] = rev
        self.apply_config(novo, remoto=True)

    def minha_vez_relatorio(self):
        """Posição deste computador entre os que estão ligados. O primeiro gera o relatório, os outros só entram se ele falhar."""
        agora = time.time() * 1000
        eu = self.cfg.get("maquina_id", "")
        vivos = {eu}
        for m, v in (getattr(self, "maquinas", None) or {}).items():
            if isinstance(v, dict) and agora - float(v.get("ts", 0)) < 150000:
                vivos.add(m)
        return sorted(vivos).index(eu)

    def build_snapshot(self):
        st, cfg = self.state, self.cfg
        nomes = {e["id"]: e["nome"] for e in self.funcionarios()}
        tarefas = []
        for e in sorted(st.get("log", []), key=lambda x: x["done"]):
            tarefas.append({"key": nuvem.chave_tarefa(e["k"], e["id"], e["done"]), "tipo": e["k"], "nome": e["nome"],
                            "previsto": int(e["due"] * 1000), "feito": int(e["done"] * 1000),
                            "atraso": round(max(0.0, (e["done"] - e["due"]) / 60.0), 1), "func": nomes.get(e.get("func"), ""),
                            "pts": e.get("pts", 0), "pen": e.get("pen", 0), "via": e.get("via", "")})
        faltando, total = [], 0
        if relatorio is not None:
            try:
                d = relatorio.coletar(st, cfg)
                faltando, total = d["pendentes"], d["total"]
            except Exception:
                log("snapshot coletar: " + traceback.format_exc())
        urg = [{"nome": p.get("text") or p.get("label", ""), "desde": int(p["start"] * 1000), "nivel": p.get("maxlevel", 0)}
               for p in self.pend.values()]
        return {"loja": cfg.get("nome_loja", ""), "data": st["date"], "atualizado": int(time.time() * 1000),
                "aberto": bool(self.day_open), "funcionario": self.emp_nome(self.emp_id()) if self.funcionarios() else cfg.get("nome_caixa", ""),
                "pontos": st.get("pontos", 0), "pts_func": {nomes.get(k, k): v for k, v in st.get("pts_func", {}).items()},
                "tarefas": tarefas, "faltando": faltando, "total": total, "urgentes": urg,
                "rejeitadas": st.get("rejeitadas", []), "relatorio": bool(st.get("relatorio_gerado")),
                "funcionarios": [{"id": e["id"], "nome": e["nome"]} for e in self.funcionarios()],
                "lista": self.lista_snapshot(), "agenda": self.agenda_snapshot(), "entregas": self.entregas_cfg()}

    def agenda_snapshot(self):
        if agenda is None:
            return []
        corte = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        itens = sorted([it for it in agenda.vivos(self.agenda) if it["data"] >= corte], key=agenda.chave_roteiro)
        campos = ("id", "data", "hora", "tipo", "titulo", "detalhe", "antes", "feito") + agenda.EXTRAS
        return [{k: it.get(k) for k in campos if it.get(k) not in (None, "")} for it in itens[:300]]

    def lista_snapshot(self):
        bucket = {"am": "am", "cx": "cx", "lem": "lem", "conf": "last"}
        out = []
        for kind, iid, nome in self.lista_tarefas():
            try:
                prev = int(self.due_ts(kind, iid) * 1000)
            except Exception:
                prev = 0
            out.append({"k": kind, "id": iid, "nome": nome, "previsto": prev, "feito": int((self.state[bucket[kind]].get(iid) or 0) * 1000)})
        return out

    def lista_tarefas(self):
        """Todas as tarefas de hoje: (tipo, id, nome)."""
        out = [("am", r[0], r[1]) for r in self.cfg["ao_chegar"]]
        out += [("cx", str(h), "Caixa das %sh" % h) for h in self.cfg["horas_caixa"]]
        out += [("conf", r[0], r[1]) for r in self.cfg["conferencias"]]
        out += [("lem", lid, nome) for lid, mn, nome, texto, curto in lembretes_cfg(self.cfg)]
        return out

    def aplicar_pedido(self, p):
        """Marcação feita no celular do funcionário. A hora e o autor vêm do pedido, então todos os computadores chegam ao mesmo resultado."""
        if p.get("k") == "ag":
            return self.pedido_agenda(p)
        kind, iid = p.get("k"), str(p.get("id"))
        try:
            ts = float(p.get("ts", 0)) / 1000.0
        except (TypeError, ValueError):
            return False
        if not ts or kind not in ("am", "cx", "lem", "conf") or not any(t == kind and i == iid for t, i, _ in self.lista_tarefas()):
            return False
        if abs(time.time() - ts) > 36 * 3600:
            return False
        st = self.state
        bucket = {"am": "am", "cx": "cx", "lem": "lem", "conf": "last"}[kind]
        if kind != "conf" and st[bucket].get(iid):
            return False
        if kind == "conf":
            ult = st["last"].get(iid) or 0
            if "conf-" + iid not in self.pend and ult and ts - ult < int(self.cfg.get("conferencia_espera_minutos", 30)) * 60:
                return False
        fid = p.get("fid") if any(e["id"] == p.get("fid") for e in self.funcionarios()) else None
        self.ov = {"ts": ts, "fid": fid}
        try:
            self.record(kind, iid, "celular")
        finally:
            self.ov = None
        st[bucket][iid] = max(ts, st[bucket].get(iid) or 0)
        if kind == "conf":
            self.conf_gate_until = time.time() + self.cfg["intervalo_entre_conferencias_minutos"] * 60
        q = self.pend.get({"cx": "cx" + iid, "conf": "conf-" + iid, "lem": iid}.get(kind, ""))
        if q:
            st["ok"] += 1
            self.close_pending_pop(q)
            self.pend.pop({"cx": "cx" + iid, "conf": "conf-" + iid, "lem": iid}[kind], None)
        self.save()
        self.refresh()
        self.check_celebrate()
        return True

    def on_pedidos(self, dia, ped):
        if dia != self.state["date"]:
            # pedidos de agenda feitos de dias em que este computador estava desligado (celular/iPhone pela internet)
            try:
                idade = (dt.date.today() - dt.datetime.strptime(dia, "%Y-%m-%d").date()).days
            except ValueError:
                return
            if not 0 < idade <= 7:
                return
            for pid, p in sorted(ped.items(), key=lambda kv: (kv[1] or {}).get("ts", 0) if isinstance(kv[1], dict) else 0):
                if isinstance(p, dict) and p.get("k") == "ag":
                    try:
                        self.aplicar_pedido(dict(p, pid=pid, atrasado=True))
                    except Exception:
                        log("pedido antigo: " + traceback.format_exc())
            return
        vistos = self.state.setdefault("pedidos_vistos", [])
        for pid, p in sorted(ped.items(), key=lambda kv: (kv[1] or {}).get("ts", 0) if isinstance(kv[1], dict) else 0):
            if pid in vistos or not isinstance(p, dict):
                continue
            vistos.append(pid)
            try:
                self.aplicar_pedido(dict(p, pid=pid))
            except Exception:
                log("pedido: " + traceback.format_exc())

    def avisar_lider(self, titulo, texto, prio=3):
        if self.local is not None:
            self.local.avisar(titulo, texto, prio)
        if self.nuvem is not None and not self.cfg.get("modo_cliente"):
            self.nuvem.avisar(titulo, texto, prio)

    def on_validacoes(self, dia, novas):
        if dia != self.state["date"]:
            return
        vistas = self.state.setdefault("val_vistas", {})
        mudou = False
        for k, v in novas.items():
            if k in vistas:
                continue
            vistas[k] = v.get("ts")
            lg = self.state["log"]
            idx = next((i for i, e in enumerate(lg) if nuvem.chave_tarefa(e["k"], e["id"], e["done"]) == k), None)
            if idx is None:
                continue
            e = lg[idx]
            mudou = True
            if v.get("ok"):
                e["val"] = "ok"
                self.show("O líder conferiu", "%s: conferido. Obrigado!" % e["nome"], "tag", 7000, True)
                continue
            # o líder disse que NÃO estava feito: tira os pontos, desconta a penalidade e reabre a tarefa
            fid = e.get("func")
            self.marcar_removida(e)
            del lg[idx]
            pen = int(self.cfg.get("penalidade_nao_feito", 2))
            self.penalize(e["nome"], pen, "Líder: não estava feito", fid, "rej-" + k)
            self.add_points(0, fid or "_")
            kind, iid = e["k"], str(e["id"])
            bucket = {"am": "am", "cx": "cx", "lem": "lem", "conf": "last"}.get(kind)
            if bucket:
                self.state[bucket][iid] = 0
            rj = self.state.setdefault("rejeitadas", [])
            if not any(x.get("key") == k for x in rj):
                rj.append({"key": k, "nome": e["nome"], "func": fid, "quando": int(time.time() * 1000),
                           "nota": v.get("nota", ""), "pts": max(0, int(e.get("pts", 0))) + pen})
            nota = (" Motivo: %s." % v["nota"]) if v.get("nota") else ""
            self.show("Líder: não estava feito", "%s. Faça de verdade e marque de novo. -%d pontos.%s" % (e["nome"], max(0, int(e.get("pts", 0))) + pen, nota),
                      "banner", 20000, True)
        if self.nuvem is not None:
            self.nuvem.confirmar(novas)
        if mudou:
            self.save()
            self.refresh()

    def day_sched(self, d=None):
        d = d or dt.date.today()
        iso = d.isoformat()
        for ex in self.cfg.get("excecoes") or []:          # datas especiais (campanhas, sábado diferente...) valem mais que o dia da semana
            try:
                if ex.get("de", "") <= iso <= (ex.get("ate") or ex.get("de", "")):
                    return ex
            except Exception:
                continue
        base = (self.cfg.get("dias_semana") or {}).get(str(d.weekday()))
        if not isinstance(base, dict):
            base = DEFAULT_DIAS[str(d.weekday())]
        return base

    @staticmethod
    def horas_auto(tarde):
        """Sem horas definidas: confere o caixa a cada hora cheia da tarde (da abertura até 1 hora antes do fim)."""
        ini, fim = hm_to_min(tarde[0]), hm_to_min(tarde[1])
        h0 = (ini + 59) // 60
        return list(range(h0, max(h0 + 1, fim // 60)))

    def apply_day(self):
        """Aplica o horário do dia da semana de hoje (cada dia pode ter o seu)."""
        s = self.day_sched()
        ref = DEFAULT_DIAS["0"]
        self.day_open = bool(s.get("aberto", True))
        self.cfg["ao_chegar_horario"] = list(s.get("ao_chegar") or ref["ao_chegar"])
        self.cfg["tarde_horario"] = list(s.get("tarde") or ref["tarde"])
        horas = s.get("horas") or self.horas_auto(self.cfg["tarde_horario"])
        self.cfg["horas_caixa"] = sorted(int(h) for h in horas)
        self.state["sched"] = {"aberto": self.day_open, "ao_chegar_horario": self.cfg["ao_chegar_horario"],
                               "tarde_horario": self.cfg["tarde_horario"], "horas_caixa": self.cfg["horas_caixa"]}

    # ---- som
    def beep(self, kind):
        if not self.cfg.get("som"):
            return
        seqs = [[(660, 110), (880, 150)], [(520, 110), (780, 110), (660, 150)], [(740, 120), (590, 160)]]
        seq = seqs[kind % 3]

        def run():
            try:
                if winsound:
                    for f, d in seq:
                        winsound.Beep(f, d)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def alarm(self, level):
        if not self.cfg.get("som"):
            return
        seq = [(880, 160), (880, 160)] if level == 1 else [(988, 180), (740, 180), (988, 180), (740, 180)]

        def run():
            try:
                if winsound:
                    for f, d in seq:
                        winsound.Beep(f, d)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    # ---- criação de janelas
    def new_win(self, bg, alpha=None):
        w = tk.Toplevel(self.root)
        w.withdraw()
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=bg)
        if alpha is not None:
            w.attributes("-alpha", alpha)
        return w

    def finish(self, win, w, h, corner, extra=None):
        win.update_idletasks()
        noactivate(win)
        win.geometry("%dx%d+0+0" % (w, h))
        pop = Pop(self, win, w, h, corner, extra)
        self.pops.append(pop)
        self.relayout()
        win.deiconify()
        win.attributes("-topmost", True)
        noactivate(win)
        return pop

    def relayout(self):
        l, t, r, b = work_area(self.root)
        m = 16
        off = {"br": 0, "bl": 0, "tr": 0, "tl": 0}
        banner_h = sum(p.h for p in self.pops if p.corner == "tc")
        for p in self.pops:
            c = p.corner
            if c == "tc":
                x, y = l, t
                p.win.geometry("%dx%d+%d+%d" % (r - l, p.h, x, y))
            elif c == "bc":
                x, y = l + (r - l - p.w) // 2, b - m - p.h
                p.win.geometry("%dx%d+%d+%d" % (p.w, p.h, x, y))
            else:
                x = (r - p.w - m) if c in ("br", "tr") else (l + m)
                if c in ("br", "bl"):
                    y = b - m - off[c] - p.h
                else:
                    y = t + m + banner_h + off[c]
                off[c] += p.h + 10
                p.win.geometry("%dx%d+%d+%d" % (p.w, p.h, x, y))

    def card(self, corner, w, bg, fg, label, text, buttons, ms=None, progress=False,
             text_size=13, border=None, pause_link=False, click_close=False):
        win = self.new_win(border or bg)
        outer = tk.Frame(win, bg=bg)
        outer.pack(fill="both", expand=True, padx=3 if border else 0, pady=3 if border else 0)
        frm = tk.Frame(outer, bg=bg)
        frm.pack(fill="both", expand=True, padx=14, pady=(10, 8))
        tk.Label(frm, text=label.upper(), font=(FONT, 9, "bold"), bg=bg, fg=fg, anchor="w").pack(fill="x")
        tk.Label(frm, text=text, font=(FONT, text_size, "bold"), bg=bg, fg=fg, wraplength=w - 50,
                 justify="left", anchor="w").pack(fill="x", pady=(2, 10))
        bar = tk.Frame(frm, bg=bg)
        bar.pack(fill="x")
        holder = {}

        def wrap(cb):
            def f():
                try:
                    if cb:
                        cb()
                finally:
                    if holder.get("pop"):
                        holder["pop"].close()
            return f
        for txt, cb in buttons:
            tk.Button(bar, text=txt, command=wrap(cb), bg=fg, fg=bg, activebackground=fg, activeforeground=bg,
                      relief="flat", font=(FONT, 10, "bold"), padx=14, pady=5, cursor="hand2").pack(side="left", padx=(0, 8))
        if pause_link:
            tk.Button(bar, text="pausar %d min" % self.cfg["pausa_atendimento_minutos"],
                      command=wrap(lambda: self.set_hold(True)), bg=bg, fg=fg, activebackground=bg,
                      activeforeground=fg, relief="flat", bd=0, font=(FONT, 9, "underline"),
                      cursor="hand2").pack(side="right")
        bar_prog = None
        if progress and ms:
            bar_prog = tk.Frame(outer, bg=fg, height=4)
            bar_prog.place(x=0, rely=1.0, y=-4, relwidth=1.0, height=4)
        win.update_idletasks()
        h = win.winfo_reqheight()
        pop = self.finish(win, w, h, corner)
        holder["pop"] = pop
        if click_close:
            def walk(wd):
                wd.bind("<Button-1>", lambda e: pop.close())
                for ch in wd.winfo_children():
                    walk(ch)
            walk(win)
        if ms:
            pop.after_id = self.root.after(ms, pop.close)
            if bar_prog is not None:
                t0 = time.time()

                def step():
                    if pop.closed:
                        return
                    frac = max(0.0, 1 - (time.time() - t0) * 1000 / ms)
                    bar_prog.place_configure(relwidth=frac)
                    self.root.after(200, step)
                step()
        return pop

    def edge_flash(self, color, ms=5000):
        l, t, r, b = 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        th = 10
        rects = [(l, t, r - l, th), (l, b - th, r - l, th), (l, t, th, b - t), (r - th, t, th, b - t)]
        wins = []
        for (x, y, w, h) in rects:
            win = self.new_win(color)
            win.update_idletasks()
            noactivate(win)
            win.geometry("%dx%d+%d+%d" % (w, h, x, y))
            win.deiconify()
            win.attributes("-topmost", True)
            wins.append(win)
        state = {"on": True, "n": 0, "dead": False}

        def blink():
            if state["dead"]:
                return
            state["n"] += 1
            state["on"] = not state["on"]
            for w in wins:
                try:
                    w.attributes("-alpha", 0.95 if state["on"] else 0.0)
                except Exception:
                    pass
            if state["n"] < 8:
                self.root.after(480, blink)
        blink()

        def kill():
            state["dead"] = True
            for w in wins:
                try:
                    w.destroy()
                except Exception:
                    pass
        self.root.after(ms, kill)
        return kill

    # ---- formatos de aviso
    def pick_fmt(self):
        opts = [f for f in ("tag", "banner", "edge", "ask", "blink") if f != self.last_fmt]
        self.last_fmt = random.choice(opts)
        return self.last_fmt

    def show(self, label, text, fmt=None, ms=None, test=False):
        fmt = fmt or self.pick_fmt()
        self.last_shown = time.time()
        if not test:
            self.state["shown"] += 1
            self.save()
        order = ["tag", "banner", "edge", "ask", "blink"]
        if fmt == "joy":
            self.chime()
        else:
            self.beep(order.index(fmt))

        def ok():
            if not test:
                self.state["ok"] += 1
                self.save()

        def later():
            self.root.after(120000, lambda: self.show(label, text, "tag"))

        if fmt == "joy":
            self.card(random.choice(["br", "bl", "tr", "tl"]), 400, GREEN, "#FFFFFF", label, text, [],
                      ms=ms or 9000, text_size=14, click_close=True)
        elif fmt == "tag":
            self.card(random.choice(["br", "br", "bl", "tr"]), 380, PINK, "#FFFFFF", label, text,
                      [("Ok", ok)], ms=ms or 10000, progress=True, pause_link=True)
        elif fmt == "banner":
            self.card("tc", 900, BLUE, "#FFFFFF", label, text, [("Ok", ok)], ms=ms or 7000, text_size=14)
        elif fmt == "edge":
            kill = self.edge_flash(PINK, (ms or 6500))
            pop = self.card("bc", 520, PINK, "#FFFFFF", label, text, [("Ok", ok)], ms=ms or 6500)
            pop.on_close = kill
        elif fmt == "ask":
            self.card(random.choice(["br", "tr", "bl"]), 400, PAPER, INK, label, text,
                      [("Feito", ok), ("Lembrar depois", later)], ms=ms or 16000,
                      text_size=14, border=PINK, pause_link=True)
        else:
            self.blink_pill(text, ms or 7500, ok)

    def blink_pill(self, text, ms, ok):
        win = self.new_win(INK)
        frm = tk.Frame(win, bg=INK)
        frm.pack(fill="both", expand=True, padx=12, pady=8)
        cv = tk.Canvas(frm, width=16, height=16, bg=INK, highlightthickness=0)
        dot = cv.create_oval(2, 2, 14, 14, fill=PINK, outline="")
        cv.pack(side="left", padx=(0, 10))
        lbl = tk.Label(frm, text=text, font=(FONT, 12, "bold"), bg=INK, fg="#FFFFFF", wraplength=330, justify="left")
        lbl.pack(side="left")
        win.update_idletasks()
        w, h = max(220, win.winfo_reqwidth()), win.winfo_reqheight()
        pop = self.finish(win, w, h, random.choice(["br", "bl", "tr", "tl"]))

        def click(_e=None):
            ok()
            pop.close()
        for wd in (win, frm, cv, lbl):
            wd.bind("<Button-1>", click)
        n = {"i": 0}

        def blink():
            if pop.closed:
                return
            n["i"] += 1
            cv.itemconfigure(dot, fill=PINK if n["i"] % 2 else INK)
            if n["i"] < 14:
                self.root.after(300, blink)
        blink()
        pop.after_id = self.root.after(ms, pop.close)

    # ---- pendências com escalonamento
    def add_pending(self, pid, label, text, kind, arg, until_min):
        if pid in self.pend:
            self.pend[pid]["text"] = text
            return
        self.pend[pid] = {"label": label, "text": text, "kind": kind, "arg": arg, "until": until_min,
                          "start": time.time(), "next_at": 0, "pop": None, "level": -1,
                          "maxlevel": 0, "snoozes": 0, "fid": self.emp_id()}

    def resolved(self, p, m):
        k, a = p["kind"], p["arg"]
        if k == "cx":
            return bool(self.state["cx"].get(str(a)))
        if k == "conf":
            return not self.is_stale(a, m)
        if k == "am":
            return all(self.state["am"].get(i) for i, _ in self.cfg["ao_chegar"])
        if k == "lem":
            return bool(self.state["lem"].get(a))
        return False

    def close_pending_pop(self, p):
        if p.get("pop") and not p["pop"].closed:
            p["pop"].close()
        p["pop"] = None

    def complete(self, pid):
        p = self.pend.get(pid)
        if not p:
            return
        now = time.time()
        kind, arg = p["kind"], p["arg"]
        if kind in ("cx", "conf", "lem"):
            self.record(kind, arg, "aviso")
        if kind == "cx":
            self.state["cx"][str(arg)] = now
        elif kind == "conf":
            self.state["last"][arg] = now
            self.conf_gate_until = now + self.cfg["intervalo_entre_conferencias_minutos"] * 60
        elif kind == "lem":
            self.state["lem"][arg] = now
        self.state["ok"] += 1
        self.save()
        self.close_pending_pop(p)
        self.pend.pop(pid, None)
        self.refresh()
        if kind in ("cx", "conf", "lem"):
            self.after_done(kind, arg)

    def snooze(self, pid):
        p = self.pend.get(pid)
        if p:
            p["snoozes"] = p.get("snoozes", 0) + 1
            p["next_at"] = time.time() + self.cfg["adiar_minutos"] * 60
            self.close_pending_pop(p)

    def show_pending(self, pid, p):
        elapsed = time.time() - p["start"]
        e1, e2 = [x * 60 for x in self.cfg["escalonar_apos_minutos"]]
        level = 0 if elapsed < e1 else (1 if elapsed < e2 else 2)
        self.close_pending_pop(p)
        p["level"] = level
        p["maxlevel"] = max(p.get("maxlevel", 0), level)
        self.last_shown = time.time()
        self.state["shown"] += 1
        self.save()
        if p["kind"] == "am":
            btns = [("Abrir a lista", self.open_window), ("Adiar", lambda: self.snooze(pid))]
        else:
            btns = [("Concluído", lambda: self.complete(pid)), ("Adiar %d min" % self.cfg["adiar_minutos"], lambda: self.snooze(pid))]
        if self.local is not None and not p.get("local_n%d" % level):
            p["local_n%d" % level] = True
            self.local.avisar(("Caixa: " if level < 2 else "URGENTE: ") + p["label"], p["text"], 3 + level)
        if level == 0:
            self.beep(0)
            p["pop"] = self.card("br", 400, PINK, "#FFFFFF", p["label"], p["text"], btns, text_size=14)
            p["next_at"] = p["start"] + e1
        elif level == 1:
            self.alarm(1)
            p["pop"] = self.card("br", 460, ORANGE, "#FFFFFF", "Ainda pendente · " + p["label"], p["text"], btns, text_size=17)
            self.root.after(0, lambda: self.edge_flash(ORANGE, 3500))
            p["next_at"] = p["start"] + e2
        else:
            self.alarm(2)
            if not p.get("lider_avisado"):
                p["lider_avisado"] = True
                self.avisar_lider("Caixa: tarefa atrasada", "%s está pendente há %s." % (p["label"], ago_txt(elapsed)), 4)
            p["pop"] = self.card("tc", 900, RED, "#FFFFFF", "URGENTE · " + p["label"],
                                 p["text"] + "  (pendente há %s)" % ago_txt(elapsed) + self.pen_txt(elapsed), btns, text_size=20)
            self.root.after(0, lambda: self.edge_flash(RED, 6000))
            p["next_at"] = time.time() + self.cfg["repetir_urgente_minutos"] * 60

    def p_done(self, p):
        k, a = p["kind"], p["arg"]
        if k == "cx":
            return bool(self.state["cx"].get(str(a)))
        if k == "lem":
            return bool(self.state["lem"].get(a))
        if k == "conf":
            return (self.state["last"].get(a) or 0) >= p["start"]
        return False

    def tick_pending(self, m):
        for pid, p in list(self.pend.items()):
            res = self.resolved(p, m)
            if m >= p["until"] or res:
                if m >= p["until"] and p["kind"] != "am" and not self.p_done(p):
                    self.penalize(self.task_name(p["kind"], p["arg"]), self.cfg.get("penalidade_nao_feito", 2), "Não feito", p.get("fid"), "nf-%s-%s" % (p["kind"], p["arg"]))
                self.close_pending_pop(p)
                self.pend.pop(pid, None)
                continue
            if time.time() >= p["next_at"] and not self.holding():
                self.show_pending(pid, p)

    # ---- conferências
    def is_stale(self, cid, m):
        _, p = self.ranges()
        last = self.state["last"].get(cid)
        if m >= p[1]:
            return False
        if not last:
            return m >= p[0] + 30
        return time.time() - last > self.cfg["repetir_conferencia_minutos"] * 60

    # ---- eventos por minuto
    def once(self, key):
        if key in self.fired:
            return False
        self.fired.add(key)
        return True

    def notify(self, label, text, fmt="tag", ms=14000):
        if self.holding():
            if all(q[1] != text for q in self.queue_hold):
                self.queue_hold.append((label, text, fmt, ms))
            return
        self.show(label, text, fmt, ms)

    def on_minute(self, d):
        if d.minute % 5 == 0:        # sinal de vida: o líder vê que o programa do caixa está ligado
            self.push_snapshot()
        if today() != self.state["date"]:
            self.state = fresh_state()
            self.fired.clear()
            self.conf_gate_until = 0
            self.pend.clear()
            self.apply_day()
            self.save()
        try:
            self.tick_agenda()
        except Exception:
            log("tick_agenda: " + traceback.format_exc())
        if self.cfg.get("modo_cliente") and self.nuvem is not None and self.nuvem.ultimo_erro and time.time() - self.nuvem.ultimo_ok > 90:
            self.redescobrir_servidor()
        m = d.hour * 60 + d.minute
        a, p = self.ranges()
        ph = self.phase(m)
        if not self.day_open:
            return
        self.checar_quem(d)
        if m % 10 == 0:
            self.process_envios()
        if m == a[0] and self.once("open"):
            self.notify("Bom dia", "Hora de abrir: comece pelo checklist de ao chegar")
        for off in (40, 75):
            if m == a[0] + off and ph == "am":
                n = sum(1 for i, _ in self.cfg["ao_chegar"] if not self.state["am"].get(i))
                if n and self.once("am%d" % off):
                    self.add_pending("am", "Ao chegar", "Faltam %d %s do checklist de abertura" % (n, "itens" if n > 1 else "item"),
                                     "am", None, a[1])
        if m == a[1] - 5 and self.once("prel"):
            self.notify("Quase hora do almoço", "Confira o caixa antes de sair")
        if (ph == "end" and self.cfg.get("gerar_relatorio_no_fim", True) and not self.state.get("relatorio_gerado")
                and (self.state["log"] or self.state.get("shown")) and self.once("fim")):
            self.fim_alvo = time.time() + 25 * self.minha_vez_relatorio()
        if m == a[1] and self.once("lunch"):
            self.notify("Almoço", "Bom almoço! Volta às %s" % self.cfg["tarde_horario"][0], "banner", 7000)
        # caixa de hora em hora (também pega quem abre o app no meio da hora)
        for h in self.cfg["horas_caixa"]:
            if h * 60 <= m < h * 60 + 60 and ph == "pm" and not self.state["cx"].get(str(h)):
                if self.once("cx%d" % h):
                    txt = ("De volta do almoço! Confira o caixa das %dh" % h) if h * 60 == p[0] \
                        else "Hora de conferir o caixa das %dh" % h
                    self.add_pending("cx%d" % h, "Caixa", txt, "cx", h, min(h * 60 + 90, p[1]))
        # lembretes fixos (maquininha etc.)
        for lid, mn, nome, texto, curto in lembretes_cfg(self.cfg):
            if ph in ("am", "pm") and mn <= m < mn + 90 and not self.state["lem"].get(lid) and self.once(lid):
                self.add_pending(lid, curto, texto, "lem", lid, min(mn + 90, p[1] + 30))
        # conferências vencidas: uma de cada vez, com intervalo entre elas
        if ph == "pm" and time.time() >= self.conf_gate_until \
                and not any(k.startswith("conf-") for k in self.pend):
            for cid, name, *_ in self.cfg["conferencias"]:
                if self.is_stale(cid, m):
                    last = self.state["last"].get(cid)
                    extra = " (já faz %s)" % ago_txt(time.time() - last) if last else ""
                    self.add_pending("conf-" + cid, "Conferência", name + extra, "conf", cid, p[1])
                    break

    # ---- avisos aleatórios
    def sched_random(self):
        a, b = self.cfg["aviso_aleatorio_min_minutos"], self.cfg["aviso_aleatorio_max_minutos"]
        return time.time() + random.uniform(a, max(a, b)) * 60

    def fill_name(self, text):
        e = self.current_emp()
        nome = (e["nome"] if e else (self.cfg.get("nome_caixa") or "")).strip()
        if nome:
            return text.replace("{nome}", nome)
        return text.replace(", {nome}", "").replace("{nome}", "").replace("  ", " ").strip()

    def pick_text(self, arr):
        txt = random.choice(arr)
        for _ in range(12):
            if txt not in self.recent or len(arr) < 2:
                break
            txt = random.choice(arr)
        self.recent.append(txt)
        self.recent = self.recent[-8:]
        return txt

    def pick_random(self):
        joy = [x for x in self.cfg.get("avisos_alegres", []) if x.strip()]
        try:
            chance = float(self.cfg.get("chance_aviso_alegre", 25))
        except Exception:
            chance = 25
        if joy and random.random() * 100 < chance:
            return "Pra alegrar o dia", self.fill_name(self.pick_text(joy)), "joy"
        att = [x for x in self.cfg["durante_atendimento"] if x.strip()]
        free = [x for x in self.cfg["quando_livre"] if x.strip()]
        use_att = random.random() < 0.55
        if not att:
            use_att = False
        if not free:
            use_att = True
        arr = att if use_att else free
        if not arr:
            return None
        return ("Atenção" if use_att else "Se estiver livre"), self.pick_text(arr), None

    def tick_random(self, m):
        if time.time() < self.next_random:
            return
        busy = any(p.get("pop") and not p["pop"].closed for p in self.pend.values())
        if not self.in_work(m):
            self.next_random = self.sched_random()
        elif self.holding() or busy or time.time() - self.last_shown < 90:
            self.next_random = time.time() + 45
        else:
            r = self.pick_random()
            if r:
                self.show(*r)
            self.next_random = self.sched_random()

    # ---- funcionários
    def funcionarios(self):
        return [e for e in self.cfg.get("funcionarios", []) if str(e.get("nome", "")).strip()]

    def emp_nome(self, fid):
        for e in self.funcionarios():
            if e["id"] == fid:
                return e["nome"]
        return "Sem funcionário" if fid in (None, "_") else str(fid)

    @staticmethod
    def shift_of(e, wd):
        v = (e.get("dias") or {}).get(str(wd))
        try:
            return hm_to_min(v[0]), hm_to_min(v[1])
        except Exception:
            return None

    def current_emp(self):
        """Quem está no caixa agora: o escolhido à mão ou quem está no turno."""
        emps = self.funcionarios()
        if not emps:
            return None
        man = self.state.get("func_manual")
        if man:
            for e in emps:
                if e["id"] == man:
                    return e
        d = dt.datetime.now()
        m = d.hour * 60 + d.minute
        shifts = [(e, self.shift_of(e, d.weekday())) for e in emps]
        shifts = [(e, sh) for e, sh in shifts if sh]
        for e, (a, b) in shifts:
            if a <= m < b:
                return e
        if shifts:
            past = [(b, e) for e, (a, b) in shifts if b <= m]
            if past:
                return max(past, key=lambda x: x[0])[1]
            return min(shifts, key=lambda x: x[1][0])[0]
        return emps[0]

    def emp_id(self):
        e = self.current_emp()
        return e["id"] if e else "_"

    def score_fid(self):
        return self.emp_id() if self.funcionarios() else None

    def set_func_manual(self, fid):
        self.state["func_manual"] = fid or None
        self.state["combo"] = 0
        self.save()
        self.refresh()

    # ---- registro das tarefas, pontos e prêmio
    def task_name(self, kind, arg):
        if kind == "cx":
            return "Caixa das %sh" % arg
        if kind == "lem":
            for lid, mn, nome, texto, curto in lembretes_cfg(self.cfg):
                if lid == arg:
                    return nome
            return str(arg)
        for row in (self.cfg["ao_chegar"] if kind == "am" else self.cfg["conferencias"]):
            if row[0] == arg:
                return row[1]
        return str(arg)

    def due_ts(self, kind, arg):
        """Horário em que a tarefa deveria ter sido feita."""
        t0 = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
        a, p = self.ranges()
        if kind == "am":
            return t0 + a[0] * 60
        if kind == "cx":
            return t0 + int(arg) * 3600
        if kind == "lem":
            pend = self.pend.get(arg)
            if pend:
                return pend["start"]
            for lid, mn, nome, texto, curto in lembretes_cfg(self.cfg):
                if lid == arg:
                    return t0 + mn * 60
            return time.time()
        pend = self.pend.get("conf-" + str(arg))
        if pend:
            return pend["start"]
        last = self.state["last"].get(arg)
        if last:
            return last + self.cfg["repetir_conferencia_minutos"] * 60
        return t0 + (p[0] + 30) * 60

    # penalidades
    def penalty_for(self, atraso):
        """Pontos perdidos por demorar demais (atraso em minutos)."""
        c = self.cfg
        if not c.get("penalidade_ativa", True):
            return 0
        late = atraso - float(c.get("penalidade_apos_minutos", 15))
        if late <= 0:
            return 0
        step = max(1, int(c.get("penalidade_a_cada_minutos", 10)))
        pen = math.ceil(late / step) * int(c.get("penalidade_pontos", 2))
        return min(pen, int(c.get("penalidade_max_por_tarefa", 10)))

    def pen_txt(self, elapsed_seconds):
        pen = self.penalty_for(elapsed_seconds / 60.0)
        return "  ·  já perdeu %d pontos" % pen if pen > 0 else ""

    def penalize(self, nome, n, motivo, fid=None, pid=None):
        n = int(n or 0)
        if n <= 0 or not self.cfg.get("penalidade_ativa", True):
            return
        fid = fid or "_"
        pid = pid or "p" + uuid.uuid4().hex[:10]
        pl = self.state.setdefault("penal", [])
        if any(x.get("id") == pid for x in pl):      # já aplicada (aqui ou em outro computador)
            return
        pl.append({"id": pid, "nome": nome, "pen": n, "motivo": motivo, "func": fid, "t": time.time()})
        self.add_points(0, fid)
        self.save()

    def settle_pendings(self, m):
        """No fim do dia: o que ficou pendente perde pontos e as pendências fecham."""
        for pid, p in list(self.pend.items()):
            if p["kind"] != "am" and not self.p_done(p):
                self.penalize(self.task_name(p["kind"], p["arg"]), self.cfg.get("penalidade_nao_feito", 2), "Não feito", p.get("fid"), "nf-%s-%s" % (p["kind"], p["arg"]))
            self.close_pending_pop(p)
            self.pend.pop(pid, None)

    def record(self, kind, arg, via):
        now = self.ov["ts"] if self.ov else time.time()
        pid = {"cx": "cx%s" % arg, "conf": "conf-%s" % arg, "lem": arg}.get(kind)
        p = self.pend.get(pid) if pid else None
        due = min(self.due_ts(kind, arg), now)
        atraso = max(0.0, (now - due) / 60.0)
        c = self.cfg
        if atraso <= PRAZO_MIN:
            base = int(c.get("pontos_no_prazo", 2))
        else:
            base = int(c.get("pontos_atraso_leve", 1)) if atraso <= LEVE_MIN else int(c.get("pontos_atrasado", 0))
        self.state["combo"] = 0
        if kind == "conf":     # anti-burla: cada conferência só pontua algumas vezes por dia
            lim = int(c.get("limite_pontos_conferencia_dia", 4))
            if sum(1 for x in self.state["log"] if x["k"] == "conf" and x["id"] == str(arg) and x.get("base", 0) > 0) >= lim:
                base = 0
        pen = self.penalty_for(atraso)
        pts = base - pen
        fid = (self.ov or {}).get("fid") or self.emp_id()
        self.state["log"].append({
            "k": kind, "id": str(arg), "nome": self.task_name(kind, arg), "due": due, "done": now,
            "nivel": p.get("maxlevel", 0) if p else 0, "adiou": p.get("snoozes", 0) if p else 0,
            "via": via, "pts": pts, "base": base, "pen": pen, "func": fid})
        self.last_award = (pts, self.state["combo"], pen)
        self.add_points(0, fid)
        self.save()

    def marcar_removida(self, e):
        k = chave_log(e)
        rm = self.state.setdefault("removidas", [])
        if k not in rm:
            rm.append(k)

    def unrecord(self, kind, arg):
        lg = self.state["log"]
        for i in range(len(lg) - 1, -1, -1):
            if lg[i]["k"] == kind and lg[i]["id"] == str(arg):
                pts, fid = lg[i].get("pts", 0), lg[i].get("func") or "_"
                self.marcar_removida(lg[i])
                del lg[i]
                self.state["combo"] = 0
                self.add_points(0, fid)
                break
        self.save()

    # pontos, sequência e meta da semana (por funcionário)
    def recalc_points(self):
        """Pontos = soma do que está no registro do dia - penalidades + bônus. Assim todos os computadores chegam ao mesmo número."""
        st, pf = self.state, {}
        for e in st["log"]:
            f = e.get("func") or "_"
            pf[f] = pf.get(f, 0) + int(e.get("pts", 0))
        for p in st.get("penal", []):
            f = p.get("func") or "_"
            pf[f] = pf.get(f, 0) - int(p.get("pen", 0))
        for f, n in st.get("bonus", {}).items():
            pf[f] = pf.get(f, 0) + int(n)
        st["pts_func"] = {f: max(0, v) for f, v in pf.items()}
        st["pontos"] = sum(st["pts_func"].values())

    def add_points(self, n=0, fid=None):
        fid = fid or self.emp_id()
        antes = self.state.get("pts_func", {}).get(fid, 0)
        self.recalc_points()
        self.update_placar()
        if self.state["pts_func"].get(fid, 0) > antes:
            self.check_goal(fid)

    def update_placar(self):
        self.placar["dias"][today()] = {"pontos": self.state.get("pontos", 0), "completo": bool(self.state.get("bonus_dia")),
                                        "func": dict(self.state.get("pts_func", {}))}
        save_json(PLACAR_FILE, self.placar)

    @staticmethod
    def week_key(iso):
        y, w, _ = dt.date.fromisoformat(iso).isocalendar()
        return "%d-W%02d" % (y, w)

    @staticmethod
    def _pts(entry, fid):
        if fid is None:
            return entry.get("pontos", 0)
        return entry.get("func", {}).get(fid, 0)

    def week_points(self, fid=None):
        wk = self.week_key(today())
        return sum(self._pts(v, fid) for k, v in self.placar["dias"].items() if self.week_key(k) == wk)

    def total_points(self, fid=None):
        return sum(self._pts(v, fid) for v in self.placar["dias"].values())

    def streak(self, fid=None):
        dias, t, n = self.placar["dias"], today(), 0
        for k in sorted((k for k in dias if k < t), reverse=True):
            e = dias[k]
            if fid is not None and fid not in e.get("func", {}):
                continue                      # folga do funcionário: não conta e não quebra
            if e.get("completo"):
                n += 1
            else:
                break
        e = dias.get(t, {})
        if e.get("completo") and (fid is None or fid in e.get("func", {})):
            n += 1
        return n

    def streak_txt(self, fid=None):
        n = self.streak(fid)
        return "%d dia%s" % (n, "" if n == 1 else "s")

    def score_info(self):
        fid = self.score_fid()
        nivel, prox, falta = nivel_de(self.total_points(fid))
        wk = self.week_key(today())
        return {"pontos": self.state.get("pts_func", {}).get(fid, 0) if fid else self.state.get("pontos", 0),
                "func": self.emp_nome(fid) if fid else "", "sequencia": self.streak(fid), "semana": self.week_points(fid),
                "meta": int(self.cfg.get("meta_semana_pontos", 0) or 0), "premio": self.cfg.get("premio_semana", ""),
                "premio_ganho": (wk if fid is None else wk + ":" + fid) in self.placar["premios"], "nivel": nivel,
                "proximo": prox, "falta": falta}

    def check_goal(self, fid=None):
        try:
            meta = int(self.cfg.get("meta_semana_pontos", 0) or 0)
        except Exception:
            meta = 0
        sf = fid if self.funcionarios() else None
        wk = self.week_key(today())
        key = wk if sf is None else wk + ":" + sf
        if meta <= 0 or key in self.placar["premios"] or self.week_points(sf) < meta:
            return
        self.placar["premios"][key] = today()
        save_json(PLACAR_FILE, self.placar)
        quem = (", " + self.emp_nome(sf)) if sf else ""
        txt = (self.cfg.get("premio_semana") or "Meta batida!") + "  Mostre ao patrão!"
        self.root.after(5000, lambda: self.celebrate("Meta da semana batida%s!" % quem, txt, "tr"))

    def award_day(self):
        """Dia completo: bônus de pontos para quem trabalhou. Devolve um texto para a comemoração."""
        if self.state.get("bonus_dia"):
            return ""
        self.state["bonus_dia"] = True
        self.state["celebrado"] = True
        b = int(self.cfg.get("bonus_dia_completo", 5))
        rec = [f for f, v in self.state.get("pts_func", {}).items() if v > 0] or [self.emp_id()]
        bn = self.state.setdefault("bonus", {})
        for f in rec:
            bn[f] = b
            self.add_points(0, f)
        self.save()
        return "  +%d pontos de bônus%s! Sequência: %s." % (b, " para cada um" if len(rec) > 1 else "", self.streak_txt(self.score_fid()))

    def counts(self):
        st, done, total = self.state, 0, 0
        for i, _ in self.cfg["ao_chegar"]:
            total += 1
            done += 1 if st["am"].get(i) else 0
        for h in self.cfg["horas_caixa"]:
            total += 1
            done += 1 if st["cx"].get(str(h)) else 0
        for r in self.cfg["conferencias"]:
            total += 1
            done += 1 if st["last"].get(r[0]) else 0
        for lid, *_ in lembretes_cfg(self.cfg):
            total += 1
            done += 1 if st["lem"].get(lid) else 0
        return done, total

    def all_done(self):
        done, total = self.counts()
        return total > 0 and done == total

    def after_done(self, kind, arg):
        aw, self.last_award = self.last_award, None
        pts, combo, pen = (aw if aw else (None, 0, 0))
        if kind == "am":
            if all(self.state["am"].get(i) for i, _ in self.cfg["ao_chegar"]) and self.once("am_ok"):
                self.cheer("Ao chegar", "Abertura completa! Que o dia seja ótimo.", pts, combo, pen)
        else:
            self.cheer(self.task_name(kind, arg), None, pts, combo, pen)
        done, total = self.counts()
        if total and done * 2 >= total and not self.state.get("marco50"):
            self.state["marco50"] = True
            self.save()
            self.root.after(2500, lambda: self.cheer("Metade do dia", "Metade das tarefas já está pronta. Continue assim!"))
        self.check_celebrate()

    def check_celebrate(self):
        d = dt.datetime.now()
        m = d.hour * 60 + d.minute
        if self.state.get("bonus_dia") or m < max(self.cfg["horas_caixa"]) * 60 or not self.all_done():
            return
        if any(not self.resolved(p, m) for p in self.pend.values()):
            return
        extra = self.award_day()
        self.avisar_lider("Caixa: dia completo", "Todas as tarefas de hoje foram feitas.", 3)
        base = self.fill_name(random.choice(self.cfg["mensagens_dia_completo"] or ["Parabéns! Tudo certo hoje."]))
        self.celebrate("Dia completo!", base + extra)

    def chime(self, big=False):
        if not self.cfg.get("som"):
            return
        seq = [(784, 90), (988, 90), (1175, 120), (1568, 220)] if big else [(784, 80), (1047, 140)]

        def run():
            try:
                if winsound:
                    for f, d in seq:
                        winsound.Beep(f, d)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def cheer(self, nome, msg=None, pts=None, combo=0, pen=0):
        msg = self.fill_name(msg or random.choice(self.cfg["mensagens_alegres"] or ["Muito bem!"]))
        if pts is not None and self.cfg.get("mostrar_pontos", True):
            msg += "\n%+d pontos" % pts  + (" · demora: -%d" % pen if pen else "")
        self.chime()
        self.card("br", 380, GREEN if not pen else ORANGE, "#FFFFFF", "Concluído · " + nome, msg, [], ms=5000, text_size=13, click_close=True)

    def celebrate(self, title="Dia completo!", text=None, corner="bc"):
        text = text or self.fill_name(random.choice(self.cfg["mensagens_dia_completo"] or ["Parabéns! Tudo certo hoje."]))
        self.chime(True)
        W, H = 540, 170
        win = self.new_win(GREEN)
        cv = tk.Canvas(win, width=W, height=H, bg=GREEN, highlightthickness=0)
        cv.pack()
        cores = ["#FFFFFF", "#FFD23F", "#FF5C9A", "#B8F2E6", "#FFB347"]
        parts = []
        for _ in range(46):
            x, y, sz = random.randint(0, W), random.randint(-H, 0), random.randint(5, 9)
            it = cv.create_rectangle(x, y, x + sz, y + sz, fill=random.choice(cores), outline="")
            parts.append((it, random.uniform(2.0, 4.5), random.uniform(-1.0, 1.0)))
        cv.create_text(W // 2, 56, text=title, font=(FONT, 22, "bold"), fill="#FFFFFF", width=W - 40)
        cv.create_text(W // 2, 108, text=text, font=(FONT, 12), fill="#FFFFFF", width=W - 60)
        bar = tk.Frame(win, bg=GREEN)
        bar.pack(fill="x", pady=(0, 12))
        holder = {}

        def fechar():
            if holder.get("pop"):
                holder["pop"].close()

        def rel():
            fechar()
            self.generate_report()
        for txt, cb in (("Gerar relatório do dia", rel), ("Fechar", fechar)):
            tk.Button(bar, text=txt, command=cb, bg="#FFFFFF", fg=GREEN, activebackground="#FFFFFF",
                      relief="flat", font=(FONT, 10, "bold"), padx=14, pady=5, cursor="hand2").pack(side="left", padx=(18, 0))
        win.update_idletasks()
        pop = self.finish(win, W, win.winfo_reqheight(), corner)
        holder["pop"] = pop
        t0 = time.time()

        def step():
            if pop.closed or time.time() - t0 > 7:
                return
            for it, vy, vx in parts:
                cv.move(it, vx, vy)
                if cv.coords(it)[1] > H:
                    cv.move(it, 0, -H - 20)
            self.root.after(40, step)
        step()
        pop.after_id = self.root.after(30000, pop.close)

    def reports_folder(self):
        f = self.cfg.get("pasta_relatorios") or ""
        if not f:
            desk = os.path.join(os.path.expanduser("~"), "Desktop")
            f = os.path.join(desk if os.path.isdir(desk) else BASE, "Relatorios do Caixa")
        os.makedirs(f, exist_ok=True)
        return f

    def open_path(self, path):
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            log("open_path: " + traceback.format_exc())

    def make_report(self):
        if relatorio is None:
            self.show("Relatório", "O relatório não está disponível: falta o arquivo relatorio.py na mesma pasta.",
                      "tag", 12000, test=True)
            return None
        try:
            self.state["placar_info"] = self.score_info()
            return relatorio.gerar(self.state, self.cfg, self.reports_folder(), BASE)
        except Exception:
            log("relatorio: " + traceback.format_exc())
            self.show("Relatório", "Não consegui gerar o relatório. Veja o arquivo erro.log.", "tag", 12000, test=True)
            return None

    def report_card(self, path, label, text):
        self.card("br", 440, BLUE, "#FFFFFF", label, text,
                  [("Abrir", lambda: self.open_path(path)),
                   ("Abrir pasta", lambda: self.open_path(os.path.dirname(path)))], ms=90000, text_size=13)

    def generate_report(self):
        path = self.make_report()
        if path:
            self.report_card(path, "Relatório pronto", os.path.basename(path))

    def end_of_day(self):
        d = dt.datetime.now()
        self.settle_pendings(d.hour * 60 + d.minute)
        completo = self.all_done()
        extra = self.award_day() if completo and not self.state.get("bonus_dia") else ""
        path = self.make_report()
        if not path:
            return
        self.state["relatorio_gerado"] = True
        self.save()
        self.avisar_lider("Caixa: fim do expediente", "Relatório do dia gerado%s." % ("" if completo else ". Ficaram tarefas sem fazer"), 3)
        mandar = bool(self.cfg.get("email_ativo")) and envio is not None
        if mandar:
            self.queue_email(path, self.state)
        fim = " e enviado por e-mail" if mandar else ""
        if completo and extra:
            self.celebrate("Expediente completo!", "Tudo feito hoje. Parabéns! O relatório foi gerado%s." % fim + extra)
        elif completo:
            self.report_card(path, "Fim do expediente", "Parabéns pelo dia! O relatório foi gerado%s." % fim)
        else:
            self.report_card(path, "Fim do expediente", "O relatório do dia foi gerado%s. Veja o que ficou pendente." % fim)

    # ---- envio do relatório por e-mail (em segundo plano, com nova tentativa)
    def queue_email(self, path, state):
        try:
            dia = dt.date.fromisoformat(state["date"]).strftime("%d/%m/%Y")
        except Exception:
            dia = state.get("date", "")
        assunto = (self.cfg.get("email_assunto") or "Relatório do Caixa - {data}").replace("{data}", dia) \
            .replace("{loja}", self.cfg.get("nome_loja", ""))
        try:
            corpo = relatorio.resumo_texto(state, self.cfg)
        except Exception:
            log("resumo: " + traceback.format_exc())
            corpo = "Segue em anexo o relatório do caixa de %s." % dia
        with self.envio_lock:
            lst = load_json(ENVIOS_FILE, [])
            if not isinstance(lst, list):
                lst = []
            lst = [x for x in lst if x.get("path") != path]
            lst.append({"path": path, "assunto": assunto, "corpo": corpo, "tent": 0, "prox": 0})
            save_json(ENVIOS_FILE, lst)
        self.process_envios()

    def process_envios(self):
        if envio is None or self.envio_busy or not self.cfg.get("email_ativo"):
            return
        with self.envio_lock:
            lst = load_json(ENVIOS_FILE, [])
        if not isinstance(lst, list) or not lst:
            return
        self.envio_busy = True
        threading.Thread(target=self._envio_worker, args=(dict(self.cfg), lst), daemon=True).start()

    def _envio_worker(self, cfg, lst):
        sent, upd = set(), {}
        try:
            for it in lst:
                if it.get("prox", 0) > time.time():
                    continue
                try:
                    envio.enviar(cfg, it["assunto"], it["corpo"], [it["path"]])
                    sent.add(it["path"])
                    self.cmd_q.put(("info", "E-mail enviado", "Relatório enviado: " + os.path.basename(it["path"])))
                except Exception as e:
                    msg = envio.erro_amigavel(e)
                    it["tent"] = it.get("tent", 0) + 1
                    it["prox"] = time.time() + 600
                    it["erro"] = msg
                    log("email tentativa %d: %s | %r" % (it["tent"], msg, e))
                    if it["tent"] == 1:
                        self.cmd_q.put(("info", "E-mail não enviado", msg + " Vou tentar de novo sozinho."))
                    if it["tent"] >= 72:         # cerca de 12 horas
                        sent.add(it["path"])
                        self.cmd_q.put(("info", "E-mail desistido", "Não consegui enviar o relatório %s. Envie à mão." % os.path.basename(it["path"])))
                    else:
                        upd[it["path"]] = it
            with self.envio_lock:
                cur = load_json(ENVIOS_FILE, [])
                out = [upd.get(x["path"], x) for x in (cur if isinstance(cur, list) else []) if x.get("path") not in sent]
                save_json(ENVIOS_FILE, out)
        except Exception:
            log("envio_worker: " + traceback.format_exc())
        finally:
            self.envio_busy = False

    def startup_tasks(self):
        """Ao abrir o app: gera o relatório de um dia que ficou sem (computador desligado) e reenvia e-mails pendentes."""
        try:
            if self.catchup and relatorio is not None and self.cfg.get("gerar_relatorio_no_fim", True):
                prev, self.catchup = self.catchup, None
                path = relatorio.gerar(prev, self.cfg, self.reports_folder(), BASE)
                self.save()                       # grava o estado de hoje por cima do dia antigo
                if path:
                    if self.cfg.get("email_ativo") and envio is not None:
                        self.queue_email(path, prev)
                    self.report_card(path, "Relatório do dia anterior", "O dia %s ficou sem relatório; gerei agora." % prev.get("date", ""))
        except Exception:
            log("catchup: " + traceback.format_exc())
        self.process_envios()

    def on_message(self, c):
        if c[0] == "remoto":
            try:
                self.merge_remoto(c[1], c[2], c[3])
            except Exception:
                log("remoto: " + traceback.format_exc())
        elif c[0] == "loja_arquivo":
            if c[2]:
                self.conectar_loja(c[1], False)
                self.show("Conectado", "Este computador entrou na loja pelo arquivo loja.txt.", "tag", 9000, True)
            else:
                self.open_wizard()
        elif c[0] == "config_remota":
            try:
                self.config_remota(c[1])
            except Exception:
                log("config_remota: " + traceback.format_exc())
        elif c[0] == "pedidos":
            self.on_pedidos(c[1], c[2])
        elif c[0] == "servidor_achado":
            if self.cfg.get("modo_cliente") and "http://" + c[1] != self.cfg.get("nuvem_url"):
                self.cfg["nuvem_url"] = "http://" + c[1]
                save_json(CONFIG_FILE, self.cfg)
                log("servidor principal agora em %s" % c[1])
        elif c[0] == "agenda_remota":
            try:
                self.ag_remota(c[1])
            except Exception:
                log("agenda_remota: " + traceback.format_exc())
        elif c[0] == "validacoes":
            try:
                self.on_validacoes(c[1], c[2])
            except Exception:
                log("validacoes: " + traceback.format_exc())
        elif c[0] == "info":
            self.show(c[1], c[2], "tag", 14000, True)

    # ---- trocar quem está no caixa
    def open_switch(self):
        emps = self.funcionarios()
        if not emps:
            self.show("Funcionários", "Nenhum funcionário cadastrado. Cadastre em Configurações > Funcionários.", "tag", 10000, True)
            return
        w = tk.Toplevel(self.root)
        w.title("Quem está no caixa?")
        w.configure(bg=BG)
        w.attributes("-topmost", True)
        w.geometry("+%d+%d" % (max(60, self.root.winfo_screenwidth() // 2 - 180), 120))
        tk.Label(w, text="Quem está no caixa agora?", font=(FONT, 13, "bold"), bg=BG, fg=INK).pack(padx=24, pady=(18, 8), anchor="w")
        var = tk.StringVar(value=self.state.get("func_manual") or "")
        tk.Radiobutton(w, text="Automático (pelo horário de cada um)", variable=var, value="", bg=BG, font=(FONT, 11),
                       activebackground=BG, anchor="w").pack(fill="x", padx=24)
        for e in emps:
            tk.Radiobutton(w, text=e["nome"], variable=var, value=e["id"], bg=BG, font=(FONT, 11),
                           activebackground=BG, anchor="w").pack(fill="x", padx=24)

        def ok():
            self.set_func_manual(var.get() or None)
            w.destroy()
        row = tk.Frame(w, bg=BG)
        row.pack(fill="x", padx=24, pady=16)
        tk.Button(row, text="OK", command=ok, bg=BLUE, fg="#FFFFFF", relief="flat", font=(FONT, 11, "bold"), padx=22, pady=5,
                  cursor="hand2").pack(side="right")
        tk.Button(row, text="Cancelar", command=w.destroy, relief="flat", font=(FONT, 10), padx=12, pady=5,
                  cursor="hand2").pack(side="right", padx=8)

    # ---- horário só de hoje (campanha, dia diferente) sem mexer na configuração geral
    # ---- agenda: entregas, condicionais, atendimentos, lembretes e avisos para um dia e hora
    def ag_gravar(self, it):
        """Guarda o item (aqui, nos outros computadores e no celular)."""
        it["mod"] = int(time.time() * 1000)
        self.agenda = agenda.limpar(agenda.mesclar(self.agenda, [it]))
        save_json(AGENDA_FILE, self.agenda)
        if self.nuvem is not None and self.nuvem.ativo():
            self.nuvem.escrever([("agenda/" + it["id"], it)])
        self.sync_soon()

    def ag_remota(self, dados):
        if agenda is None or not isinstance(dados, dict):
            return
        antes = json.dumps(self.agenda, sort_keys=True)
        ids_antes = {x["id"] for x in self.agenda}
        prev = {x["id"]: x for x in self.agenda}
        novo = agenda.limpar(agenda.mesclar(self.agenda, list(dados.values())))
        if json.dumps(novo, sort_keys=True) == antes:
            return
        self.agenda = novo
        save_json(AGENDA_FILE, self.agenda)
        self.sync_soon()
        self.ag_atualizar_janela()
        novos = [it for it in novo if it["id"] not in ids_antes]
        for it in novos:
            self.auto_imprimir(it)
        if self.bridge and self.nuvem is not None:         # repassa para a outra sincronização (rede da loja <-> internet)
            self.nuvem.escrever([("agenda/" + it["id"], it) for it in novo if prev.get(it["id"]) != it][-60:])

    def pedido_agenda(self, p):
        """Item novo ou 'feito' vindo do celular. O id vem do pedido, então vários computadores chegam ao mesmo resultado."""
        if agenda is None:
            return False
        try:
            if p.get("op") == "apagar":
                it = next((x for x in self.agenda if x["id"] == str(p.get("id"))), None)
                if not it or it.get("apagado"):
                    return False
                self.ag_fechar(it["id"])
                it = dict(it, apagado=True, mod=int(p.get("ts", 0)) or int(time.time() * 1000))
                self.agenda = agenda.mesclar(self.agenda, [it])
            elif p.get("op") == "feito":
                it = next((x for x in self.agenda if x["id"] == str(p.get("id"))), None)
                if not it or it.get("feito"):
                    return False
                it = dict(it, feito=float(p.get("ts", 0)) / 1000.0 or time.time(), mod=int(p.get("ts", 0)) or int(time.time() * 1000))
                self.agenda = agenda.mesclar(self.agenda, [it])
            else:
                i = p.get("item") or {}
                iid = "a" + re.sub(r"[^A-Za-z0-9]", "", str(p.get("pid", "")))[-9:]
                if any(x["id"] == iid for x in self.agenda):
                    return False
                if i.get("tipo") in agenda.TIPOS_ENTREGA:
                    it = self.item_entrega(i, iid)
                else:
                    it = agenda.criar(agenda.parse_data(i.get("data", "")), agenda.parse_hora(i.get("hora", "")), i.get("tipo", "Aviso"),
                                      i.get("titulo", ""), i.get("detalhe", ""), int(i.get("antes", 0) or 0), id_=iid)
                it["mod"] = int(p.get("ts", 0)) or it["mod"]
                self.agenda = agenda.mesclar(self.agenda, [it])
        except Exception as e:
            log("pedido agenda: %r" % (e,))
            return False
        save_json(AGENDA_FILE, self.agenda)
        if self.nuvem is not None and self.nuvem.ativo():
            self.nuvem.escrever([("agenda/" + it["id"], it)])
        self.sync_soon()
        self.ag_atualizar_janela()
        if p.get("op") not in ("feito", "apagar"):
            self.auto_imprimir(it, recente=False)       # imprime mesmo que o pedido tenha chegado com o computador desligado
        return True

    def lista_vendedores(self):
        """Nomes de vendedores guardados (cadastrados + os que já agendaram), sem repetir."""
        vistos, out = set(), []
        for n in list(self.cfg.get("vendedores_entrega") or []) + [f.get("nome", "") for f in self.cfg.get("funcionarios", [])]:
            n = str(n or "").strip()
            k = agenda.chave_bairro(n) if agenda else n.lower()
            if n and k not in vistos:
                vistos.add(k)
                out.append(n)
        return sorted(out, key=lambda x: x.lower())

    def entregas_cfg(self):
        return {"janelas": list(self.cfg.get("janelas_entrega") or []), "dias": list(self.cfg.get("dias_entrega") or []),
                "vendedores": self.lista_vendedores(),
                "bairros_extra": [dict(e) for e in (self.cfg.get("bairros_extra") or []) if isinstance(e, dict) and e.get("bairro")]}

    def todos_bairros(self):
        """[(nome, info|None)] da tabela de rotas + bairros guardados (sem região)."""
        vistos, out = set(), []
        for b in bairros().values():
            if b["bairro"] not in vistos:
                vistos.add(b["bairro"])
                out.append((b["bairro"], b))
        for e in self.cfg.get("bairros_extra") or []:
            if isinstance(e, dict) and e.get("bairro") and e["bairro"] not in vistos:
                vistos.add(e["bairro"])
                out.append((e["bairro"], None))
        return sorted(out, key=lambda x: agenda.chave_bairro(x[0]))

    def aprender_entrega(self, it):
        """Guarda o vendedor e o bairro novos (que ainda não estavam nas listas) para sugerir da próxima vez."""
        try:
            novo = {}
            v = str(it.get("vendedor") or "").strip()
            if v and agenda.chave_bairro(v) not in {agenda.chave_bairro(x) for x in self.lista_vendedores()}:
                novo["vendedores_entrega"] = list(self.cfg.get("vendedores_entrega") or []) + [v]
            b = str(it.get("bairro") or "").strip()
            extras = list(self.cfg.get("bairros_extra") or [])
            if b and agenda.chave_bairro(b) not in bairros() and agenda.chave_bairro(b) not in {agenda.chave_bairro(e.get("bairro", "")) for e in extras if isinstance(e, dict)}:
                novo["bairros_extra"] = extras + [{"bairro": b}]
            if novo:
                self.apply_config(dict(self.cfg, **novo))
        except Exception:
            log("aprender_entrega: " + traceback.format_exc())

    def item_entrega(self, i, iid=None):
        """Entrega / condicional / troca pedida pelo vendedor. Valida tudo de novo aqui (a página já validou, mas o celular não é de confiança)."""
        def pega(k):
            return str(i.get(k) or "").strip()
        for k, rot in (("cliente", "nome do cliente"), ("endereco", "endereço"), ("bairro", "bairro"), ("telefone", "telefone"), ("vendedor", "vendedor"), ("janela", "horário")):
            if not pega(k):
                raise ValueError("falta " + rot)
        data = agenda.parse_data(pega("data"))
        try:
            janela = agenda.parse_janela(pega("janela"))
            if janela != agenda.QUALQUER and janela not in (self.cfg.get("janelas_entrega") or []):
                janela = agenda.parse_hora(pega("janela").split("-")[0])        # horário fora das janelas: vale como horário específico
        except ValueError:
            janela = agenda.parse_hora(pega("janela"))                         # horário específico (ex.: 14:30)
        if dt.datetime.strptime(data, "%Y-%m-%d").weekday() not in (self.cfg.get("dias_entrega") or []):
            raise ValueError("dia sem entregas")
        tel = re.sub(r"\D", "", pega("telefone"))
        if len(tel) < 10 or len(tel) > 11:
            raise ValueError("telefone inválido")
        tel_fmt = "(%s) %s-%s" % (tel[:2], tel[2:-4], tel[-4:])
        cep = re.sub(r"\D", "", pega("cep"))
        if cep and len(cep) != 8:
            raise ValueError("CEP inválido")
        b = bairros().get(agenda.chave_bairro(pega("bairro")))
        nome_b = b["bairro"] if b else next((e["bairro"] for e in (self.cfg.get("bairros_extra") or []) if isinstance(e, dict)
                                             and agenda.chave_bairro(e.get("bairro", "")) == agenda.chave_bairro(pega("bairro"))), pega("bairro"))
        tipo = i["tipo"]
        det = ["Cliente: %s - Tel: %s" % (pega("cliente"), tel_fmt),
               "Endereço: %s" % pega("endereco"),
               "Bairro: %s%s" % (nome_b, (" (Região %d, %s, ~%s)" % (b["zona"], b["dist"], b["tempo"])) if b else " (fora da tabela de rotas)")]
        if cep:
            det.append("CEP: %s-%s" % (cep[:5], cep[5:]))
        if pega("referencia"):
            det.append("Referência: %s" % pega("referencia"))
        if pega("detalhe"):
            det.append("Obs.: %s" % pega("detalhe"))
        det.append("Vendedor: %s - Horário: %s" % (pega("vendedor"), janela.replace("-", " às ")))
        primeira = sorted(str(j).split("-")[0] for j in (self.cfg.get("janelas_entrega") or ["09:00-11:00"]))[0]
        it = agenda.criar(data, agenda.janela_inicio(janela, primeira), tipo, "%s - %s (%s)" % (tipo, pega("cliente"), nome_b), "\n".join(det)[:800],
                          0 if janela == agenda.QUALQUER else int(self.cfg.get("entrega_antes", 15) or 0), id_=iid,
                          extra={"cliente": pega("cliente"), "bairro": nome_b, "endereco": pega("endereco"), "referencia": pega("referencia"),
                                 "obs": pega("detalhe"), "cep": cep, "telefone": tel_fmt, "vendedor": pega("vendedor"),
                                 "janela": janela, "zona": b["zona"] if b else "", "tempo": b["tempo"] if b else ""})
        self.aprender_entrega(it)
        return it

    def ag_imprimir(self, it):
        """Imprime o endereço da entrega na impressora térmica (Epson TM-T20x)."""
        try:
            import impressao
            alvo = impressao.enviar(self.cfg.get("impressora", ""), impressao.montar_endereco(it, self.cfg.get("impressora_colunas", 48)), "Entrega")
            self.show("Impressão", "Endereço enviado para %s." % alvo, "joy", 3500, True)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Não consegui imprimir", str(e))

    def auto_imprimir(self, it, recente=True):
        """Impressão automática do endereço quando o vendedor agenda (só no computador onde isso está ligado)."""
        if not self.cfg.get("imprimir_auto") or it.get("tipo") not in (agenda.TIPOS_ENTREGA if agenda else []) or not it.get("endereco"):
            return
        if it["id"] in self.impressos or it.get("apagado") or it.get("feito"):
            return
        if recente and time.time() * 1000 - int(it.get("mod", 0)) > 15 * 60 * 1000:
            return                         # item antigo (sincronização ao abrir o programa): não imprime de novo
        self.impressos.add(it["id"])
        save_json(IMPRESSOS_FILE, sorted(self.impressos)[-500:])
        dados = dict(it)
        colunas, nome = self.cfg.get("impressora_colunas", 48), self.cfg.get("impressora", "")

        def trabalho():
            try:
                import impressao
                impressao.enviar(nome, impressao.montar_endereco(dados, colunas), "Entrega")
                self.root.after(0, lambda: self.show("Entrega impressa", "%s - %s (%s)" % (dados["tipo"], dados.get("cliente", ""), dados.get("bairro", "")), "joy", 5000, True))
            except Exception as e:
                msg = str(e)
                self.root.after(0, lambda: self.show("Não consegui imprimir a entrega", "%s. Use \"Imprimir endereço\" na Agenda." % msg, "tag", 12000, True))
        threading.Thread(target=trabalho, daemon=True).start()

    def ag_imprimir_roteiro(self, iso):
        try:
            import impressao
            alvo = impressao.enviar(self.cfg.get("impressora", ""), impressao.montar_roteiro(agenda.roteiro_texto(self.agenda, iso), self.cfg.get("impressora_colunas", 48)), "Roteiro")
            self.show("Impressão", "Roteiro enviado para %s." % alvo, "joy", 3500, True)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Não consegui imprimir", str(e))

    def ag_fechar(self, iid):
        e = self.ag_est.get(iid)
        if e and e.get("pop") and not e["pop"].closed:
            e["pop"].close()
        if e:
            e["pop"] = None

    def ag_feito(self, iid):
        it = next((x for x in self.agenda if x["id"] == iid), None)
        if it:
            self.ag_fechar(iid)
            self.ag_gravar(dict(it, feito=time.time()))
            self.ag_atualizar_janela()

    def ag_adiar(self, iid):
        e = self.ag_est.setdefault(iid, {"next": 0, "pre": False, "n": 0, "pop": None})
        e["next"] = time.time() + self.cfg.get("adiar_minutos", 5) * 60
        self.ag_fechar(iid)

    def ag_mostrar(self, it, pre=False, atraso=0.0):
        e = self.ag_est[it["id"]]
        self.ag_fechar(it["id"])
        corpo = it["titulo"] + ("\n" + it["detalhe"] if it.get("detalhe") else "")
        iid = it["id"]
        if pre:
            self.beep(0)
            e["pop"] = self.card("br", 440, ROXO if it.get("janela") else BLUE, "#FFFFFF", "Daqui a %d min · %s às %s" % (int(it.get("antes", 0)), it["tipo"], it["hora"]), corpo,
                                 [("Ok", None), ("Já fiz", lambda: self.ag_feito(iid))], text_size=14)
            self.avisar_lider("Agenda: %s" % it["tipo"], "Daqui a %d min (%s): %s" % (int(it.get("antes", 0)), it["hora"], corpo), 3)
            return
        cor = RED if atraso >= 15 else (ROXO if it.get("janela") else PINK)
        if atraso >= 15:
            self.alarm(2)
        else:
            self.alarm(1)
        botoes = [("Feito", lambda: self.ag_feito(iid)), ("Adiar %d min" % self.cfg.get("adiar_minutos", 5), lambda: self.ag_adiar(iid))]
        if it.get("endereco"):
            botoes.insert(1, ("Imprimir endereço", lambda: (self.ag_imprimir(it), self.ag_adiar(iid))))
        e["pop"] = self.card("tc", 760, cor, "#FFFFFF", "%s · %s%s" % (it["tipo"], it["hora"], " (atrasado %d min)" % int(atraso) if atraso >= 2 else ""), corpo,
                             botoes,
                             text_size=18)
        self.root.after(0, lambda: self.edge_flash(cor, 4000))
        if e["n"] == 1:
            self.avisar_lider("Agenda: %s agora" % it["tipo"], corpo, 4)

    def tick_agenda(self):
        if agenda is None:
            return
        agora = time.time()
        for it in agenda.da_data(self.agenda, today()):
            if it.get("feito"):
                self.ag_fechar(it["id"])
                continue
            try:
                t = agenda.prazo(it)
            except Exception:
                continue
            e = self.ag_est.setdefault(it["id"], {"next": 0, "pre": False, "n": 0, "pop": None})
            antes = int(it.get("antes", 0) or 0) * 60
            if antes and not e["pre"] and t - antes <= agora < t:
                e["pre"] = True
                self.ag_mostrar(it, pre=True)
            elif agora >= t and agora >= e["next"]:
                e["n"] += 1
                e["next"] = agora + max(1, int(self.cfg.get("repetir_urgente_minutos", 5))) * 60
                self.ag_mostrar(it, atraso=(agora - t) / 60.0)

    def ag_atualizar_janela(self):
        try:
            if self.ag_win is not None and self.ag_win.winfo_exists():
                self.ag_win.recarregar()
        except Exception:
            pass

    def open_agenda(self):
        if agenda is None:
            return
        from tkinter import ttk, messagebox
        if self.ag_win is not None and self.ag_win.winfo_exists():
            self.ag_win.lift()
            self.ag_win.focus_force()
            return
        w = tk.Toplevel(self.root)
        self.ag_win = w
        w.title("Agenda")
        w.configure(bg=BG)
        w.geometry("+%d+%d" % (max(20, self.root.winfo_screenwidth() // 2 - 400), 60))
        edit = {"id": None}
        ENT = list(agenda.TIPOS_ENTREGA)
        V = {"tipo": tk.StringVar(value=ENT[0]), "data": tk.StringVar(), "hora": tk.StringVar(value="14:00"),
             "antes": tk.StringVar(value="15"), "titulo": tk.StringVar()}
        E = {k: tk.StringVar() for k in ("vendedor", "cliente", "tel", "bairro", "end", "ref", "cep", "jan", "esp")}
        V["data"].set(agenda.data_br(today()))
        OUTRO = "Outro horário (digitar)"
        janelas = list(self.cfg.get("janelas_entrega") or []) + [agenda.QUALQUER, OUTRO]
        E["jan"].set(janelas[0])
        w.minsize(920, 600)
        rodape = tk.Frame(w, bg=BG)
        rodape.pack(side="bottom", fill="x", padx=16, pady=(0, 10))
        tk.Button(rodape, text="Fechar", command=w.destroy, relief="flat", font=(FONT, 10), padx=14, pady=4, cursor="hand2").pack(side="right")
        st = ttk.Style(w)
        st.configure("Ag.Treeview", rowheight=28, font=(FONT, 10))
        st.configure("Ag.Treeview.Heading", font=(FONT, 10, "bold"))
        st.configure("TNotebook.Tab", font=(FONT, 11, "bold"), padding=(18, 7))
        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        tab_a, tab_l, tab_r = tk.Frame(nb, bg=BG), tk.Frame(nb, bg=BG), tk.Frame(nb, bg=BG)
        nb.add(tab_a, text="  Agendar  ")
        nb.add(tab_l, text="  Agendados  ")
        nb.add(tab_r, text="  Roteiro do dia  ")
        f = tk.Frame(tab_a, bg=BG)
        f.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(f, text="Novo agendamento", font=(FONT, 12, "bold"), bg=BG, fg=INK).grid(row=0, column=0, columnspan=6, sticky="w")
        tk.Label(f, text="O que é", font=(FONT, 9), bg=BG, fg=GREY).grid(row=1, column=0, sticky="w", pady=(8, 0))
        cb_tipo = ttk.Combobox(f, textvariable=V["tipo"], values=agenda.TIPOS, width=24, state="readonly")
        cb_tipo.grid(row=2, column=0, sticky="w")

        def lab(par, txt, r, c, span=1):
            tk.Label(par, text=txt, font=(FONT, 9), bg=BG, fg=GREY).grid(row=r, column=c, columnspan=span, sticky="w", padx=(0, 8), pady=(8, 0))

        # ---- formulário de ENTREGA / CONDICIONAL / TROCA (igual ao do site dos vendedores)
        fe = tk.Frame(f, bg=BG)
        lab(fe, "Vendedor(a) *", 0, 0)
        cb_vend = ttk.Combobox(fe, textvariable=E["vendedor"], values=self.lista_vendedores(), width=24)
        cb_vend.grid(row=1, column=0, sticky="w", padx=(0, 8))
        lab(fe, "Dia * (dd/mm/aaaa)", 0, 1)
        ttk.Entry(fe, textvariable=V["data"], width=14).grid(row=1, column=1, sticky="w", padx=(0, 8))
        lab(fe, "Horário *", 0, 2)
        cb_jan = ttk.Combobox(fe, textvariable=E["jan"], values=janelas, width=22, state="readonly")
        cb_jan.grid(row=1, column=2, sticky="w")
        lab(fe, "Horário específico (HH:MM)", 0, 3)
        ent_esp = ttk.Entry(fe, textvariable=E["esp"], width=8, state="disabled")
        ent_esp.grid(row=1, column=3, sticky="w", padx=(8, 0))
        lab(fe, "Nome do cliente *", 2, 0)
        ttk.Entry(fe, textvariable=E["cliente"], width=34).grid(row=3, column=0, columnspan=2, sticky="w")
        lab(fe, "Telefone * (DDD + número)", 2, 2)
        ttk.Entry(fe, textvariable=E["tel"], width=20).grid(row=3, column=2, sticky="w")
        lab(fe, "Bairro * (digite o começo: cen, sant...)", 4, 0, 2)
        ent_b = ttk.Entry(fe, textvariable=E["bairro"], width=34)
        ent_b.grid(row=5, column=0, columnspan=2, sticky="w")
        binfo = tk.Label(fe, text="", font=(FONT, 9), bg=BG, fg=GREY, anchor="w", justify="left")
        binfo.grid(row=5, column=2, columnspan=2, sticky="w")
        sug = tk.Listbox(fe, height=0, font=(FONT, 10), exportselection=False, activestyle="none")
        lab(fe, "Endereço * (rua, número, complemento)", 7, 0, 3)
        ttk.Entry(fe, textvariable=E["end"], width=70).grid(row=8, column=0, columnspan=4, sticky="we")
        lab(fe, "Ponto de referência", 9, 0, 2)
        ttk.Entry(fe, textvariable=E["ref"], width=48).grid(row=10, column=0, columnspan=2, sticky="w")
        lab(fe, "CEP (opcional)", 9, 2)
        ttk.Entry(fe, textvariable=E["cep"], width=12).grid(row=10, column=2, sticky="w")
        lab(fe, "Observações", 11, 0, 3)
        obs = tk.Text(fe, height=2, width=70, font=(FONT, 10), wrap="word")
        obs.grid(row=12, column=0, columnspan=4, sticky="we")

        # ---- formulário de lembrete / aviso / atendimento
        fg = tk.Frame(f, bg=BG)
        for c, txt in enumerate(("Dia (dd/mm/aaaa)", "Hora", "Avisar antes (min)")):
            lab(fg, txt, 0, c)
        ttk.Entry(fg, textvariable=V["data"], width=14).grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(fg, textvariable=V["hora"], width=7).grid(row=1, column=1, sticky="w", padx=(0, 8))
        ttk.Combobox(fg, textvariable=V["antes"], values=[str(x) for x in agenda.ANTES], width=6, state="readonly").grid(row=1, column=2, sticky="w")
        lab(fg, "Título (ex.: Ligar para a Maria)", 2, 0, 3)
        ttk.Entry(fg, textvariable=V["titulo"], width=70).grid(row=3, column=0, columnspan=3, sticky="we")
        lab(fg, "Detalhes (o que explicar, telefone...)", 4, 0, 3)
        det = tk.Text(fg, height=4, width=70, font=(FONT, 10), wrap="word")
        det.grid(row=5, column=0, columnspan=3, sticky="we")

        bar = tk.Frame(f, bg=BG)
        bar.grid(row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
        msg = tk.Label(f, text="", font=(FONT, 9), bg=BG, fg=RED, anchor="w", justify="left", wraplength=640)
        msg.grid(row=5, column=0, columnspan=6, sticky="w", pady=(4, 0))

        def mostrar_form(_e=None):
            if V["tipo"].get() in ENT:
                fg.grid_remove()
                fe.grid(row=3, column=0, columnspan=6, sticky="w")
            else:
                fe.grid_remove()
                fg.grid(row=3, column=0, columnspan=6, sticky="w")
            msg.configure(text="")
        cb_tipo.bind("<<ComboboxSelected>>", mostrar_form)

        def jan_mudou(_e=None):
            esp = E["jan"].get() == OUTRO
            ent_esp.configure(state="normal" if esp else "disabled")
            if not esp:
                E["esp"].set("")
        cb_jan.bind("<<ComboboxSelected>>", jan_mudou)

        def sugerir(_e=None):
            t = agenda.chave_bairro(E["bairro"].get())
            exato = bairros().get(t)
            sug.delete(0, "end")
            if exato:
                binfo.configure(text="Região %s · %s · %s" % (exato["zona"], exato["dist"], exato["tempo"]), fg=GREEN)
            elif t:
                binfo.configure(text="Bairro fora da tabela: será guardado para as próximas vezes.", fg=GREY)
            else:
                binfo.configure(text="")
            if len(t) >= 2 and not exato:
                ach = [n for n, _b in self.todos_bairros() if agenda.chave_bairro(n).startswith(t) or (" " + t) in (" " + agenda.chave_bairro(n))][:6]
            else:
                ach = []
            if ach:
                for n in ach:
                    sug.insert("end", n)
                sug.configure(height=len(ach))
                sug.grid(row=6, column=0, columnspan=2, sticky="we")
            else:
                sug.grid_remove()

        def escolher_bairro(_e=None):
            sel = sug.curselection()
            if sel:
                E["bairro"].set(sug.get(sel[0]))
                sug.grid_remove()
                sugerir()
        ent_b.bind("<KeyRelease>", sugerir)
        sug.bind("<<ListboxSelect>>", escolher_bairro)

        # ---------------- aba AGENDADOS: lista com caixa de seleção (☐/☑ = feito)
        fl = tk.Frame(tab_l, bg=BG)
        fl.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(fl, text="Mostrar:", bg=BG, fg=GREY, font=(FONT, 10)).pack(side="left")
        FILTROS = ["Hoje, próximos e atrasados", "Só hoje", "Só amanhã", "Últimos 3 dias e próximos", "Só os não feitos"]
        filtro = tk.StringVar(value=FILTROS[0])
        cbf = ttk.Combobox(fl, textvariable=filtro, values=FILTROS, width=28, state="readonly")
        cbf.pack(side="left", padx=8)
        resumo = tk.Label(fl, text="", bg=BG, fg=GREY, font=(FONT, 10, "bold"))
        resumo.pack(side="right")
        tk.Label(tab_l, text="Clique na caixinha ☐ para marcar como feito (☑). Clique de novo para desmarcar. Dê 2 cliques numa linha para editar.",
                 bg=BG, fg=GREY, font=(FONT, 9)).pack(anchor="w", padx=16)
        cols = ("ok", "quando", "tipo", "cliente", "bairro", "tel", "vend")
        tvf = tk.Frame(tab_l, bg=BG)
        tvf.pack(fill="both", expand=True, padx=16, pady=(6, 4))
        tv = ttk.Treeview(tvf, columns=cols, show="headings", height=12, selectmode="browse", style="Ag.Treeview")
        sbv = ttk.Scrollbar(tvf, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sbv.set)
        for c, t, wd, an in (("ok", "Feito", 56, "center"), ("quando", "Horário", 140, "w"), ("tipo", "Tipo", 130, "w"), ("cliente", "Cliente / assunto", 230, "w"),
                             ("bairro", "Bairro", 130, "w"), ("tel", "Telefone", 120, "w"), ("vend", "Vendedor(a)", 100, "w")):
            tv.heading(c, text=t)
            tv.column(c, width=wd, anchor=an, stretch=(c == "cliente"))
        tv.tag_configure("dia", background="#2D2A4A", foreground="#FFFFFF", font=(FONT, 10, "bold"))
        tv.tag_configure("entrega", background="#F1EAFF")
        tv.tag_configure("atrasado", background="#FDE2E2")
        tv.tag_configure("feito", foreground="#9AA3AF", background="#F3F4F6")
        tv.pack(side="left", fill="both", expand=True)
        sbv.pack(side="right", fill="y")
        msgl = tk.Label(tab_l, text="", font=(FONT, 9), bg=BG, fg=RED, anchor="w", justify="left", wraplength=800)
        msgl.pack(fill="x", padx=16)
        DIAS_P = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

        def nome_dia(iso):
            d = dt.date.fromisoformat(iso)
            h = dt.date.today()
            ref = "Hoje" if d == h else ("Amanhã" if d == h + dt.timedelta(days=1) else ("Ontem" if d == h - dt.timedelta(days=1) else DIAS_P[d.weekday()].capitalize()))
            return "%s · %s" % (ref, agenda.data_br(iso))

        def quando_txt(it):
            if it.get("janela"):
                return agenda.rotulo_janela(it["janela"]).replace(" às ", "–").replace(" (horário específico)", "")
            return it["hora"]

        def recarregar_lista():
            tv.delete(*tv.get_children())
            hoje = today()
            amanha = (dt.date.today() + dt.timedelta(days=1)).isoformat()
            corte = (dt.date.today() - dt.timedelta(days=3)).isoformat()
            agora = time.time()
            modo = filtro.get()
            pend = feitos = 0
            ultimo = None
            itens = []
            for it in sorted(agenda.vivos(self.agenda), key=agenda.chave_roteiro):
                d, fe_ = it["data"], bool(it.get("feito"))
                if modo == FILTROS[0]:
                    ok = d >= hoje or (not fe_ and d >= corte)
                elif modo == FILTROS[1]:
                    ok = d == hoje
                elif modo == FILTROS[2]:
                    ok = d == amanha
                elif modo == FILTROS[3]:
                    ok = d >= corte
                else:
                    ok = not fe_ and d >= corte
                if ok:
                    itens.append(it)
            contagem = {}
            for it in itens:
                contagem[it["data"]] = contagem.get(it["data"], 0) + 1
            for it in itens:
                if it["data"] != ultimo:
                    ultimo = it["data"]
                    tv.insert("", "end", iid="dia-" + ultimo, tags=("dia",), values=("", nome_dia(ultimo) + "   (%d)" % contagem[ultimo], "", "", "", "", ""))
                if it.get("feito"):
                    feitos += 1
                    tag = "feito"
                else:
                    pend += 1
                    atras = it["data"] < hoje or (it["data"] == hoje and agenda.prazo(it) < agora)
                    tag = "atrasado" if atras else ("entrega" if it.get("janela") else "")
                tv.insert("", "end", iid=it["id"], tags=(tag,) if tag else (),
                          values=("☑" if it.get("feito") else "☐", quando_txt(it), it["tipo"], it.get("cliente") or it["titulo"], it.get("bairro", ""),
                                  it.get("telefone", ""), it.get("vendedor", "")))
            resumo.configure(text="%d a fazer · %d feitos" % (pend, feitos))
        filtro.trace_add("write", lambda *_: recarregar_lista())

        def alternar(iid):
            it = next((x for x in self.agenda if x["id"] == iid), None)
            if not it:
                return
            if it.get("feito"):
                self.ag_est.pop(iid, None)
                self.ag_gravar(dict(it, feito=False))
            else:
                self.ag_feito(iid)
            recarregar()

        def clique(e):
            if tv.identify_region(e.x, e.y) == "cell" and tv.identify_column(e.x) == "#1":
                row = tv.identify_row(e.y)
                if row and not row.startswith("dia-"):
                    alternar(row)
                    return "break"
        tv.bind("<Button-1>", clique, add="+")

        # ---------------- aba ROTEIRO DO DIA: por horário, um cliente por linha
        fr = tk.Frame(tab_r, bg=BG)
        fr.pack(fill="x", padx=16, pady=(12, 4))
        rdata = tk.StringVar(value=agenda.data_br(today()))

        def rd_dia():
            try:
                return agenda.parse_data(rdata.get())
            except ValueError:
                return today()

        def mover(n):
            rdata.set(agenda.data_br((dt.date.fromisoformat(rd_dia()) + dt.timedelta(days=n)).isoformat()))
            roteiro_view()
        tk.Button(fr, text="◀", command=lambda: mover(-1), relief="flat", font=(FONT, 11, "bold"), width=3, cursor="hand2").pack(side="left")
        er = ttk.Entry(fr, textvariable=rdata, width=12, font=(FONT, 12, "bold"), justify="center")
        er.pack(side="left", padx=6)
        er.bind("<Return>", lambda _e: roteiro_view())
        tk.Button(fr, text="▶", command=lambda: mover(1), relief="flat", font=(FONT, 11, "bold"), width=3, cursor="hand2").pack(side="left")
        tk.Button(fr, text="Hoje", command=lambda: (rdata.set(agenda.data_br(today())), roteiro_view()), relief="flat", font=(FONT, 10), padx=10, cursor="hand2").pack(side="left", padx=8)
        rres = tk.Label(fr, text="", bg=BG, fg=GREY, font=(FONT, 10, "bold"))
        rres.pack(side="right")
        rtf = tk.Frame(tab_r, bg=BG)
        rtf.pack(fill="both", expand=True, padx=16, pady=(4, 4))
        rtx = tk.Text(rtf, wrap="word", font=(FONT, 11), bg="#FFFFFF", relief="flat", padx=14, pady=10, cursor="arrow", height=16)
        rsb = ttk.Scrollbar(rtf, orient="vertical", command=rtx.yview)
        rtx.configure(yscrollcommand=rsb.set)
        rtx.pack(side="left", fill="both", expand=True)
        rsb.pack(side="right", fill="y")
        rtx.tag_configure("h", font=(FONT, 13, "bold"), foreground="#FFFFFF", background=ROXO, spacing1=12, spacing3=4, lmargin1=4, lmargin2=4)
        rtx.tag_configure("n", font=(FONT, 11, "bold"), foreground=INK)
        rtx.tag_configure("m", foreground=GREY, font=(FONT, 10))
        rtx.tag_configure("e", foreground="#4B5563", font=(FONT, 10), lmargin1=36, lmargin2=36, spacing3=6)
        rtx.tag_configure("f", foreground="#9AA3AF", overstrike=True)
        rtx.tag_configure("box", font=(FONT, 14), foreground=ROXO)

        def roteiro_view():
            iso = rd_dia()
            rtx.configure(state="normal")
            rtx.delete("1.0", "end")
            grupos = agenda.roteiro_grupos(self.agenda, iso)
            tot = sum(len(g) for _r, g in grupos)
            fei = sum(1 for _r, g in grupos for x in g if x.get("feito"))
            rres.configure(text="%d agendamentos · %d feitos" % (tot, fei) if tot else "")
            if not grupos:
                rtx.insert("end", "\nNenhuma entrega, condicional ou troca agendada para %s." % agenda.data_br(iso), "m")
            n = 0
            for rot, its in grupos:
                rtx.insert("end", " %s  (%d) \n" % (rot, len(its)), "h")
                for it in its:
                    n += 1
                    tg = "cb%d" % n
                    rtx.insert("end", "☑ " if it.get("feito") else "☐ ", ("box", tg))
                    rtx.tag_bind(tg, "<Button-1>", lambda _e, i=it["id"]: alternar(i))
                    rtx.tag_bind(tg, "<Enter>", lambda _e: rtx.configure(cursor="hand2"))
                    rtx.tag_bind(tg, "<Leave>", lambda _e: rtx.configure(cursor="arrow"))
                    ft = ("f",) if it.get("feito") else ()
                    rtx.insert("end", it.get("cliente") or it.get("titulo", ""), ("n",) + ft)
                    resto = "   %s · %s%s%s" % (it.get("tipo", ""), (it.get("bairro", "") + (" (R%s)" % it["zona"] if it.get("zona") else "")),
                                                ("  ·  " + it["telefone"]) if it.get("telefone") else "", ("  ·  " + it["vendedor"]) if it.get("vendedor") else "")
                    rtx.insert("end", resto + "\n", ("m",) + ft)
                    end = agenda.linha_endereco(it)
                    if end:
                        rtx.insert("end", end + "\n", ("e",) + ft)
            rtx.configure(state="disabled")

        def recarregar():
            recarregar_lista()
            roteiro_view()
        ordem = []

        def limpar_form():
            edit["id"] = None
            V["tipo"].set(ENT[0])
            V["data"].set(agenda.data_br(today()))
            V["hora"].set("14:00")
            V["antes"].set("15")
            V["titulo"].set("")
            det.delete("1.0", "end")
            obs.delete("1.0", "end")
            vend = E["vendedor"].get()
            for k in E:
                E[k].set("")
            E["vendedor"].set(vend)                 # mantém o vendedor para o próximo cadastro
            E["jan"].set(janelas[0])
            jan_mudou()
            cb_vend.configure(values=self.lista_vendedores())
            sug.grid_remove()
            binfo.configure(text="")
            btn_add.configure(text="Adicionar")
            mostrar_form()

        w.recarregar = recarregar

        def adicionar():
            try:
                if V["tipo"].get() in ENT:
                    jan = E["jan"].get()
                    if jan == OUTRO:
                        if not E["esp"].get().strip():
                            raise ValueError("Digite o horário específico (ex.: 14:30).")
                        jan = E["esp"].get().strip()
                    pedido = {"tipo": V["tipo"].get(), "vendedor": E["vendedor"].get(), "cliente": E["cliente"].get(), "telefone": E["tel"].get(),
                              "bairro": E["bairro"].get(), "endereco": E["end"].get(), "referencia": E["ref"].get(), "cep": E["cep"].get(),
                              "data": V["data"].get(), "janela": jan, "detalhe": obs.get("1.0", "end").strip()}
                    try:
                        novo = self.item_entrega(pedido, edit["id"])
                    except ValueError as ex:
                        t = str(ex)
                        if t.startswith("falta "):
                            t = "Preencha: " + t[6:] + "."
                        elif t == "dia sem entregas":
                            t = "Nesse dia não há entregas (veja os dias em Configurações > Entregas)."
                        elif t == "telefone inválido":
                            t = "Telefone inválido: use DDD + número (10 ou 11 números)."
                        elif t == "CEP inválido":
                            t = "CEP inválido: use 8 números ou deixe vazio."
                        raise ValueError(t)
                else:
                    d = agenda.parse_data(V["data"].get())
                    h = agenda.parse_hora(V["hora"].get())
                    novo = agenda.criar(d, h, V["tipo"].get(), V["titulo"].get(), det.get("1.0", "end"), int(V["antes"].get() or 0), id_=edit["id"])
            except ValueError as ex:
                msg.configure(text=str(ex), fg=RED)
                return
            if edit["id"]:
                self.ag_est.pop(edit["id"], None)
            self.ag_gravar(novo)
            if novo.get("tipo") in ENT and not edit["id"]:
                self.auto_imprimir(novo, recente=False)
            limpar_form()
            recarregar()
            msg.configure(text="Salvo.", fg=GREEN)
            w.after(2500, lambda: msg.configure(text="", fg=RED))

        def selecionado():
            s = tv.selection()
            return next((x for x in self.agenda if s and x["id"] == s[0]), None)

        def editar(_e=None):
            it = selecionado()
            if not it:
                return
            limpar_form()
            edit["id"] = it["id"]
            V["tipo"].set(it["tipo"])
            V["data"].set(agenda.data_br(it["data"]))
            if it["tipo"] in ENT:
                E["vendedor"].set(it.get("vendedor", ""))
                E["cliente"].set(it.get("cliente", ""))
                E["tel"].set(it.get("telefone", ""))
                E["bairro"].set(it.get("bairro", ""))
                E["end"].set(it.get("endereco", ""))
                E["ref"].set(it.get("referencia", ""))
                E["cep"].set(it.get("cep", ""))
                obs.insert("1.0", it.get("obs", ""))
                j = it.get("janela") or ""
                if j in janelas:
                    E["jan"].set(j)
                elif j:
                    E["jan"].set(OUTRO)
                    E["esp"].set(j.split("-")[0])
                jan_mudou()
                sugerir()
                if not it.get("endereco"):
                    msg.configure(text="Esta entrega está sem endereço/dados. Preencha os campos e salve para poder imprimir.", fg=RED)
            else:
                V["hora"].set(it["hora"])
                V["antes"].set(str(it.get("antes", 0)))
                V["titulo"].set(it["titulo"])
                det.insert("1.0", it.get("detalhe", ""))
            btn_add.configure(text="Salvar alteração")
            mostrar_form()
            nb.select(tab_a)

        def marcar():
            it = selecionado()
            if it:
                self.ag_feito(it["id"])

        def excluir():
            it = selecionado()
            if it and messagebox.askyesno("Excluir", "Excluir \"%s\"?" % it["titulo"], parent=w):
                self.ag_fechar(it["id"])
                self.ag_gravar(dict(it, apagado=True))
                if edit["id"] == it["id"]:
                    limpar_form()
                recarregar()
        tv.bind("<Double-1>", lambda e: clique(e) or editar(e))      # 2 cliques na caixinha = marca/desmarca; no resto da linha = editar
        btn_add = tk.Button(bar, text="Adicionar", command=adicionar, bg=BLUE, fg="#FFFFFF", relief="flat", font=(FONT, 10, "bold"), padx=16, pady=4, cursor="hand2")
        btn_add.pack(side="left")
        tk.Button(bar, text="Limpar", command=limpar_form, relief="flat", font=(FONT, 10), padx=10, pady=4, cursor="hand2").pack(side="left", padx=8)
        b2 = tk.Frame(tab_l, bg=BG)
        b2.pack(fill="x", padx=16, pady=(0, 10))
        tk.Button(b2, text="Editar (ou 2 cliques)", command=editar, relief="flat", font=(FONT, 10), padx=10, pady=4, cursor="hand2").pack(side="left")
        def copiar_roteiro():
            iso = rd_dia()
            self.root.clipboard_clear()
            self.root.clipboard_append(agenda.roteiro_texto(self.agenda, iso))
            rres.configure(text="Roteiro de %s copiado. Cole no WhatsApp." % agenda.data_br(iso), fg=GREEN)
        def imprimir_sel():
            it = selecionado()
            if not it:
                msgl.configure(text="Escolha um item da lista para imprimir.", fg=RED)
            elif not it.get("endereco"):
                msgl.configure(text="Esse item não tem endereço. Dê 2 cliques nele, preencha o endereço e salve.", fg=RED)
            else:
                msgl.configure(text="")
                self.ag_imprimir(it)

        def imprimir_dia():
            self.ag_imprimir_roteiro(rd_dia())
        tk.Button(b2, text="Imprimir endereço", command=imprimir_sel, bg=BLUE, fg="#FFFFFF", relief="flat", font=(FONT, 10, "bold"), padx=10, pady=4, cursor="hand2").pack(side="left", padx=(8, 0))
        tk.Button(b2, text="Excluir", command=excluir, relief="flat", font=(FONT, 10), padx=10, pady=4, cursor="hand2").pack(side="left", padx=8)
        br = tk.Frame(tab_r, bg=BG)
        br.pack(fill="x", padx=16, pady=(0, 10))
        tk.Button(br, text="Imprimir roteiro do dia", command=imprimir_dia, bg=BLUE, fg="#FFFFFF", relief="flat", font=(FONT, 10, "bold"), padx=14, pady=5, cursor="hand2").pack(side="left")
        tk.Button(br, text="Copiar para o WhatsApp", command=copiar_roteiro, relief="flat", font=(FONT, 10), padx=12, pady=5, cursor="hand2").pack(side="left", padx=8)
        recarregar()
        mostrar_form()
        tema.polir(w)

    def open_hoje(self):
        hoje = dt.date.today()
        iso = hoje.isoformat()
        s = self.day_sched(hoje)
        w = tk.Toplevel(self.root)
        w.title("Horário de hoje")
        w.configure(bg=BG)
        w.attributes("-topmost", True)
        w.geometry("+%d+%d" % (max(60, self.root.winfo_screenwidth() // 2 - 220), 100))
        tk.Label(w, text="Horário só de hoje (%s)" % hoje.strftime("%d/%m"), font=(FONT, 14, "bold"), bg=BG, fg=INK).pack(padx=24, pady=(18, 2), anchor="w")
        tk.Label(w, text="Vale apenas para hoje. Amanhã volta ao horário normal.", font=(FONT, 10), bg=BG, fg=GREY).pack(padx=24, anchor="w")
        fechado = tk.BooleanVar(value=not bool(s.get("aberto", True)))
        tk.Checkbutton(w, text="A loja está fechada hoje", variable=fechado, bg=BG, activebackground=BG, font=(FONT, 11)).pack(padx=24, pady=(10, 4), anchor="w")
        g = tk.Frame(w, bg=BG)
        g.pack(padx=24, pady=4, anchor="w")
        ao, ta = s.get("ao_chegar") or ["09:00", "10:30"], s.get("tarde") or ["13:00", "19:00"]
        campos = {}
        for r, (rot, k, val) in enumerate([("Ao chegar: começa", "a0", ao[0]), ("Ao chegar: termina", "a1", ao[1]),
                                           ("Tarde: começa", "p0", ta[0]), ("Fecha às", "p1", ta[1])]):
            tk.Label(g, text=rot, bg=BG, font=(FONT, 11)).grid(row=r, column=0, sticky="w", pady=3)
            campos[k] = tk.StringVar(value=val)
            tk.Entry(g, textvariable=campos[k], width=8, font=(FONT, 12)).grid(row=r, column=1, padx=12)
        erro = tk.StringVar()
        tk.Label(w, textvariable=erro, bg=BG, fg=RED, font=(FONT, 10), wraplength=380, justify="left").pack(padx=24, anchor="w")

        def salvar():
            try:
                def hm(t):
                    t = t.strip()
                    h, m = t.split(":")
                    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
                        raise ValueError
                    return "%02d:%02d" % (int(h), int(m))
                a0, a1, p0, p1 = (hm(campos[k].get()) for k in ("a0", "a1", "p0", "p1"))
                if not fechado.get() and not (hm_to_min(a0) < hm_to_min(a1) <= hm_to_min(p0) < hm_to_min(p1)):
                    erro.set("Horários fora de ordem. Use: chegada < fim da chegada <= volta < fechamento.")
                    return
            except Exception:
                erro.set("Use o formato HH:MM, por exemplo 09:00.")
                return
            novo = json.loads(json.dumps(self.cfg))
            novo["excecoes"] = [x for x in novo.get("excecoes", []) if x.get("id") != "hoje-" + iso]
            novo["excecoes"].append({"id": "hoje-" + iso, "nome": "Hoje", "de": iso, "ate": iso, "aberto": not fechado.get(),
                                     "ao_chegar": [a0, a1], "tarde": [p0, p1], "horas": []})
            self.apply_config(novo)
            self.show("Horário de hoje", "Pronto. Hoje: %s e %s às %s." % (a0, p0, p1) if not fechado.get() else "Loja marcada como fechada hoje.", "tag", 8000, True)
            w.destroy()

        def normal():
            novo = json.loads(json.dumps(self.cfg))
            novo["excecoes"] = [x for x in novo.get("excecoes", []) if x.get("id") != "hoje-" + iso]
            self.apply_config(novo)
            w.destroy()
        row = tk.Frame(w, bg=BG)
        row.pack(fill="x", padx=24, pady=14)
        tk.Button(row, text="Salvar", command=salvar, bg=BLUE, fg="#FFFFFF", relief="flat", font=(FONT, 11, "bold"), padx=22, pady=5, cursor="hand2").pack(side="right")
        tk.Button(row, text="Cancelar", command=w.destroy, relief="flat", font=(FONT, 10), padx=12, pady=5, cursor="hand2").pack(side="right", padx=8)
        if any(x.get("id") == "hoje-" + iso for x in self.cfg.get("excecoes", [])):
            tk.Button(row, text="Voltar ao normal", command=normal, relief="flat", font=(FONT, 10), padx=8, pady=5, cursor="hand2").pack(side="left")

    # ---- quem está no caixa: pergunta no começo do dia e na troca de turno
    def pedir_funcionario(self, titulo="Quem está no caixa agora?"):
        emps = self.funcionarios()
        if not emps:
            return
        try:
            if getattr(self, "quem_win", None) is not None and self.quem_win.winfo_exists():
                self.quem_win.lift()
                return
        except tk.TclError:
            pass
        atual = self.current_emp()
        w = self.quem_win = tk.Toplevel(self.root)
        w.title("Quem está no caixa?")
        w.configure(bg=BG)
        w.attributes("-topmost", True)
        w.geometry("+%d+%d" % (max(40, self.root.winfo_screenwidth() // 2 - 200), 110))
        tk.Label(w, text=titulo, font=(FONT, 16, "bold"), bg=BG, fg=INK).pack(padx=30, pady=(22, 4), anchor="w")
        tk.Label(w, text="Toque no seu nome. Os pontos e as tarefas ficam no seu nome.", font=(FONT, 10), bg=BG, fg=GREY).pack(padx=30, anchor="w")

        def escolher(e):
            self.set_func_manual(e["id"])
            self.state["func_confirmado"] = True
            self.save()
            self.show("Bom trabalho, %s!" % e["nome"].split()[0], "Você está no caixa agora.", "tag", 6000, True)
            w.destroy()
        for e in emps:
            sug = atual is not None and e["id"] == atual["id"]
            tk.Button(w, text=e["nome"] + ("   (turno agora)" if sug else ""), command=lambda e=e: escolher(e),
                      font=(FONT, 15, "bold"), bg=PINK if sug else INK, fg="#FFFFFF", activebackground=BLUE, activeforeground="#FFFFFF",
                      relief="flat", cursor="hand2", padx=20, pady=12).pack(fill="x", padx=30, pady=(12, 0))
        tk.Button(w, text="Agora não", command=w.destroy, relief="flat", font=(FONT, 10), bg=BG, fg=GREY, cursor="hand2").pack(pady=(12, 16))

    def checar_quem(self, d):
        """Pergunta quem está no caixa ao abrir o programa e no começo do turno de cada funcionário."""
        if not self.funcionarios() or not self.day_open:
            return
        m = d.hour * 60 + d.minute
        if not self.state.get("func_confirmado") and self.once("quem-inicio"):
            self.pedir_funcionario()
            return
        for e in self.funcionarios():
            sh = self.shift_of(e, d.weekday())
            if sh and m == sh[0] and self.once("turno-" + e["id"]):
                self.pedir_funcionario("Começou o turno de %s. Quem está no caixa?" % e["nome"].split()[0])
                return

    # ---- pausa "cliente na frente"
    def set_hold(self, on):
        if on:
            self.hold_until = time.time() + self.cfg["pausa_atendimento_minutos"] * 60
            self.state["pausas"] = self.state.get("pausas", 0) + 1
            self.save()
        else:
            self.hold_until = 0
            items, self.queue_hold = self.queue_hold[:2], []
            for i, (label, text, fmt, ms) in enumerate(items):
                self.root.after(6000 + i * 8000, lambda a=(label, text, fmt, ms): self.show(*a))
        self.refresh()

    def tick_hold(self):
        if self.hold_until and time.time() >= self.hold_until:
            self.set_hold(False)

    # ---- bandeja do Windows
    def start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            self.tray = None
            self.make_pill()
            return
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.polygon([(16, 6), (58, 6), (58, 58), (16, 58), (4, 32)], fill=(224, 36, 111, 255))
        d.ellipse([16, 26, 26, 36], fill=(255, 255, 255, 255))
        put = lambda c: (lambda icon=None, item=None: self.cmd_q.put(c))
        menu = pystray.Menu(
            pystray.MenuItem("Abrir checklist", put("open"), default=True),
            pystray.MenuItem("Cliente na frente (pausar avisos)", put("hold")),
            pystray.MenuItem("Trocar funcionário", put("switch")),
            pystray.MenuItem("Agenda", put("agenda")),
            pystray.MenuItem("Horário de hoje", put("hoje")),
            pystray.MenuItem("Configurações", put("settings")),
            pystray.MenuItem("Ver os formatos de aviso", put("test")),
            pystray.MenuItem("Gerar relatório do dia", put("report")),
            pystray.MenuItem("Sair", put("quit")),
        )
        self.tray = pystray.Icon("caixa", img, "Painel do Caixa", menu)
        self.tray.run_detached()

    def make_pill(self):
        """Sem bandeja: um botãozinho discreto no canto para abrir o checklist."""
        win = self.new_win(INK)
        tk.Button(win, text="Caixa", command=self.open_window, bg=INK, fg="#FFFFFF", relief="flat",
                  font=(FONT, 9, "bold"), cursor="hand2", padx=8, pady=2).pack()
        win.update_idletasks()
        noactivate(win)
        l, t, r, b = work_area(self.root)
        win.geometry("+%d+%d" % (l + 4, b - 34))
        win.deiconify()
        win.attributes("-topmost", True)

    def process_cmds(self):
        while True:
            try:
                c = self.cmd_q.get_nowait()
            except queue.Empty:
                return
            if isinstance(c, tuple):
                self.on_message(c)
                continue
            if c == "open":
                self.open_window()
            elif c == "hold":
                self.set_hold(not self.holding())
            elif c == "test":
                self.demo()
            elif c == "report":
                self.generate_report()
            elif c == "settings":
                self.open_settings()
            elif c == "switch":
                self.open_switch()
            elif c == "hoje":
                self.open_hoje()
            elif c == "agenda":
                self.open_agenda()
            elif c == "quem":
                self.pedir_funcionario()
            elif c == "quit":
                self.quit()

    def demo(self):
        ex = {"tag": "Sorria para o cliente", "banner": "Confira o troco antes de entregar",
              "edge": "Atenção ao receber", "ask": "Tem mercadoria para tirar etiquetas?",
              "blink": "Limpe o balcão e o caixa", "joy": "Seu sorriso muda o dia de quem chega na loja!"}
        for i, f in enumerate(("tag", "banner", "edge", "ask", "blink", "joy")):
            self.root.after(i * 2800, lambda f=f: self.show("Teste · " + f, ex[f], f, 5000, True))

    def quit(self):
        try:
            if self.local is not None:
                self.local.sair()
        except Exception:
            pass
        try:
            if self.nuvem is not None:
                self.nuvem.sair()
        except Exception:
            pass
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.root.destroy()

    # ---- janela do checklist
    def open_window(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.deiconify()
            self.win.lift()
            self.refresh()
            return
        w = tk.Toplevel(self.root)
        self.win = w
        w.title("Painel do Caixa")
        h = max(420, min(880, w.winfo_screenheight() - 100))
        w.geometry("680x%d+40+20" % h)
        w.minsize(560, 420)
        w.configure(bg=BG)
        w.protocol("WM_DELETE_WINDOW", w.withdraw)
        W = self.w = {"am": {}, "cx": {}, "conf": {}, "lem": {}, "lem_btn": {}}

        # --- aparência (cores e degradê escolhidos em Configurações > Aparência)
        c1, c2, dg = tema.cores(self.cfg)
        mid = tema.cor_media(self.cfg)
        escuro = tema.luminosidade(mid) < 0.45
        fundo_txt = "#E8EDF5" if escuro else GREY
        borda = tema.escurece(mid, 0.10) if not escuro else "#46526A"
        SOFT = "#EEF2F8"
        solido = c1 if dg == "nenhum" else mid
        w.configure(bg=solido)

        def botao(pai, texto, cmd, tipo="suave", **kw):
            cores_ = {"escuro": (INK, "#FFFFFF"), "roxo": (ROXO, "#FFFFFF"), "azul": (BLUE, "#FFFFFF"),
                      "suave": (SOFT, BLUE), "neutro": (SOFT, INK)}
            bgc, fgc = cores_[tipo]
            opts = dict(text=texto, command=cmd, font=(FONT, 10, "bold"), relief="flat", bd=0, bg=bgc, fg=fgc,
                        activebackground=bgc, activeforeground=fgc, cursor="hand2", padx=14, pady=5)
            opts.update(kw)
            return tk.Button(pai, **opts)

        def cartao(pai, cor=None):
            f = tk.Frame(pai, bg=PAPER, highlightbackground=borda, highlightthickness=1)
            if cor:
                tk.Frame(f, width=5, bg=cor).pack(side="left", fill="y")
            corpo = tk.Frame(f, bg=PAPER)
            corpo.pack(side="left", fill="both", expand=True)
            return f, corpo

        # --- topo fixo: relógio, pausa, placar (cada bloco num cartão)
        topc = tk.Canvas(w, bg=solido, highlightthickness=0, height=10)
        topc.pack(side="top", fill="x")
        g1 = topc.create_image(0, 0, anchor="nw")
        topc.tag_lower(g1)
        ptop = tema.Pilha(topc, ao_medir=lambda y: topc.configure(height=y - 4) if int(topc.cget("height")) != y - 4 else None)

        c_top, top = cartao(topc, PINK)
        ptop.add(c_top)
        row1 = tk.Frame(top, bg=PAPER)
        row1.pack(fill="x", padx=14, pady=(8, 0))
        left = tk.Frame(row1, bg=PAPER)
        left.pack(side="left")
        W["date"] = tk.Label(left, text="", font=(FONT, 10), bg=PAPER, fg=GREY, anchor="w")
        W["date"].pack(fill="x")
        W["clock"] = tk.Label(left, text="", font=(FONT, 38, "bold"), bg=PAPER, fg=INK, anchor="w")
        W["clock"].pack(fill="x")
        W["phase"] = tk.Label(left, text="", font=(FONT, 11, "bold"), bg=PAPER, fg=INK, anchor="w")
        W["phase"].pack(fill="x")
        W["emp"] = tk.Label(left, text="", font=(FONT, 10), bg=PAPER, fg=BLUE, anchor="w")
        W["emp"].pack(fill="x")
        right = tk.Frame(row1, bg=PAPER)
        right.pack(side="right", anchor="ne")
        botao(right, "Relatório do dia", self.generate_report, "escuro").pack(fill="x", pady=(0, 4))
        botao(right, "Configurações", self.open_settings, "neutro").pack(fill="x")
        botao(right, "Agenda (entregas e avisos)", self.open_agenda, "roxo").pack(fill="x", pady=(4, 0))
        botao(right, "Horário de hoje", self.open_hoje, "suave").pack(fill="x", pady=(4, 0))
        W["btn_emp"] = botao(right, "Trocar funcionário", self.open_switch, "suave")
        W["hold"] = tk.Button(top, text="", command=lambda: self.set_hold(not self.holding()), font=(FONT, 12, "bold"),
                              relief="flat", bd=0, cursor="hand2", pady=9)
        W["hold"].pack(fill="x", padx=14, pady=(10, 12))

        c_pf, pf = cartao(topc, ROXO)
        ptop.add(c_pf)
        W["pts"] = tk.Label(pf, text="", font=(FONT, 13, "bold"), bg=PAPER, fg=INK, anchor="w")
        W["pts"].pack(fill="x", padx=12, pady=(8, 0))
        W["nivel"] = tk.Label(pf, text="", font=(FONT, 9), bg=PAPER, fg=GREY, anchor="w")
        W["nivel"].pack(fill="x", padx=12)
        W["bar"] = tk.Canvas(pf, height=12, bg="#E9EDF2", highlightthickness=0)
        W["bar"].pack(fill="x", padx=12, pady=(6, 2))
        W["week"] = tk.Label(pf, text="", font=(FONT, 9), bg=PAPER, fg=GREY, anchor="w")
        W["week"].pack(fill="x", padx=12, pady=(0, 4))
        W["prog"] = tk.Label(pf, text="", font=(FONT, 10), bg=PAPER, fg=GREY, anchor="w")
        W["prog"].pack(fill="x", padx=12, pady=(0, 8))

        W["stats"] = tk.Label(w, text="", font=("Consolas", 9), bg=solido, fg=fundo_txt, anchor="w")
        W["stats"].pack(side="bottom", fill="x", padx=18, pady=6)

        # --- área com rolagem (os cartões flutuam sobre o fundo)
        body = tk.Frame(w, bg=solido)
        body.pack(fill="both", expand=True)
        cv = tk.Canvas(body, bg=solido, highlightthickness=0)
        sb = tk.Scrollbar(body, orient="vertical", command=cv.yview)
        g2 = cv.create_image(0, 0, anchor="nw")
        cv.tag_lower(g2)

        def rolou(a, b):
            sb.set(a, b)
            cv.coords(g2, 0, cv.canvasy(0))
        cv.configure(yscrollcommand=rolou)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)

        def medido(y):
            cv.configure(scrollregion=(0, 0, max(1, cv.winfo_width()), y))
        pila = tema.Pilha(cv, ao_medir=medido)
        imgs = {}

        def pintar():
            imgs["t"] = None
            try:
                if not w.winfo_exists():
                    return
                LW, LH = w.winfo_width(), w.winfo_height()
                full = tema.imagem_degrade(tk, LW, LH, c1, c2, dg)
                if full is None:
                    return
                ht = max(1, topc.winfo_height())
                p1, p2 = tk.PhotoImage(), tk.PhotoImage()
                p1.tk.call(p1, "copy", full, "-from", 0, 0, LW, min(ht, LH))
                p2.tk.call(p2, "copy", full, "-from", 0, min(ht, LH - 1), LW, LH)
                imgs["p"] = (full, p1, p2)
                topc.itemconfigure(g1, image=p1)
                cv.itemconfigure(g2, image=p2)
                cv.coords(g2, 0, cv.canvasy(0))
            except Exception:
                pass

        def repintar(e=None):
            if e is not None and e.widget is not w and e.widget is not topc:
                return
            if imgs.get("t"):
                try:
                    w.after_cancel(imgs["t"])
                except Exception:
                    pass
            imgs["t"] = w.after(150, pintar)
        w.bind("<Configure>", repintar, add="+")
        topc.bind("<Configure>", repintar, add="+")
        w.after(250, pintar)

        def wheel(e):
            step = -1 if (getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4) else 1
            cv.yview_scroll(step * 2, "units")
        w.bind("<MouseWheel>", wheel)
        w.bind("<Button-4>", wheel)
        w.bind("<Button-5>", wheel)

        def section(title, hours, cor=PINK):
            f, corpo = cartao(cv, cor)
            pila.add(f)
            hdr = tk.Frame(corpo, bg=PAPER)
            hdr.pack(fill="x", padx=14, pady=(10, 4))
            tk.Label(hdr, text=title.upper(), font=(FONT, 15, "bold"), bg=PAPER, fg=INK).pack(side="left")
            tk.Label(hdr, text=hours, font=("Consolas", 10), bg=SOFT, fg=GREY, padx=8, pady=1).pack(side="left", padx=10)
            return corpo
        a, p = self.cfg["ao_chegar_horario"], self.cfg["tarde_horario"]
        fa = section("Ao chegar", "%s – %s" % tuple(a), ORANGE)
        for iid, name in self.cfg["ao_chegar"]:
            var = tk.BooleanVar(value=bool(self.state["am"].get(iid)))
            tk.Checkbutton(fa, text=name, variable=var, font=(FONT, 13), bg=PAPER, activebackground=PAPER,
                           anchor="w", cursor="hand2", command=lambda i=iid, v=var: self.set_am(i, v.get())).pack(fill="x", padx=14, pady=2)
            W["am"][iid] = var
        tk.Frame(fa, height=6, bg=PAPER).pack()

        fp = section("Tarde", "%s – %s" % tuple(p), BLUE)
        tk.Label(fp, text="CAIXA DE HORA EM HORA", font=(FONT, 8, "bold"), bg=PAPER, fg=GREY, anchor="w").pack(fill="x", padx=14)
        chips = tk.Frame(fp, bg=PAPER)
        chips.pack(fill="x", padx=14, pady=(2, 8))
        for hh in self.cfg["horas_caixa"]:
            b = tk.Button(chips, text="", font=(FONT, 10, "bold"), relief="flat", bd=0, cursor="hand2", width=12, pady=6,
                          command=lambda hh=hh: self.toggle_cx(hh))
            b.pack(side="left", padx=3)
            W["cx"][hh] = b
        tk.Label(fp, text="CONFERÊNCIAS DO DIA", font=(FONT, 8, "bold"), bg=PAPER, fg=GREY, anchor="w").pack(fill="x", padx=14)
        for cid, name, note in self.cfg["conferencias"]:
            row = tk.Frame(fp, bg=PAPER)
            row.pack(fill="x", padx=14, pady=4)
            lf = tk.Frame(row, bg=PAPER)
            lf.pack(side="left", fill="x", expand=True)
            tk.Label(lf, text=name, font=(FONT, 13, "bold"), bg=PAPER, fg=INK, anchor="w").pack(fill="x")
            if note:
                tk.Label(lf, text=note, font=(FONT, 9), bg=PAPER, fg=GREY, anchor="w", wraplength=360, justify="left").pack(fill="x")
            st = tk.Label(lf, text="", font=("Consolas", 9), bg=PAPER, fg=GREY, anchor="w")
            st.pack(fill="x")
            botao(row, "Conferi", lambda c=cid: self.set_conf(c), "azul", font=(FONT, 11, "bold"), padx=16, pady=6).pack(side="right")
            W["conf"][cid] = st
        tk.Frame(fp, height=6, bg=PAPER).pack()

        lems = lembretes_cfg(self.cfg)
        if lems:
            fl = section("Lembretes", "maquininha e outros", ROXO)
            for lid, mn, nome, texto, curto in lems:
                row = tk.Frame(fl, bg=PAPER)
                row.pack(fill="x", padx=14, pady=4)
                lf = tk.Frame(row, bg=PAPER)
                lf.pack(side="left", fill="x", expand=True)
                tk.Label(lf, text=nome, font=(FONT, 13, "bold"), bg=PAPER, fg=INK, anchor="w").pack(fill="x")
                st = tk.Label(lf, text="", font=("Consolas", 9), bg=PAPER, fg=GREY, anchor="w")
                st.pack(fill="x")
                bt = botao(row, "Feito", lambda i=lid: self.set_lem(i), "azul", font=(FONT, 11, "bold"), padx=16, pady=6)
                bt.pack(side="right")
                W["lem"][lid] = st
                W["lem_btn"][lid] = bt
            tk.Frame(fl, height=6, bg=PAPER).pack()
        tema.polir(w)
        self.refresh()

    def set_am(self, iid, val):
        if val:
            self.record("am", iid, "lista")
            self.state["am"][iid] = time.time()
        else:
            self.unrecord("am", iid)
            self.state["am"][iid] = 0
        self.save()
        self.refresh()
        if val:
            self.after_done("am", iid)

    def toggle_cx(self, h):
        k = str(h)
        if self.state["cx"].get(k):
            self.unrecord("cx", h)
            self.state["cx"][k] = 0
        else:
            self.record("cx", h, "lista")
            self.state["cx"][k] = time.time()
        self.save()
        self.refresh()
        if self.state["cx"].get(k):
            self.after_done("cx", h)

    def set_lem(self, lid):
        if self.state["lem"].get(lid):
            self.unrecord("lem", lid)
            self.state["lem"][lid] = 0
        else:
            self.record("lem", lid, "lista")
            self.state["lem"][lid] = time.time()
        self.save()
        self.refresh()
        if self.state["lem"].get(lid):
            self.after_done("lem", lid)

    def set_conf(self, cid):
        # anti-spam: sem aviso pendente, repetir a mesma conferência logo em seguida não vale nada
        pid = "conf-%s" % cid
        espera = int(self.cfg.get("conferencia_espera_minutos", 30))
        ult = self.state["last"].get(cid) or 0
        if pid not in self.pend and ult and time.time() - ult < espera * 60:
            falta = int(espera - (time.time() - ult) / 60.0) + 1
            self.show("Já conferido", "Essa conferência foi feita às %s. Só vale de novo daqui a uns %d min, ou quando o aviso aparecer."
                      % (dt.datetime.fromtimestamp(ult).strftime("%H:%M"), falta), "tag", 7000, True)
            return
        self.record("conf", cid, "lista")
        self.state["last"][cid] = time.time()
        self.conf_gate_until = time.time() + self.cfg["intervalo_entre_conferencias_minutos"] * 60
        self.save()
        self.refresh()
        self.after_done("conf", cid)

    def refresh(self):
        try:
            if self.win is not None and not self.win.winfo_exists():
                self.win = None
        except tk.TclError:
            return
        if self.win is None or not self.w:
            return
        W = self.w
        d = dt.datetime.now()
        m = d.hour * 60 + d.minute
        ph = self.phase(m)
        meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
        dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        W["date"].config(text="CAIXA · %s%s, %d de %s" % (dias[d.weekday()], "-feira" if d.weekday() < 5 else "", d.day, meses[d.month - 1]))
        W["clock"].config(text=d.strftime("%H:%M"))
        W["phase"].config(text={"pre": "Antes de abrir", "am": "Ao chegar", "lunch": "Almoço", "pm": "Tarde", "end": "Expediente encerrado", "closed": "Loja fechada hoje"}[ph])
        for iid, var in W["am"].items():
            var.set(bool(self.state["am"].get(iid)))
        for h, b in W["cx"].items():
            ts = self.state["cx"].get(str(h))
            if ts:
                b.config(text="%dh · %s" % (h, hm(ts)), bg=GREEN, fg="#FFFFFF")
            elif ph == "pm" and h * 60 <= m < h * 60 + 60:
                b.config(text="%dh · conferir" % h, bg=PINK, fg="#FFFFFF")
            elif ph in ("pm", "end") and m >= h * 60 + 60:
                b.config(text="%dh · faltou" % h, bg="#FFF1DD", fg="#B25E00")
            else:
                b.config(text="%dh" % h, bg="#E9EDF2", fg=GREY)
        for cid, lbl in W["conf"].items():
            last = self.state["last"].get(cid)
            if last:
                t = "última às %s · há %s" % (hm(last), ago_txt(time.time() - last))
            else:
                t = "ainda não conferido hoje" if ph in ("pm", "end") else "conferir a partir de %s" % self.cfg["tarde_horario"][0]
            stale = ph == "pm" and self.is_stale(cid, m)
            lbl.config(text=t + (" · conferir de novo" if stale and last else ""), fg="#B25E00" if stale else GREY)
        for lid, mn, nome, texto, curto in lembretes_cfg(self.cfg):
            lbl, bt = W["lem"].get(lid), W["lem_btn"].get(lid)
            if lbl is None:
                continue
            ts = self.state["lem"].get(lid)
            if ts:
                lbl.config(text="feito às %s" % hm(ts), fg=GREEN)
                bt.config(text="Desfazer", bg="#E9EDF2", fg=GREY)
            elif m >= mn and ph in ("am", "pm", "end"):
                lbl.config(text="pendente desde %02d:%02d" % (mn // 60, mn % 60), fg="#B25E00")
                bt.config(text="Feito", bg=BLUE, fg="#FFFFFF")
            else:
                lbl.config(text="às %02d:%02d" % (mn // 60, mn % 60), fg=GREY)
                bt.config(text="Feito", bg=BLUE, fg="#FFFFFF")
        done, total = self.counts()
        W["prog"].config(text="%d de %d tarefas do dia" % (done, total))
        if self.holding():
            left = int(self.hold_until - time.time())
            W["hold"].config(text="Atendendo · avisos em pausa (%d:%02d) · toque para voltar" % (left // 60, left % 60), bg=BLUE, fg="#FFFFFF")
        else:
            W["hold"].config(text="Cliente na frente (pausar avisos %d min)" % self.cfg["pausa_atendimento_minutos"], bg="#EEF2F8", fg=BLUE)
        W["stats"].config(text="Avisos hoje: %d · Confirmados: %d" % (self.state["shown"], self.state["ok"]))
        # placar
        emp = self.current_emp()
        W["emp"].config(text=("No caixa agora: %s%s" % (emp["nome"], " (escolhido à mão)" if self.state.get("func_manual") else "")) if emp else "")
        if emp:
            W["btn_emp"].pack(fill="x", pady=(4, 0))
        else:
            W["btn_emp"].pack_forget()
        if self.cfg.get("mostrar_pontos", True):
            si = self.score_info()
            W["pts"].config(text="%sHoje: %d pontos  ·  Sequência: %s" % (si["func"] + " · " if si["func"] else "", si["pontos"], self.streak_txt(self.score_fid())))
            W["nivel"].config(text=("Nível: %s" % si["nivel"]) + (" · faltam %d pontos para %s" % (si["falta"], si["proximo"]) if si["proximo"] else ""))
            meta = si["meta"]
            if meta > 0:
                frac = min(1.0, si["semana"] / float(meta))
                bar = W["bar"]
                bar.delete("all")
                wd = max(bar.winfo_width(), 10)
                bar.create_rectangle(0, 0, int(wd * frac), 12, fill=GREEN if frac >= 1 else PINK, outline="")
                W["week"].config(text="Semana: %d de %d pontos%s · %s" % (si["semana"], meta, " (meta batida!)" if frac >= 1 else "", si["premio"]))
            else:
                W["bar"].delete("all")
                W["week"].config(text="")
        else:
            for k in ("pts", "nivel", "week"):
                W[k].config(text="")
            W["bar"].delete("all")

    # ---- configurações
    def open_settings(self):
        pw = self.cfg.get("senha_config") or ""
        if pw:
            from tkinter import simpledialog
            parent = self.win if (self.win is not None and self.win.winfo_exists()) else self.root
            if simpledialog.askstring("Configurações", "Digite a senha:", show="*", parent=parent) != pw:
                return
        try:
            import configuracoes
            configuracoes.abrir(self)
        except Exception:
            log("configuracoes: " + traceback.format_exc())
            self.show("Configurações", "Não consegui abrir as configurações. Veja o arquivo erro.log.", "tag", 12000, test=True)

    def apply_config(self, new, remoto=False):
        self.cfg = new
        if not remoto:
            # a revisão tem de ser maior que qualquer uma já vista, mesmo que o relógio deste computador esteja atrasado
            self.cfg["cfg_rev"] = max(int(time.time() * 1000), int(getattr(self, "rev_visto", 0)) + 1, int(new.get("cfg_rev", 0)) + 1)
        save_json(CONFIG_FILE, self.cfg)             # primeiro grava no disco; o resto pode falhar sem perder a alteração
        try:
            self.apply_day()
            if not remoto:
                self.empurrar_config()
            self.sync_soon()
            self.next_random = self.sched_random()
            self.fired = {k for k in self.fired if not k.startswith("lem")}
            if self.win is not None and self.win.winfo_exists():
                self.win.destroy()
                self.win, self.w = None, {}
                self.open_window()
            self.refresh()
        except Exception:
            log("apply_config: " + traceback.format_exc())
            if not remoto:
                raise

    # ---- laço principal
    def tick(self):
        try:
            self.process_cmds()
            d = dt.datetime.now()
            m = d.hour * 60 + d.minute
            if m != self.last_min:
                self.last_min = m
                self.on_minute(d)
            if self.fim_alvo and time.time() >= self.fim_alvo:
                self.fim_alvo = None
                if not self.state.get("relatorio_gerado"):
                    self.end_of_day()
            self.tick_pending(m)
            self.tick_random(m)
            self.tick_hold()
            self.refresh()
        except Exception:
            log("tick: " + traceback.format_exc())
        try:
            self.root.after(1000, self.tick)
        except Exception:
            pass


def pasta_instalacao():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "PainelDoCaixa")


def falar_com_instancia(msg, espera=0.0):
    """Manda uma palavra para o programa que já está rodando. Devolve True se havia um."""
    try:
        c = socket.create_connection(("127.0.0.1", PORTA), timeout=2)
        c.sendall(msg)
        c.close()
        if espera:
            time.sleep(espera)
        return True
    except OSError:
        return False


def instalar_e_abrir():
    """Versão .exe: ao abrir de qualquer pasta, copia-se para AppData, registra o início com o Windows e abre dali.
    Assim basta baixar o .exe e dar dois cliques; baixar uma versão nova e abrir também atualiza."""
    if not (FROZEN and sys.platform == "win32") or os.environ.get("CAIXA_DADOS"):
        return False
    try:
        import shutil
        destino_dir = pasta_instalacao()
        destino = os.path.join(destino_dir, "PainelDoCaixa.exe")
        atual = os.path.abspath(sys.executable)
        if os.path.normcase(atual) == os.path.normcase(destino):
            return False
        os.makedirs(destino_dir, exist_ok=True)
        if falar_com_instancia(b"sair"):          # fecha a versão antiga para poder trocar o arquivo
            for _ in range(20):
                time.sleep(0.5)
                try:
                    probe = socket.socket()
                    probe.bind(("127.0.0.1", PORTA))
                    probe.close()
                    break
                except OSError:
                    continue
        for _ in range(10):
            try:
                shutil.copy2(atual, destino)
                break
            except OSError:
                time.sleep(0.5)
        else:
            return False
        subprocess.Popen([destino], cwd=destino_dir, creationflags=0x00000008 | 0x00000200)
        return True
    except Exception:
        log("instalar: " + traceback.format_exc())
        return False


def ensure_autostart():
    """Versão .exe: registra o programa para abrir sozinho com o Windows."""
    if not (FROZEN and sys.platform == "win32"):
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "PainelDoCaixa", 0, winreg.REG_SZ, '"%s"' % sys.executable)
    except Exception:
        log("autostart: " + traceback.format_exc())


def ouvir_instancia(lock, app):
    """O socket de instância única também recebe pedidos de outras cópias: 'abrir' (mostra a janela) e 'sair' (atualização)."""
    def run():
        try:
            lock.listen(5)
            while True:
                conn, _ = lock.accept()
                try:
                    conn.settimeout(1)
                    dado = conn.recv(16)
                    conn.close()
                except OSError:
                    continue
                app.cmd_q.put("quit" if dado.startswith(b"sair") else "open")
        except OSError:
            return
    threading.Thread(target=run, daemon=True).start()


def main():
    if instalar_e_abrir():
        return
    try:  # uma cópia só
        lock = socket.socket()
        lock.bind(("127.0.0.1", PORTA))
    except OSError:
        falar_com_instancia(b"abrir")          # já está rodando: só mostra a janela
        return
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    ensure_autostart()
    try:
        app = App()
        ouvir_instancia(lock, app)
        app.root.mainloop()
    except Exception:
        log("main: " + traceback.format_exc())
    finally:
        lock.close()


if __name__ == "__main__":
    main()
