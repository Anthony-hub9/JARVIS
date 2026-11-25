package com.jarvis.hud.presentation.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.automirrored.filled.VolumeOff
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.jarvis.hud.designsystem.components.ArcReactorOrb
import com.jarvis.hud.designsystem.theme.JarvisAmber
import com.jarvis.hud.designsystem.theme.JarvisCyan
import com.jarvis.hud.designsystem.theme.JarvisEmerald
import com.jarvis.hud.designsystem.theme.JarvisError
import com.jarvis.hud.designsystem.theme.JarvisOutline
import com.jarvis.hud.designsystem.theme.JarvisSurface
import com.jarvis.hud.designsystem.theme.JarvisSurfaceVariant
import com.jarvis.hud.domain.model.ChatMessage
import com.jarvis.hud.domain.model.ConnectionStatus
import com.jarvis.hud.domain.model.MobileIntent
import com.jarvis.hud.domain.model.OrbState
import com.jarvis.hud.presentation.JarvisUiState

private val QuickCommands = listOf(
    "¿Qué hora es?",
    "Estado laptop",
    "Abrir WhatsApp",
    "Recordatorio"
)

@Composable
fun HudScreen(
    state: JarvisUiState,
    onOrbClick: () -> Unit,
    onInputChange: (String) -> Unit,
    onSendClick: () -> Unit,
    onQuickCommand: (String) -> Unit,
    onToggleWakeWord: (Boolean) -> Unit,
    onToggleTts: (Boolean) -> Unit,
    onReconnect: () -> Unit,
    onLaunchMobileApp: (MobileIntent) -> Unit,
    onCameraClick: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val listState = rememberLazyListState()

    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty()) {
            listState.animateScrollToItem(state.messages.lastIndex)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        StatusChipRow(
            connectionStatus = state.connectionStatus,
            wakeWordEnabled = state.wakeWordEnabled,
            ttsEnabled = state.ttsEnabled,
            onToggleWakeWord = onToggleWakeWord,
            onToggleTts = onToggleTts,
            onReconnect = onReconnect
        )

        Spacer(modifier = Modifier.height(6.dp))

        ArcReactorOrb(
            state = state.orbState,
            onClick = onOrbClick,
            size = 136.dp
        )

        Spacer(modifier = Modifier.height(8.dp))

        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = PaddingValues(vertical = 4.dp)
        ) {
            if (state.messages.isEmpty()) {
                item {
                    EmptyHudHint()
                }
            } else {
                items(state.messages, key = { it.id }) { msg ->
                    ChatBubble(
                        message = msg,
                        onLaunchMobileApp = onLaunchMobileApp
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            QuickCommands.forEach { cmd ->
                AssistChip(
                    onClick = { onQuickCommand(cmd) },
                    label = { Text(cmd, style = MaterialTheme.typography.labelMedium) },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = JarvisSurface,
                        labelColor = JarvisCyan
                    ),
                    border = BorderStroke(1.dp, JarvisOutline)
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            IconButton(
                onClick = onOrbClick,
                modifier = Modifier.size(48.dp),
                colors = IconButtonDefaults.iconButtonColors(
                    containerColor = if (state.orbState == OrbState.LISTENING) {
                        JarvisEmerald
                    } else {
                        JarvisSurfaceVariant
                    },
                    contentColor = if (state.orbState == OrbState.LISTENING) {
                        MaterialTheme.colorScheme.onSecondary
                    } else {
                        JarvisCyan
                    }
                )
            ) {
                Icon(
                    imageVector = if (state.orbState == OrbState.LISTENING) {
                        Icons.Default.Stop
                    } else {
                        Icons.Default.Mic
                    },
                    contentDescription = "Hablar con JARVIS"
                )
            }

            IconButton(
                onClick = onCameraClick,
                modifier = Modifier.size(48.dp),
                colors = IconButtonDefaults.iconButtonColors(
                    containerColor = JarvisSurfaceVariant,
                    contentColor = JarvisCyan
                )
            ) {
                Icon(
                    imageVector = Icons.Default.PhotoCamera,
                    contentDescription = "Analizar con cámara"
                )
            }

            OutlinedTextField(
                value = state.inputText,
                onValueChange = onInputChange,
                modifier = Modifier.weight(1f),
                placeholder = { Text("Escribe un comando...") },
                singleLine = true,
                shape = RoundedCornerShape(24.dp),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { onSendClick() }),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = JarvisCyan,
                    unfocusedBorderColor = JarvisOutline,
                    focusedContainerColor = JarvisSurface,
                    unfocusedContainerColor = JarvisSurface
                )
            )

            IconButton(
                onClick = onSendClick,
                enabled = state.inputText.isNotBlank(),
                modifier = Modifier.size(48.dp),
                colors = IconButtonDefaults.iconButtonColors(
                    containerColor = JarvisCyan,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                    disabledContainerColor = JarvisSurfaceVariant
                )
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.Send,
                    contentDescription = "Enviar comando"
                )
            }
        }
    }
}

