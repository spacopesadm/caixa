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

TIPOS_ENTREGA = ["Entrega", "Condicional (Levar)", "Condicional (Buscar)", "Troca"]
BUSCAR = "Vem buscar"        # a cliente (ou alguém por ela) vem buscar na loja: sem endereço, com controle de pagamento
FORMAS_PAGTO = ["Pix", "Cartão de débito", "Cartão de crédito", "Dinheiro", "Link de pagamento", "Outra forma"]
TIPOS = TIPOS_ENTREGA + [BUSCAR, "Condicional", "Buscar condicional", "Atendimento", "Lembrete", "Aviso"]
EXTRAS = ("cliente", "bairro", "cep", "telefone", "vendedor", "janela", "zona", "tempo", "endereco", "referencia", "obs", "quem_busca", "pago", "pagamento")
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


def criar(data, hora, tipo, titulo, detalhe="", antes=0, id_=None, extra=None):
    titulo = (titulo or "").strip()
    if not titulo:
        raise ValueError("Escreva o que é (por exemplo: Condicional para Fulana).")
    it = {"id": id_ or novo_id(), "data": data, "hora": hora, "tipo": tipo if tipo in TIPOS else "Aviso", "titulo": titulo[:120],
            "detalhe": (detalhe or "").strip()[:600], "antes": int(antes) if int(antes) in ANTES else 0, "feito": 0, "apagado": False,
            "mod": int(time.time() * 1000)}
    for k in EXTRAS:
        if extra and extra.get(k) not in (None, ""):
            it[k] = str(extra[k])[:120]
    return it


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


QUALQUER = "Qualquer horário"      # entrega sem horário marcado: o cliente aceita receber a qualquer hora do dia


def e_qualquer(j):
    import unicodedata
    t = unicodedata.normalize("NFD", str(j or "")).encode("ascii", "ignore").decode().lower().replace(" ", "")
    return t.startswith("qualquer") or t in ("livre", "diatodo", "indiferente")


def janela_inicio(j, padrao="09:00"):
    if e_qualquer(j):
        return parse_hora(padrao)
    return parse_hora((j or "").split("-")[0])


def parse_janela(j):
    """'09:00-11:00' (ou '9h-11h') -> '09:00-11:00'. 'Qualquer horário' também vale."""
    if e_qualquer(j):
        return QUALQUER
    partes = (j or "").replace(" ", "").replace("às", "-").replace("as", "-").split("-")
    if len(partes) != 2:
        raise ValueError("Horário inválido. Use por exemplo 09:00-11:00.")
    a, b = parse_hora(partes[0]), parse_hora(partes[1])
    if a >= b:
        raise ValueError("Horário inválido: o fim tem de ser depois do início (%s)." % j)
    return "%s-%s" % (a, b)


def chave_roteiro(it):
    """Ordem do roteiro: dia, horário, zona (perto primeiro), bairro."""
    try:
        z = int(it.get("zona") or 9)
    except ValueError:
        z = 9
    return (it["data"], it.get("janela") or it["hora"], z, it.get("bairro") or "", it.get("cliente") or it.get("titulo", ""))


def rotulo_janela(j):
    j = str(j or "")
    if e_qualquer(j):
        return QUALQUER
    return j.replace("-", " às ") if "-" in j else "%s (horário específico)" % j


def roteiro_grupos(lista, iso):
    """[(rótulo do horário, [itens])] do dia: horários em ordem; dentro de cada um, zona (perto primeiro), bairro e nome."""
    itens = sorted([x for x in da_data(lista, iso) if x.get("janela")], key=chave_roteiro)
    grupos, ordem = {}, []
    for it in itens:
        if it["janela"] not in grupos:
            grupos[it["janela"]] = []
            ordem.append(it["janela"])
        grupos[it["janela"]].append(it)
    return [(rotulo_janela(j), grupos[j]) for j in ordem]


def linha_cliente(it, caixa=True):
    """Uma linha por cliente: [ ] Nome | Tipo | Bairro (Rn) | Telefone | Vendedor."""
    if it.get("tipo") == BUSCAR:
        partes = [it.get("cliente") or it.get("titulo", ""), it.get("tipo", ""), "Quem busca: %s" % (it.get("quem_busca") or "a cliente"),
                  texto_pagamento(it), it.get("telefone", "")]
    else:
        partes = [it.get("cliente") or it.get("titulo", ""), it.get("tipo", ""),
                  (it.get("bairro", "") + (" (R%s)" % it["zona"] if it.get("zona") else "")).strip(), it.get("telefone", "")]
    if it.get("vendedor"):
        partes.append("Vend.: %s" % it["vendedor"])
    return ("[X] " if it.get("feito") else "[ ] ") + " | ".join(p for p in partes if p)


def texto_pagamento(it):
    """'PAGO (Pix)' ou 'A PAGAR na retirada (Pix)'."""
    forma = str(it.get("pagamento") or "").strip()
    if str(it.get("pago") or "").lower().startswith("s"):
        return "PAGO" + (" (%s)" % forma if forma else "")
    return "A PAGAR na retirada" + (" (%s)" % forma if forma else "")


def linha_endereco(it):
    t = it.get("endereco", "")
    if it.get("referencia"):
        t += " - ref.: %s" % it["referencia"]
    if it.get("obs"):
        t += " - obs.: %s" % str(it["obs"]).replace("\n", " / ")
    return t.strip()


def roteiro_texto(lista, iso):
    """Roteiro do dia para imprimir/copiar: por horário, um cliente por linha (com o endereço logo abaixo)."""
    grupos = roteiro_grupos(lista, iso)
    if not grupos:
        return "Nenhuma entrega/condicional/troca agendada para %s." % data_br(iso)
    total = sum(len(g) for _r, g in grupos)
    out = ["ROTEIRO %s - %d %s" % (data_br(iso), total, "agendamento" if total == 1 else "agendamentos")]
    for rot, its in grupos:
        out += ["", "== %s (%d) ==" % (rot, len(its))]
        for it in its:
            out.append(linha_cliente(it))
            end = linha_endereco(it)
            if end:
                out.append("      " + end)
    return "\n".join(out)


def chave_bairro(s):
    """Para comparar bairros sem acento e sem maiúsculas."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())
