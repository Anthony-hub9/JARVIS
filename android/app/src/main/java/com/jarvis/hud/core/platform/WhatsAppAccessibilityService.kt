package com.jarvis.hud.core.platform

import android.accessibilityservice.AccessibilityService
import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import android.text.TextUtils
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.atomic.AtomicLong

object WhatsAppAutoSendArmer {
    private val armedUntilMs = AtomicLong(0L)

    fun arm(timeoutMs: Long = 10_000L) {
        val safeTimeout = timeoutMs.coerceAtLeast(0L)
        armedUntilMs.set(System.currentTimeMillis() + safeTimeout)
    }

    fun isArmed(): Boolean {
        val deadline = armedUntilMs.get()
        if (deadline <= 0L) return false
        if (System.currentTimeMillis() > deadline) {
            armedUntilMs.compareAndSet(deadline, 0L)
            return false
        }
        return true
    }

    fun consumeIfArmed(): Boolean {
        while (true) {
            val deadline = armedUntilMs.get()
            if (deadline <= 0L) return false
            if (System.currentTimeMillis() > deadline) {
                armedUntilMs.compareAndSet(deadline, 0L)
                return false
            }
            if (armedUntilMs.compareAndSet(deadline, 0L)) {
                return true
            }
        }
    }

    fun disarm() {
        armedUntilMs.set(0L)
    }
}

fun isAccessibilityEnabled(context: Context): Boolean {
    val enabled = Settings.Secure.getInt(
        context.contentResolver,
        Settings.Secure.ACCESSIBILITY_ENABLED,
        0
    )
    if (enabled != 1) return false

    val expectedComponent = ComponentName(context, WhatsAppAccessibilityService::class.java)
    val enabledServices = Settings.Secure.getString(
        context.contentResolver,
        Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
    ) ?: return false

    val splitter = TextUtils.SimpleStringSplitter(':')
    splitter.setString(enabledServices)
    while (splitter.hasNext()) {
        val component = ComponentName.unflattenFromString(splitter.next())
        if (component == expectedComponent) {
            return true
        }
    }
    return false
}

class WhatsAppAccessibilityService : AccessibilityService() {

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!WhatsAppAutoSendArmer.isArmed()) return
        val root = rootInActiveWindow ?: return

        val sendNode = findSendButton(root) ?: return
        if (WhatsAppAutoSendArmer.consumeIfArmed()) {
            sendNode.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        }
    }

    override fun onInterrupt() = Unit

    private fun findSendButton(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        for (viewId in SEND_BUTTON_IDS) {
            val matches = root.findAccessibilityNodeInfosByViewId(viewId)
            val clickable = matches.firstOrNull { it.isClickable && it.isEnabled }
            if (clickable != null) return clickable
        }
        return findByContentDescription(root)
    }

    private fun findByContentDescription(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val desc = node.contentDescription?.toString()?.trim()
        if (node.isClickable && node.isEnabled && desc != null &&
            (desc.equals("Enviar", ignoreCase = true) || desc.equals("Send", ignoreCase = true))
        ) {
            return node
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findByContentDescription(child)
            if (found != null) return found
        }
        return null
    }

    companion object {
        private val SEND_BUTTON_IDS = listOf(
            "com.whatsapp:id/send",
            "com.whatsapp.w4b:id/send"
        )
    }
}
