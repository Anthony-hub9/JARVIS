package com.jarvis.hud.core.platform

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.ContactsContract
import android.telephony.SmsManager
import androidx.core.content.ContextCompat

class ContactAndMessageHelper(private val context: Context) {

    fun sendSms(recipient: String, message: String): Result<String> {
        if (ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.SEND_SMS
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            return Result.failure(
                SecurityException("Falta el permiso SEND_SMS para enviar mensajes SMS.")
            )
        }

        val phoneNumber = resolvePhoneNumber(recipient)
            ?: return Result.failure(
                IllegalArgumentException("No encontré el número de teléfono de '$recipient'.")
            )

        return runCatching {
            val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                context.getSystemService(SmsManager::class.java)
            } else {
                @Suppress("DEPRECATION")
                SmsManager.getDefault()
            } ?: throw IllegalStateException("SmsManager no disponible en este dispositivo.")

            val parts = smsManager.divideMessage(message)
            if (parts.size > 1) {
                smsManager.sendMultipartTextMessage(phoneNumber, null, parts, null, null)
            } else {
                smsManager.sendTextMessage(phoneNumber, null, message, null, null)
            }
            phoneNumber
        }
    }

    fun openWhatsApp(recipient: String, message: String): Result<String> {
        val phoneNumber = resolvePhoneNumber(recipient)
        val digits = phoneNumber?.replace(Regex("[^0-9]"), "").orEmpty()

        return runCatching {
            if (digits.isNotEmpty()) {
                val uri = Uri.parse("https://wa.me/$digits?text=${Uri.encode(message)}")
                val directIntent = Intent(Intent.ACTION_VIEW, uri).apply {
                    setPackage(WHATSAPP_PACKAGE)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                if (directIntent.resolveActivity(context.packageManager) != null) {
                    context.startActivity(directIntent)
                } else {
                    val fallback = Intent(Intent.ACTION_VIEW, uri).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    context.startActivity(fallback)
                }
                phoneNumber!!
            } else {
                val shareIntent = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_TEXT, message)
                    setPackage(WHATSAPP_PACKAGE)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                if (shareIntent.resolveActivity(context.packageManager) == null) {
                    throw IllegalStateException("WhatsApp no está instalado en el S24+.")
                }
                context.startActivity(shareIntent)
                recipient
            }
        }
    }

    fun resolvePhoneNumber(query: String): String? {
        val trimmed = query.trim()
        if (trimmed.isEmpty()) return null

        val cleanedDigits = trimmed.replace(Regex("[\\s\\-().]"), "")
        if (cleanedDigits.matches(Regex("^\\+?\\d{7,15}$"))) {
            return cleanedDigits
        }

        if (ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.READ_CONTACTS
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            return null
        }

        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
            ContactsContract.CommonDataKinds.Phone.NUMBER
        )
        val selection = "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?"
        val selectionArgs = arrayOf("%$trimmed%")

        context.contentResolver.query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            null
        )?.use { cursor ->
            val numberIdx = cursor.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)
            if (numberIdx >= 0 && cursor.moveToFirst()) {
                val rawNumber = cursor.getString(numberIdx).orEmpty()
                val normalized = rawNumber.replace(Regex("[\\s\\-().]"), "")
                if (normalized.isNotEmpty()) {
                    return normalized
                }
            }
        }
        return null
    }

    companion object {
        private const val WHATSAPP_PACKAGE = "com.whatsapp"
    }
}
