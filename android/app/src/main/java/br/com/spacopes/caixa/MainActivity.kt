package br.com.spacopes.caixa

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class MainActivity : Activity() {
    private lateinit var raiz: FrameLayout
    private var web: WebView? = null
    private var aviso: TextView? = null
    private val h = Handler(Looper.getMainLooper())
    private var procurando = false

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        raiz = FrameLayout(this)
        setContentView(raiz)
        title = "Painel do Caixa"
        if (Build.VERSION.SDK_INT >= 33) {
            try { requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1) } catch (e: Exception) { }
        }
        if (Dados.pareado(this)) mostrarWeb() else mostrarPareamento()
    }

    override fun onResume() {
        super.onResume()
        if (Dados.pareado(this)) {
            try { AvisosService.iniciar(this) } catch (e: Exception) { }
        }
    }

    override fun onDestroy() {
        h.removeCallbacksAndMessages(null)
        web?.destroy()
        super.onDestroy()
    }

    // ---------- pareamento
    private fun mostrarPareamento() {
        h.removeCallbacksAndMessages(null)
        web?.destroy()
        web = null
        raiz.removeAllViews()
        val col = LinearLayout(this)
        col.orientation = LinearLayout.VERTICAL
        col.setPadding(dp(24), dp(24), dp(24), dp(24))
        val sv = ScrollView(this)
        sv.addView(col)
        raiz.addView(sv, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        fun texto(t: String, tam: Float, negrito: Boolean = false, cor: Int = Color.parseColor("#222222")): TextView {
            val v = TextView(this)
            v.text = t
            v.textSize = tam
            v.setTextColor(cor)
            if (negrito) v.setTypeface(v.typeface, android.graphics.Typeface.BOLD)
            v.setPadding(0, dp(6), 0, dp(6))
            return v
        }
        col.addView(texto("Conectar ao computador do caixa", 22f, true))
        col.addView(texto("1) Deixe o celular no mesmo Wi-Fi da loja.\n2) No computador, abra Configurações > Celular (Wi-Fi) e veja o PIN de 6 números.\n3) Digite o PIN aqui e toque em Conectar.", 15f))
        val pin = EditText(this)
        pin.hint = "PIN de 6 números"
        pin.inputType = InputType.TYPE_CLASS_NUMBER
        pin.textSize = 24f
        pin.gravity = Gravity.CENTER
        col.addView(pin)
        val manual = EditText(this)
        manual.hint = "Endereço do computador (só se não achar sozinho)"
        manual.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        col.addView(manual)
        val status = texto("", 15f, false, Color.parseColor("#B00020"))
        val btn = Button(this)
        btn.text = "Conectar"
        col.addView(btn)
        col.addView(status)

        btn.setOnClickListener {
            val p = pin.text.toString().trim()
            if (p.length != 6) { status.setTextColor(Color.parseColor("#B00020")); status.text = "Digite o PIN de 6 números."; return@setOnClickListener }
            var m = manual.text.toString().trim().removePrefix("http://").trimEnd('/')
            if (m.isNotEmpty() && !m.contains(":")) m = "$m:$PORTA"
            btn.isEnabled = false
            status.setTextColor(Color.parseColor("#555555"))
            status.text = if (m.isEmpty()) "Procurando o computador na rede..." else "Conectando..."
            Thread {
                var host = m
                if (host.isEmpty()) {
                    val achados = Rede.descobrir()
                    host = if (achados.isNotEmpty()) achados[0] else ""
                }
                var msg = ""
                var codigo = ""
                if (host.isEmpty()) {
                    msg = "Não achei o computador. Confira se o programa do caixa está aberto e se o celular está no mesmo Wi-Fi. Você também pode digitar o endereço mostrado nas Configurações do computador."
                } else {
                    val r = Rede.parear(host, p)
                    if (r.startsWith("!")) msg = r.substring(1) else codigo = r
                }
                runOnUiThread {
                    if (isFinishing) return@runOnUiThread
                    btn.isEnabled = true
                    if (codigo.isNotEmpty()) {
                        Dados.salvar(this, host, codigo)
                        try { AvisosService.iniciar(this) } catch (e: Exception) { }
                        mostrarWeb()
                        pedirBateria()
                    } else {
                        status.setTextColor(Color.parseColor("#B00020"))
                        status.text = msg
                    }
                }
            }.start()
        }
        invalidateOptionsMenu()
    }

    private fun pedirBateria() {
        try {
            if (Build.VERSION.SDK_INT >= 23) {
                val pm = getSystemService(POWER_SERVICE) as PowerManager
                if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                    startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
                }
            }
        } catch (e: Exception) { }
    }

    // ---------- página (a mesma do navegador, servida pelo computador do caixa)
    private fun urlPagina(): String {
        val base = Dados.base(this)
        return base + "/#u=" + base + "&t=" + Dados.codigo(this)
    }

    private fun mostrarWeb() {
        raiz.removeAllViews()
        val w = WebView(this)
        val s = w.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true
        s.cacheMode = WebSettings.LOAD_NO_CACHE
        w.webViewClient = object : WebViewClient() {
            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) falhou()
            }
            override fun onPageFinished(view: WebView, url: String?) {
                if (aviso?.visibility == View.VISIBLE && !procurando) aviso?.visibility = View.GONE
            }
        }
        web = w
        raiz.addView(w, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        val a = TextView(this)
        a.setBackgroundColor(Color.parseColor("#B00020"))
        a.setTextColor(Color.WHITE)
        a.setPadding(dp(12), dp(8), dp(12), dp(8))
        a.textSize = 14f
        a.visibility = View.GONE
        aviso = a
        raiz.addView(a, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP))
        w.loadUrl(urlPagina())
        invalidateOptionsMenu()
    }

    /** O computador não respondeu: procura de novo na rede (o endereço pode ter mudado) e recarrega. */
    private fun falhou() {
        aviso?.text = "Procurando o computador do caixa no Wi-Fi..."
        aviso?.visibility = View.VISIBLE
        if (procurando) return
        procurando = true
        Thread {
            var achou = ""
            val r = Rede.http("GET", "http://" + Dados.host(this) + "/ping.json", null, 1500)
            if (r.first != 200) {
                val l = Rede.descobrir(Dados.codigo(this))
                if (l.isNotEmpty()) { achou = l[0]; Dados.salvarHost(this, achou) }
            } else achou = Dados.host(this)
            runOnUiThread {
                procurando = false
                if (isFinishing) return@runOnUiThread
                if (achou.isNotEmpty()) { aviso?.visibility = View.GONE; web?.loadUrl(urlPagina()) }
                else h.postDelayed({ if (!isFinishing && Dados.pareado(this)) falhou() }, 8000)
            }
        }.start()
    }

    // ---------- menu e botão voltar
    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, "Recarregar")
        menu.add(0, 2, 1, "Trocar computador / desconectar")
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            1 -> if (Dados.pareado(this)) web?.loadUrl(urlPagina())
            2 -> {
                Dados.limpar(this)
                stopService(Intent(this, AvisosService::class.java))
                mostrarPareamento()
            }
        }
        return true
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        val w = web
        if (w != null && w.canGoBack()) w.goBack() else super.onBackPressed()
    }
}
