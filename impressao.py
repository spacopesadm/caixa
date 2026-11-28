# -*- coding: utf-8 -*-
"""
Impressão na impressora térmica de cupom (Epson TM-T20x e similares, 80 mm) usando ESC/POS direto pelo Windows.
Não precisa instalar nada além do driver da impressora que já está instalado.
"""
import datetime as dt
import sys
import textwrap

CODEPAGE = "cp860"          # português na Epson (ESC t 3)
ESC, GS = b"\x1b", b"\x1d"


def _t(txt):
    return str(txt).encode(CODEPAGE, errors="replace")


class Ticket:
    def __init__(self, colunas=48):
        self.col = max(24, int(colunas))
        self.b = bytearray(ESC + b"@" + ESC + b"t" + bytes([3]))

    def texto(self, txt, negrito=False, grande=False, centro=False):
        self.b += ESC + b"a" + (b"\x01" if centro else b"\x00")
        self.b += ESC + b"E" + (b"\x01" if negrito else b"\x00")
        self.b += GS + b"!" + (b"\x11" if grande else b"\x00")
        largura = self.col // (2 if grande else 1)
        for lin in (str(txt).splitlines() or [""]):
            for parte in (textwrap.wrap(lin, largura) or [""]):
                self.b += _t(parte) + b"\n"
        self.b += GS + b"!\x00" + ESC + b"E\x00" + ESC + b"a\x00"

    def linha(self, c="-"):
        self.b += _t(c * self.col) + b"\n"

    def fim(self):
        self.b += b"\n\n\n" + GS + b"V" + bytes([66, 0])      # avança e corta
        return bytes(self.b)


