package br.com.spacopes.caixa

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.app.Notification
import android.webkit.JavascriptInterface
import org.json.JSONArray
import org.json.JSONObject

/** Lembretes pessoais deste celular: guardados no aparelho e disparados por alarme (tocam mesmo com o app fechado). */
object Lembretes {
    private const val ACAO = "br.com.spacopes.caixa.LEMBRETE"
    private const val CANAL = "lembretes"

    private fun prefs(c: Context) = c.getSharedPreferences("lembretes", Context.MODE_PRIVATE)

    @Synchronized
    private fun ler(c: Context): JSONArray = try { JSONArray(prefs(c).getString("lista", "[]")) } catch (e: Exception) { JSONArray() }

    @Synchronized
    private fun gravar(c: Context, a: JSONArray) { prefs(c).edit().putString("lista", a.toString()).apply() }

    private fun pendente(c: Context, id: String, titulo: String, texto: String): PendingIntent {
        val i = Intent(c, LembreteReceiver::class.java)
        i.action = ACAO
        i.data = Uri.parse("lembrete://" + Uri.encode(id))
        i.putExtra("id", id).putExtra("titulo", titulo).putExtra("texto", texto)
        return PendingIntent.getBroadcast(c, 0, i, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun armar(c: Context, id: String, quando: Long, titulo: String, texto: String) {
        val am = c.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pi = pendente(c, id, titulo, texto)
        var exato = true
        if (Build.VERSION.SDK_INT >= 31) {
            try { exato = am.canScheduleExactAlarms() } catch (e: Exception) { exato = false }
        }
        try {
            if (exato) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, quando, pi)
            else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, quando, pi)
        } catch (e: SecurityException) {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, quando, pi)
        }
    }

    fun agendar(c: Context, id: String, quando: Long, titulo: String, texto: String) {
        val nova = JSONArray()
        val a = ler(c)
        for (i in 0 until a.length()) {
            val o = a.getJSONObject(i)
            if (o.optString("id") != id) nova.put(o)
        }
        nova.put(JSONObject().put("id", id).put("quando", quando).put("titulo", titulo).put("texto", texto))
        gravar(c, nova)
        armar(c, id, quando, titulo, texto)
    }

    fun cancelar(c: Context, id: String) {
        val nova = JSONArray()
        val a = ler(c)
        for (i in 0 until a.length()) {
            val o = a.getJSONObject(i)
            if (o.optString("id") != id) nova.put(o)
        }
        gravar(c, nova)
        try {
            val am = c.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            am.cancel(pendente(c, id, "", ""))
        } catch (e: Exception) { }
    }

    fun lista(c: Context): String {
        val a = ler(c)
        val itens = ArrayList<JSONObject>()
        for (i in 0 until a.length()) itens.add(a.getJSONObject(i))
        itens.sortBy { it.optLong("quando") }
        val out = JSONArray()
        for (o in itens) out.put(o)
        return out.toString()
    }

    /** Depois de reiniciar o celular ou atualizar o app: rearma os alarmes (os que já passaram avisam agora). */
    fun reagendar(c: Context) {
        val a = ler(c)
        val agora = System.currentTimeMillis()
        val resto = JSONArray()
        for (i in 0 until a.length()) {
            val o = a.getJSONObject(i)
            val q = o.optLong("quando")
            if (q > agora) {
                resto.put(o)
                armar(c, o.optString("id"), q, o.optString("titulo"), o.optString("texto"))
            } else {
                avisar(c, o.optString("id"), o.optString("titulo"), o.optString("texto"))
            }
        }
        gravar(c, resto)
    }

    fun avisar(c: Context, id: String, titulo: String, texto: String) {
        val nm = c.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) {
            val som = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()
            val ch = NotificationChannel(CANAL, "Lembretes", NotificationManager.IMPORTANCE_HIGH)
            ch.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION), som)
            ch.enableVibration(true)
            ch.vibrationPattern = longArrayOf(0, 400, 200, 400)
            nm.createNotificationChannel(ch)
        }
        val abrir = PendingIntent.getActivity(
            c, 0, Intent(c, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val b = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(c, CANAL) else Notification.Builder(c)
        b.setContentTitle(if (titulo.isEmpty()) "Lembrete" else titulo)
            .setContentText(texto)
            .setStyle(Notification.BigTextStyle().bigText(texto))
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setContentIntent(abrir)
            .setAutoCancel(true)
            .setWhen(System.currentTimeMillis())
        if (Build.VERSION.SDK_INT >= 21) b.setCategory(Notification.CATEGORY_REMINDER)
        if (Build.VERSION.SDK_INT < 26) {
            b.setPriority(Notification.PRIORITY_HIGH).setDefaults(Notification.DEFAULT_ALL)
        }
        try { nm.notify(id.hashCode(), b.build()) } catch (e: Exception) { }
    }
}

class LembreteReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getStringExtra("id") ?: return
        Lembretes.avisar(context, id, intent.getStringExtra("titulo") ?: "Lembrete", intent.getStringExtra("texto") ?: "")
        // o lembrete já tocou: sai da lista
        try { Lembretes.cancelar(context, id) } catch (e: Exception) { }
    }
}

/** Ponte entre a página (lembretes.html) e o celular. Só existe dentro do app. */
class PonteLembretes(private val c: Context) {
    @JavascriptInterface
    fun agendar(id: String, quando: String, titulo: String, texto: String): String {
        return try {
            Lembretes.agendar(c, id, quando.toLong(), titulo, texto)
            "ok"
        } catch (e: Exception) {
            "Não consegui agendar o aviso: " + e.javaClass.simpleName
        }
    }

    @JavascriptInterface
    fun cancelar(id: String) { try { Lembretes.cancelar(c, id) } catch (e: Exception) { } }

    @JavascriptInterface
    fun lista(): String = try { Lembretes.lista(c) } catch (e: Exception) { "[]" }
}
