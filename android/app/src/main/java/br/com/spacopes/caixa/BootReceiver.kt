package br.com.spacopes.caixa

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        try {
            if (Dados.pareado(context)) AvisosService.iniciar(context)
        } catch (e: Exception) {
        }
    }
}