@Composable
private fun StatusChipRow(
    connectionStatus: ConnectionStatus,
    wakeWordEnabled: Boolean,
    ttsEnabled: Boolean,
    onToggleWakeWord: (Boolean) -> Unit,
    onToggleTts: (Boolean) -> Unit,
    onReconnect: () -> Unit
) {
    val (connLabel, connColor) = when (connectionStatus) {
        ConnectionStatus.CONNECTED -> "HUB CONECTADO" to JarvisEmerald
        ConnectionStatus.CONNECTING -> "CONECTANDO..." to JarvisAmber
        ConnectionStatus.ERROR -> "ERROR HUB" to JarvisError
        ConnectionStatus.DISCONNECTED -> "DESCONECTADO" to JarvisError
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        AssistChip(
            onClick = onReconnect,
            label = { Text(connLabel, style = MaterialTheme.typography.labelMedium) },
            leadingIcon = {
                Surface(
                    modifier = Modifier.size(8.dp),
                    shape = CircleShape,
                    color = connColor
                ) {}
            },
            trailingIcon = if (connectionStatus != ConnectionStatus.CONNECTED) {
                {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = "Reconectar",
                        modifier = Modifier.size(16.dp)
                    )
                }
            } else {
                null
            },
            colors = AssistChipDefaults.assistChipColors(
                containerColor = JarvisSurface,
                labelColor = connColor
            ),
            border = BorderStroke(1.dp, connColor.copy(alpha = 0.45f))
        )

        FilterChip(
            selected = wakeWordEnabled,
            onClick = { onToggleWakeWord(!wakeWordEnabled) },
            label = { Text("Wake: Jarvis", style = MaterialTheme.typography.labelMedium) },
            leadingIcon = {
                Icon(
                    imageVector = Icons.Default.GraphicEq,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp)
                )
            },
            colors = FilterChipDefaults.filterChipColors(
                selectedContainerColor = JarvisEmerald.copy(alpha = 0.18f),
                selectedLabelColor = JarvisEmerald,
                selectedLeadingIconColor = JarvisEmerald
            )
        )

        FilterChip(
            selected = ttsEnabled,
            onClick = { onToggleTts(!ttsEnabled) },
            label = { Text("Voz", style = MaterialTheme.typography.labelMedium) },
            leadingIcon = {
                Icon(
                    imageVector = if (ttsEnabled) {
                        Icons.AutoMirrored.Filled.VolumeUp
                    } else {
                        Icons.AutoMirrored.Filled.VolumeOff
                    },
                    contentDescription = null,
                    modifier = Modifier.size(16.dp)
                )
            },
            colors = FilterChipDefaults.filterChipColors(
                selectedContainerColor = JarvisCyan.copy(alpha = 0.18f),
                selectedLabelColor = JarvisCyan,
                selectedLeadingIconColor = JarvisCyan
            )
        )
    }
}

@Composable
private fun ChatBubble(
    message: ChatMessage,
    onLaunchMobileApp: (MobileIntent) -> Unit
) {
    val alignment = if (message.isFromUser) Alignment.End else Alignment.Start
    val containerColor = when {
        message.isFromUser -> JarvisCyan.copy(alpha = 0.16f)
        message.isReminder -> JarvisAmber.copy(alpha = 0.16f)
        message.circuitBroken || !message.approved -> JarvisError.copy(alpha = 0.14f)
        else -> JarvisSurface
    }
    val borderColor = when {
        message.isFromUser -> JarvisCyan.copy(alpha = 0.45f)
        message.isReminder -> JarvisAmber.copy(alpha = 0.55f)
        message.circuitBroken || !message.approved -> JarvisError.copy(alpha = 0.55f)
        else -> JarvisOutline
    }

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = alignment
    ) {
        Card(
            modifier = Modifier.widthIn(max = 310.dp),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = containerColor),
            border = BorderStroke(1.dp, borderColor)
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = message.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )

                if (!message.isFromUser) {
                    Spacer(modifier = Modifier.height(6.dp))
                    val badge = when {
                        message.isReminder -> "RECORDATORIO"
                        message.circuitBroken -> "CIRCUIT BREAKER"
                        message.approved -> "APROBADO • ${message.attempts}x"
                        else -> "NO APROBADO"
                    }
                    val badgeColor = when {
                        message.isReminder -> JarvisAmber
                        message.approved && !message.circuitBroken -> JarvisEmerald
                        else -> JarvisError
                    }
                    Text(
                        text = badge,
                        style = MaterialTheme.typography.labelMedium,
                        color = badgeColor
                    )
                }

                if (message.mobileIntent != null) {
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedButton(
                        onClick = { onLaunchMobileApp(message.mobileIntent) },
                        border = BorderStroke(1.dp, JarvisCyan),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = JarvisCyan)
                    ) {
                        Icon(
                            imageVector = Icons.Default.OpenInNew,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Abrir ${message.mobileIntent.appName}")
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyHudHint() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = JarvisSurface),
        border = BorderStroke(1.dp, JarvisOutline)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "JARVIS HUD LISTO",
                style = MaterialTheme.typography.titleMedium,
                color = JarvisCyan
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Toca el orbe o usa el micrófono para hablar con el Hub en tu Laptop, o activa \"Wake: Jarvis\" para escucha continua.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
