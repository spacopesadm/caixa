package br.com.spacopes.caixa

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Lista das próximas entregas/lembretes do caixa, guardada no aparelho para o widget da tela inicial. */
object DadosAgenda {
    private fun prefs(c: Context) = c.getSharedPreferences("agenda_widget", Context.MODE_PRIVATE)

    fun itens(c: Context): JSONArray = try { JSONArray(prefs(c).getString("itens", "[]")) } catch (e: Exception) { JSONArray() }

    fun atualizado(c: Context): String {
        val ts = prefs(c).getLong("ts", 0L)
        if (ts == 0L) return ""
        return "atualizado " + SimpleDateFormat("HH:mm", Locale.US).format(Date(ts))
    }

    private fun buscar(host: String, cod: String): JSONArray? {
        val m = Rede.http("GET", "http://$host/lojas/$cod/meta.json", null, 2500)
        if (m.first != 200) return null
        val ultimo = try { JSONObject(m.second).optString("ultimo") } catch (e: Exception) { "" }
        if (ultimo.isEmpty()) return JSONArray()
        val d = Rede.http("GET", "http://$host/lojas/$cod/dias/$ultimo.json", null, 3500)
        if (d.first != 200) return null
        val ag = try { JSONObject(d.second).optJSONArray("agenda") } catch (e: Exception) { null } ?: return JSONArray()
        val hoje = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
        val lista = ArrayList<JSONObject>()
        for (i in 0 until ag.length()) {
            val o = ag.optJSONObject(i) ?: continue
            val data = o.optString("data")
            if (data.isEmpty() || data < hoje) continue
            if (o.optDouble("feito", 0.0) > 0.0) continue
            val janela = o.optString("janela")
            val hora = if (janela.isNotEmpty()) janela else o.optString("hora")
            lista.add(
                JSONObject().put("data", data).put("hora", hora).put("tipo", o.optString("tipo"))
                    .put("titulo", o.optString("titulo")).put("cliente", o.optString("cliente"))
                    .put("bairro", o.optString("bairro")).put("endereco", o.optString("endereco"))
            )
        }
        lista.sortBy { it.optString("data") + it.optString("hora") }
        val out = JSONArray()
        for (o in lista.take(40)) out.put(o)
        return out
    }

    /** Busca no computador do caixa (procura de novo na rede se o endereço mudou). Só funciona no Wi-Fi da loja. */
    fun atualizar(c: Context): Boolean {
        if (!Dados.pareado(c)) return false
        var host = Dados.host(c)
        val cod = Dados.codigo(c)
        var r = buscar(host, cod)
        if (r == null) {
            val l = Rede.descobrir(cod)
            if (l.isNotEmpty()) {
                host = l[0]
                Dados.salvarHost(c, host)
                r = buscar(host, cod)
            }
        }
        if (r == null) return false
        prefs(c).edit().putString("itens", r.toString()).putLong("ts", System.currentTimeMillis()).apply()
        return true
    }
}

class EntregasWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, mgr: AppWidgetManager, ids: IntArray) {
        for (id in ids) desenhar(context, mgr, id)
        val pr = goAsync()
        Thread {
            try {
                DadosAgenda.atualizar(context)
                redesenhar(context)
            } catch (e: Exception) {
            } finally {
                pr.finish()
            }
        }.start()
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == ACAO) {
            val mgr = AppWidgetManager.getInstance(context)
            val ids = mgr.getAppWidgetIds(ComponentName(context, EntregasWidget::class.java))
            onUpdate(context, mgr, ids)
        } else {
            super.onReceive(context, intent)
        }
    }

    companion object {
        const val ACAO = "br.com.spacopes.caixa.WIDGET_ATUALIZAR"

        fun desenhar(c: Context, mgr: AppWidgetManager, id: Int) {
            val rv = RemoteViews(c.packageName, R.layout.widget_entregas)
            val svc = Intent(c, EntregasListaService::class.java)
            svc.putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id)
            svc.data = Uri.parse(svc.toUri(Intent.URI_INTENT_SCHEME))
            rv.setRemoteAdapter(R.id.w_lista, svc)
            rv.setEmptyView(R.id.w_lista, R.id.w_vazio)
            rv.setTextViewText(R.id.w_vazio, if (Dados.pareado(c)) "Nenhuma entrega agendada." else "Abra o app e conecte ao caixa.")
            rv.setTextViewText(R.id.w_atual, DadosAgenda.atualizado(c))
            val ref = Intent(c, EntregasWidget::class.java)
            ref.action = ACAO
            rv.setOnClickPendingIntent(R.id.w_topo, PendingIntent.getBroadcast(c, 0, ref, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
            val mut = if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
            val abrir = Intent(c, MainActivity::class.java)
            rv.setPendingIntentTemplate(R.id.w_lista, PendingIntent.getActivity(c, 1, abrir, PendingIntent.FLAG_UPDATE_CURRENT or mut))
            mgr.updateAppWidget(id, rv)
        }

        /** Redesenha todos os widgets com os dados guardados. */
        fun redesenhar(c: Context) {
            val mgr = AppWidgetManager.getInstance(c)
            val ids = mgr.getAppWidgetIds(ComponentName(c, EntregasWidget::class.java))
            if (ids.isEmpty()) return
            for (id in ids) desenhar(c, mgr, id)
            mgr.notifyAppWidgetViewDataChanged(ids, R.id.w_lista)
        }
    }
}

class EntregasListaService : RemoteViewsService() {
    override fun onGetViewFactory(intent: Intent): RemoteViewsFactory = Fabrica(applicationContext)

    private class Fabrica(private val c: Context) : RemoteViewsFactory {
        private var itens = JSONArray()

        override fun onCreate() { itens = DadosAgenda.itens(c) }
        override fun onDataSetChanged() { itens = DadosAgenda.itens(c) }
        override fun onDestroy() {}
        override fun getCount(): Int = itens.length()
        override fun getLoadingView(): RemoteViews? = null
        override fun getViewTypeCount(): Int = 1
        override fun getItemId(position: Int): Long = position.toLong()
        override fun hasStableIds(): Boolean = false

        private fun rotuloDia(data: String): String {
            val f = SimpleDateFormat("yyyy-MM-dd", Locale.US)
            val hoje = f.format(Date())
            val amanha = f.format(Date(System.currentTimeMillis() + 86400000L))
            if (data == hoje) return "Hoje"
            if (data == amanha) return "Amanhã"
            val p = data.split("-")
            return if (p.size == 3) p[2] + "/" + p[1] else data
        }

        override fun getViewAt(position: Int): RemoteViews {
            val rv = RemoteViews(c.packageName, R.layout.item_entrega)
            val o = itens.optJSONObject(position) ?: return rv
            val hora = o.optString("hora").replace("-", " – ")
            val l1 = rotuloDia(o.optString("data")) + (if (hora.isNotEmpty()) "  " + hora else "") + " · " + o.optString("tipo")
            val partes = ArrayList<String>()
            val quem = if (o.optString("cliente").isNotEmpty()) o.optString("cliente") else o.optString("titulo")
            if (quem.isNotEmpty()) partes.add(quem)
            if (o.optString("bairro").isNotEmpty()) partes.add(o.optString("bairro"))
            if (o.optString("endereco").isNotEmpty()) partes.add(o.optString("endereco"))
            rv.setTextViewText(R.id.i_l1, l1)
            rv.setTextViewText(R.id.i_l2, partes.joinToString(" · "))
            rv.setOnClickFillInIntent(R.id.i_raiz, Intent())
            return rv
        }
    }
}
