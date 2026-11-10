package br.com.spacopes.caixa

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.NetworkInterface
import java.net.URL
import java.util.concurrent.Callable
import java.util.concurrent.Executors

const val PORTA = 8765

/** Dados guardados no aparelho: onde está o computador do caixa e o código da loja. */
object Dados {
    private fun p(c: Context) = c.getSharedPreferences("caixa", Context.MODE_PRIVATE)
    fun host(c: Context): String = p(c).getString("host", "") ?: ""
    fun codigo(c: Context): String = p(c).getString("codigo", "") ?: ""
    fun ultimoAviso(c: Context): Long = p(c).getLong("ultimo_aviso", -1L)
    fun salvar(c: Context, host: String, codigo: String) {
        p(c).edit().putString("host", host).putString("codigo", codigo).putLong("ultimo_aviso", -1L).apply()
    }
    fun salvarHost(c: Context, host: String) { p(c).edit().putString("host", host).apply() }
    fun salvarUltimo(c: Context, v: Long) { p(c).edit().putLong("ultimo_aviso", v).apply() }
    fun limpar(c: Context) { p(c).edit().clear().apply() }
    fun pareado(c: Context) = host(c).isNotEmpty() && codigo(c).isNotEmpty()
    fun base(c: Context) = "http://" + host(c)
}

object Rede {
    /** Faz uma chamada HTTP. Devolve (código, corpo) ou (-1, "") se não deu para falar com o computador. */
    fun http(metodo: String, url: String, corpo: String? = null, timeout: Int = 4000): Pair<Int, String> {
        return try {
            val con = URL(url).openConnection() as HttpURLConnection
            con.requestMethod = metodo
            con.connectTimeout = timeout
            con.readTimeout = timeout
            con.useCaches = false
            if (corpo != null) {
                con.doOutput = true
                con.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                con.outputStream.use { it.write(corpo.toByteArray(Charsets.UTF_8)) }
            }
            val cod = con.responseCode
            val stream = if (cod >= 400) con.errorStream else con.inputStream
            val txt = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            con.disconnect()
            Pair(cod, txt)
        } catch (e: Exception) {
            Pair(-1, "")
        }
    }

    /** Endereços IPv4 deste celular na rede (ex.: 192.168.0.45). */
    fun meusIps(): List<String> {
        val out = ArrayList<String>()
        try {
            val ifs = NetworkInterface.getNetworkInterfaces()
            while (ifs != null && ifs.hasMoreElements()) {
                val ni = ifs.nextElement()
                if (!ni.isUp || ni.isLoopback) continue
                val ends = ni.inetAddresses
                while (ends.hasMoreElements()) {
                    val a = ends.nextElement()
                    if (a is Inet4Address && a.isSiteLocalAddress) a.hostAddress?.let { out.add(it) }
                }
            }
        } catch (e: Exception) {
        }
        return out
    }

    /** Procura o computador do caixa na rede (testa todos os endereços da mesma faixa). Se vier o código da loja, confirma que é a mesma loja. */
    fun descobrir(codigo: String = ""): List<String> {
        val achados = ArrayList<String>()
        val pool = Executors.newFixedThreadPool(48)
        try {
            val tarefas = ArrayList<Callable<String?>>()
            for (ip in meusIps()) {
                val partes = ip.split(".")
                if (partes.size != 4) continue
                val prefixo = partes[0] + "." + partes[1] + "." + partes[2] + "."
                for (n in 1..254) {
                    val alvo = prefixo + n
                    if (alvo == ip) continue
                    tarefas.add(Callable {
                        val r = http("GET", "http://$alvo:$PORTA/ping.json", null, 700)
                        if (r.first == 200 && r.second.contains("\"caixa\"")) {
                            if (codigo.isEmpty()) "$alvo:$PORTA"
                            else if (http("GET", "http://$alvo:$PORTA/lojas/$codigo/meta.json", null, 1500).first == 200) "$alvo:$PORTA" else null
                        } else null
                    })
                }
            }
            for (f in pool.invokeAll(tarefas)) {
                try { f.get()?.let { achados.add(it) } } catch (e: Exception) { }
            }
        } finally {
            pool.shutdownNow()
        }
        return achados
    }

    /** Troca o PIN de 6 dígitos pelo código da loja. Devolve o código, ou uma mensagem de erro com prefixo "!". */
    fun parear(host: String, pin: String): String {
        val r = http("POST", "http://$host/parear", JSONObject().put("pin", pin).toString(), 5000)
        return when {
            r.first == 200 -> try { JSONObject(r.second).getString("codigo") } catch (e: Exception) { "!Resposta inesperada do computador." }
            r.first == 403 -> "!PIN incorreto. Veja o PIN em Configurações > Celular (Wi-Fi), no computador."
            r.first == 429 -> "!Muitas tentativas. Espere 1 minuto."
            else -> "!Não consegui falar com o computador ($host). Ele está ligado, com o programa aberto, no mesmo Wi-Fi?"
        }
    }
}
