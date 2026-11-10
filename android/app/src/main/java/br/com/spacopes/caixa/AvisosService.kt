package br.com.spacopes.caixa

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import org.json.JSONObject

/** Fica rodando em segundo plano, pergunta ao computador do caixa se há avisos novos e toca/vibra no celular. */
class AvisosService : Service() {
    @Volatile private var rodando = false
    private var thread: Thread? = null
    private var wake: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        criarCanais()
        iniciarPrimeiroPlano("Conectando ao computador do caixa...")
        if (!rodando) {
            rodando = true
            thread = Thread { laco() }.also { it.isDaemon = true; it.start() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        rodando = false
        try { wake?.release() } catch (e: Exception) { }
        super.onDestroy()
    }

    private fun nm() = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    private fun criarCanais() {
        if (Build.VERSION.SDK_INT < 26) return
        val m = nm()
        val c1 = NotificationChannel("estado", "Conexão com o caixa", NotificationManager.IMPORTANCE_MIN)
        c1.setShowBadge(false)
        m.createNotificationChannel(c1)
        val som = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()
        val c2 = NotificationChannel("avisos", "Avisos do caixa", NotificationManager.IMPORTANCE_HIGH)
        c2.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION), som)
        c2.enableVibration(true)
        m.createNotificationChannel(c2)
        val alarme = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()
        val c3 = NotificationChannel("urgente", "Avisos urgentes", NotificationManager.IMPORTANCE_HIGH)
        c3.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM), alarme)
        c3.enableVibration(true)
        c3.vibrationPattern = longArrayOf(0, 500, 200, 500, 200, 800)
        m.createNotificationChannel(c3)
    }

    private fun abrirApp(): PendingIntent {
        val i = Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val f = if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0
        return PendingIntent.getActivity(this, 0, i, f)
    }

    private fun construir(canal: String, titulo: String, texto: String): Notification.Builder {
        val b = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, canal) else Notification.Builder(this)
        b.setContentTitle(titulo).setContentText(texto).setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setContentIntent(abrirApp()).setAutoCancel(true)
        return b
    }

    private fun iniciarPrimeiroPlano(texto: String) {
        val n = construir("estado", "Painel do Caixa", texto).setOngoing(true).build()
        try {
            if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            else startForeground(1, n)
        } catch (e: Exception) {
            stopSelf()
        }
    }

    private var textoEstado = ""
    private fun estado(texto: String) {
        if (texto == textoEstado) return
        textoEstado = texto
        nm().notify(1, construir("estado", "Painel do Caixa", texto).setOngoing(true).build())
    }

    private fun avisar(id: Long, titulo: String, texto: String, prio: Int) {
        val canal = if (prio >= 5) "urgente" else "avisos"
        val b = construir(canal, titulo, texto)
        b.setStyle(Notification.BigTextStyle().bigText(texto))
        if (Build.VERSION.SDK_INT < 26) {
            b.setPriority(Notification.PRIORITY_HIGH)
            b.setDefaults(Notification.DEFAULT_ALL)
        }
        try {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            val w = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "caixa:aviso")
            w.acquire(5000)
        } catch (e: Exception) { }
        nm().notify((1000 + (id % 100000)).toInt(), b.build())
    }

    private fun laco() {
        var falhas = 0
        var ultimaBusca = 0L
        while (rodando) {
            try {
                if (!Dados.pareado(this)) { estado("Abra o app para conectar ao computador do caixa"); Thread.sleep(5000); continue }
                val url = Dados.base(this) + "/lojas/" + Dados.codigo(this) + "/avisos.json?desde=" + maxOf(0L, Dados.ultimoAviso(this))
                val r = Rede.http("GET", url, null, 4000)
                if (r.first == 200) {
                    falhas = 0
                    estado("Conectado ao computador do caixa")
                    val j = JSONObject(r.second)
                    val ultimo = j.optLong("ultimo", 0)
                    val antes = Dados.ultimoAviso(this)
                    if (antes < 0 || ultimo < antes) {
                        Dados.salvarUltimo(this, ultimo)      // primeira vez (ou o computador reiniciou): não toca avisos antigos
                    } else {
                        val itens = j.optJSONArray("itens")
                        if (itens != null) for (i in 0 until itens.length()) {
                            val it = itens.getJSONObject(i)
                            avisar(it.optLong("id"), it.optString("titulo"), it.optString("texto"), it.optInt("prio", 3))
                        }
                        if (ultimo != antes) Dados.salvarUltimo(this, ultimo)
                    }
                } else {
                    falhas++
                    estado("Sem conexão com o computador do caixa. Procurando...")
                    if (falhas >= 3 && System.currentTimeMillis() - ultimaBusca > 30000) {
                        ultimaBusca = System.currentTimeMillis()
                        val achou = Rede.descobrir(Dados.codigo(this))
                        if (achou.isNotEmpty()) { Dados.salvarHost(this, achou[0]); falhas = 0 }
                    }
                }
            } catch (e: Exception) {
                falhas++
            }
            try { Thread.sleep(4000) } catch (e: InterruptedException) { }
        }
    }

    companion object {
        fun iniciar(c: Context) {
            val i = Intent(c, AvisosService::class.java)
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i) else c.startService(i)
        }
    }
}
