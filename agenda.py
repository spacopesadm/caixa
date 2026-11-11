# -*- coding: utf-8 -*-
"""
Agenda da loja: entregas, condicionais, atendimentos, lembretes e avisos para um dia e hora.
Cada item: {id, data 'AAAA-MM-DD', hora 'HH:MM', tipo, titulo, detalhe, antes (min), feito (timestamp ou 0), apagado, mod (ms)}.
Itens são mesclados por id; vale o que tem 'mod' maior (serve para vários computadores e para o celular).
"""
import datetime as dt
import re
import time
import uuid

TIPOS = ["Entrega", "Condicional", "Buscar condicional", "Atendimento", "Lembrete", "Aviso"]
ANTES = [0, 5, 10, 15, 30, 60]


def novo_id():
    return "a" + uuid.uuid4().hex[:9]


def parse_data(txt, hoje=None):
    """Aceita 15/11/2026, 15/11/26, 15/11 e 2026-11-15. Devolve 'AAAA-MM-DD'."""
    t = (txt or "").strip().replace(".", "/").replace("-", "/")
    hoje = hoje or dt.date.today()
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", t)
    if m:
        a, mes, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
        if not m:
            raise ValueError("Data inválida. Use dia/mês/ano, por exemplo 15/11/2026.")
        d, mes = int(m.group(1)), int(m.group(2))
        a = int(m.group(3)) if m.group(3) else hoje.year
        if a < 100:
            a += 2000
    try:
        return dt.date(a, mes, d).strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError("Essa data não existe. Use dia/mês/ano, por exemplo 15/11/2026.")


def parse_hora(txt):
    t = (txt or "").strip().lower().replace("h", ":").replace(".", ":")
    if t.endswith(":"):
        t += "00"
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", t)
    if not m:
        raise ValueError("Hora inválida. Use por exemplo 14:00.")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        raise ValueError("Hora inválida. Use por exemplo 14:00.")
    return "%02d:%02d" % (h, mi)


def data_br(iso):
    try:
        return dt.datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def criar(data, hora, tipo, titulo, detalhe="", antes=0, id_=None):
    titulo = (titulo or "").strip()
    if not titulo:
        raise ValueError("Escreva o que é (por exemplo: Condicional para Fulana).")
    return {"id": id_ or novo_id(), "data": data, "hora": hora, "tipo": tipo if tipo in TIPOS else "Aviso", "titulo": titulo[:120],
            "detalhe": (detalhe or "").strip()[:600], "antes": int(antes) if int(antes) in ANTES else 0, "feito": 0, "apagado": False,
            "mod": int(time.time() * 1000)}


def prazo(item):
    """Momento (timestamp) em que o aviso deve tocar."""
    return dt.datetime.strptime("%s %s" % (item["data"], item["hora"]), "%Y-%m-%d %H:%M").timestamp()


def valido(it):
    return isinstance(it, dict) and it.get("id") and it.get("titulo") and it.get("data") and it.get("hora")


def mesclar(atual, novos):
    """Une duas listas por id; fica o item de 'mod' maior."""
    por = {}
    for it in list(atual or []) + list(novos or []):
        if not valido(it):
            continue
        a = por.get(it["id"])
        if a is None or int(it.get("mod", 0)) > int(a.get("mod", 0)):
            por[it["id"]] = it
    return sorted(por.values(), key=lambda x: (x["data"], x["hora"], x["id"]))


def limpar(lista, hoje=None, dias=45):
    corte = ((hoje or dt.date.today()) - dt.timedelta(days=dias)).strftime("%Y-%m-%d")
    return [it for it in lista if it.get("data", "") >= corte]


def vivos(lista):
    return [it for it in lista if not it.get("apagado")]


def da_data(lista, iso):
    return [it for it in vivos(lista) if it["data"] == iso]