def montar_endereco(it, colunas=48):
    """Cupom da entrega: nome, telefone, endereço e ponto de referência (letras grandes, para o entregador ler fácil)."""
    t = Ticket(colunas)
    t.texto("SPAÇO PÉS", negrito=True, grande=True, centro=True)
    t.texto(str(it.get("tipo", "Entrega")).upper(), negrito=True, centro=True)
    t.linha()
    try:
        data = dt.datetime.strptime(it["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        data = it.get("data", "")
    t.texto("Dia %s   %s" % (data, (it.get("janela") or it.get("hora", "")).replace("-", " às ")), negrito=True)
    if it.get("vendedor"):
        t.texto("Vendedor: %s" % it["vendedor"])
    t.linha()
    t.texto("CLIENTE", negrito=True)
    t.texto(it.get("cliente") or it.get("titulo", ""), grande=True)
    t.texto("TELEFONE", negrito=True)
    t.texto(it.get("telefone", ""), grande=True)
    t.linha()
    t.texto("ENDEREÇO", negrito=True)
    t.texto(it.get("endereco") or "(não informado)", grande=True)
    bairro = it.get("bairro", "")
    if it.get("zona"):
        bairro += "  (Região %s)" % it["zona"]
    t.texto("Bairro: %s" % bairro, negrito=True)
    if it.get("cep"):
        c = str(it["cep"])
        t.texto("CEP: %s" % (c[:5] + "-" + c[5:] if len(c) == 8 and "-" not in c else c))
    if it.get("referencia"):
        t.linha()
        t.texto("PONTO DE REFERÊNCIA", negrito=True)
        t.texto(it["referencia"], grande=True)
    if it.get("obs"):
        t.linha()
        t.texto("OBS: %s" % it["obs"])
    t.linha()
    t.texto("Impresso em %s" % dt.datetime.now().strftime("%d/%m %H:%M"), centro=True)
    return t.fim()


def montar_retirada(it, colunas=48):
    """Cupom do 'Vem buscar': quem é a cliente, quem vem pegar e como está o pagamento."""
    t = Ticket(colunas)
    t.texto("SPAÇO PÉS", negrito=True, grande=True, centro=True)
    t.texto("VEM BUSCAR", negrito=True, grande=True, centro=True)
    t.linha()
    try:
        data = dt.datetime.strptime(it["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        data = it.get("data", "")
    t.texto("Lançado em %s" % data, negrito=True)
    if it.get("vendedor"):
        t.texto("Vendedor: %s" % it["vendedor"])
    t.linha()
    t.texto("CLIENTE", negrito=True)
    t.texto(it.get("cliente") or it.get("titulo", ""), grande=True)
    if it.get("telefone"):
        t.texto("Telefone: %s" % it["telefone"])
    t.texto("QUEM VEM PEGAR", negrito=True)
    t.texto(it.get("quem_busca") or "A própria cliente", grande=True)
    t.linha()
    t.texto("PAGAMENTO", negrito=True)
    pago = str(it.get("pago") or "").lower().startswith("s")
    t.texto("PAGO" if pago else "A PAGAR NA RETIRADA", negrito=True, grande=True)
    if it.get("pagamento"):
        t.texto(("Forma: %s" if pago else "Vai pagar com: %s") % it["pagamento"])
    if it.get("obs"):
        t.linha()
        t.texto("OBS: %s" % it["obs"])
    t.linha()
    t.texto("Impresso em %s" % dt.datetime.now().strftime("%d/%m %H:%M"), centro=True)
    return t.fim()


def montar_roteiro(texto, colunas=48):
    t = Ticket(colunas)
    for lin in texto.splitlines():
        if lin.startswith("=="):
            t.linha()
            t.texto(lin.strip("= ").strip(), negrito=True, grande=True)
        elif lin.startswith("ROTEIRO"):
            t.texto(lin, negrito=True, grande=True, centro=True)
        elif lin.startswith("[ ]") or lin.startswith("[X]"):
            t.texto(lin, negrito=True)
        else:
            t.texto(lin)
    return t.fim()


def montar_teste(colunas=48):
    t = Ticket(colunas)
    t.texto("TESTE DE IMPRESSÃO", negrito=True, grande=True, centro=True)
    t.linha()
    t.texto("Spaço Pés - Painel do Caixa")
    t.texto("Acentos: ção ã é í ó ú ç Ç")
    t.texto("0123456789 " * 5)
    return t.fim()


# ------------------------------------------------------------------ Windows (spooler, modo RAW)
def _win():
    if not sys.platform.startswith("win"):
        raise OSError("A impressão só funciona no Windows.")
    import ctypes
    from ctypes import wintypes as wt
    lib = ctypes.WinDLL("winspool.drv", use_last_error=True)
    return ctypes, wt, lib


def listar_impressoras():
    try:
        ctypes, wt, lib = _win()
    except OSError:
        return []

    class PRINTER_INFO_4(ctypes.Structure):
        _fields_ = [("pPrinterName", wt.LPWSTR), ("pServerName", wt.LPWSTR), ("Attributes", wt.DWORD)]
    flags = 2 | 4          # LOCAL | CONNECTIONS
    need, ret = wt.DWORD(0), wt.DWORD(0)
    lib.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(need), ctypes.byref(ret))
    if not need.value:
        return []
    buf = ctypes.create_string_buffer(need.value)
    if not lib.EnumPrintersW(flags, None, 4, buf, need, ctypes.byref(need), ctypes.byref(ret)):
        return []
    arr = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_4))
    return [arr[i].pPrinterName for i in range(ret.value)]


def impressora_padrao():
    try:
        ctypes, wt, lib = _win()
    except OSError:
        return ""
    n = wt.DWORD(0)
    lib.GetDefaultPrinterW(None, ctypes.byref(n))
    if not n.value:
        return ""
    buf = ctypes.create_unicode_buffer(n.value)
    return buf.value if lib.GetDefaultPrinterW(buf, ctypes.byref(n)) else ""


def escolher(nome=""):
    """Impressora a usar: a escolhida; senão uma Epson TM-T20; senão qualquer Epson/TM; senão a padrão do Windows."""
    if nome:
        return nome
    lista = listar_impressoras()
    for chave in ("tm-t20", "epson", "tm-"):
        for n in lista:
            if chave in n.lower():
                return n
    return impressora_padrao()


def enviar(nome, dados, titulo="Painel do Caixa"):
    ctypes, wt, lib = _win()
    alvo = escolher(nome)
    if not alvo:
        raise OSError("Nenhuma impressora encontrada. Escolha a impressora em Configurações > Entregas.")

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [("pDocName", wt.LPWSTR), ("pOutputFile", wt.LPWSTR), ("pDatatype", wt.LPWSTR)]
    lib.OpenPrinterW.argtypes = [wt.LPWSTR, ctypes.POINTER(wt.HANDLE), ctypes.c_void_p]
    lib.StartDocPrinterW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p]
    lib.WritePrinter.argtypes = [wt.HANDLE, ctypes.c_char_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    for f in (lib.StartPagePrinter, lib.EndPagePrinter, lib.EndDocPrinter, lib.ClosePrinter):
        f.argtypes = [wt.HANDLE]
    h = wt.HANDLE()
    if not lib.OpenPrinterW(alvo, ctypes.byref(h), None):
        raise OSError("Não consegui abrir a impressora \"%s\" (erro %d). Ela está ligada e instalada?" % (alvo, ctypes.get_last_error()))
    try:
        doc = DOC_INFO_1(titulo, None, "RAW")
        if not lib.StartDocPrinterW(h, 1, ctypes.byref(doc)):
            raise OSError("A impressora \"%s\" recusou o trabalho (erro %d)." % (alvo, ctypes.get_last_error()))
        try:
            lib.StartPagePrinter(h)
            escrito = wt.DWORD(0)
            if not lib.WritePrinter(h, bytes(dados), len(dados), ctypes.byref(escrito)) or escrito.value != len(dados):
                raise OSError("Não consegui enviar os dados para \"%s\"." % alvo)
            lib.EndPagePrinter(h)
        finally:
            lib.EndDocPrinter(h)
    finally:
        lib.ClosePrinter(h)
    return alvo
