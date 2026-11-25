package com.jarvis.hud.presentation.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.Launch
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.hud.designsystem.theme.JarvisBg
import com.jarvis.hud.designsystem.theme.JarvisCyan
import com.jarvis.hud.designsystem.theme.JarvisEmerald
import com.jarvis.hud.designsystem.theme.JarvisOutline
import com.jarvis.hud.designsystem.theme.JarvisSurface
import com.jarvis.hud.designsystem.theme.JarvisTextSecondary
import com.jarvis.hud.domain.model.HubHealth
import com.jarvis.hud.domain.model.VoiceProfile

@Composable
fun AppsControlScreen(
    hubUrl: String,
    voiceProfile: VoiceProfile,
    health: HubHealth?,
    apps: List<String>,
    searchQuery: String,
    isAppsLoading: Boolean,
    onSearchChange: (String) -> Unit,
    onRefreshApps: () -> Unit,
    onOpenLaptopApp: (String) -> Unit,
    onSaveHubUrl: (String) -> Unit,
    onSelectVoiceProfile: (VoiceProfile) -> Unit,
    notificationAccessEnabled: Boolean = false,
    onOpenNotificationSettings: () -> Unit = {},
    accessibilityEnabled: Boolean = false,
    onOpenAccessibilitySettings: () -> Unit = {},
    backgroundServiceEnabled: Boolean = false,
    onToggleBackgroundService: (Boolean) -> Unit = {},
    modifier: Modifier = Modifier
) {
    var urlDraft by remember(hubUrl) { mutableStateOf(hubUrl) }

    val filteredApps = remember(apps, searchQuery) {
        if (searchQuery.isBlank()) {
            apps
        } else {
            apps.filter { it.contains(searchQuery.trim(), ignoreCase = true) }
        }
    }

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        contentPadding = PaddingValues(bottom = 24.dp)
    ) {
        item {
            HubSettingsCard(
                urlDraft = urlDraft,
                onUrlDraftChange = { urlDraft = it },
                onSaveUrl = { onSaveHubUrl(urlDraft) },
                voiceProfile = voiceProfile,
                onSelectVoice = onSelectVoiceProfile,
                health = health
            )
        }

        item {
            MobileCommsCard(
                notificationAccessEnabled = notificationAccessEnabled,
                onOpenNotificationSettings = onOpenNotificationSettings,
                accessibilityEnabled = accessibilityEnabled,
                onOpenAccessibilitySettings = onOpenAccessibilitySettings,
                backgroundServiceEnabled = backgroundServiceEnabled,
                onToggleBackgroundService = onToggleBackgroundService
            )
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "APPS DE LA LAPTOP (${filteredApps.size})",
                    style = MaterialTheme.typography.titleMedium,
                    color = JarvisCyan
                )
                IconButton(onClick = onRefreshApps) {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = "Actualizar apps",
                        tint = JarvisCyan
                    )
                }
            }

            OutlinedTextField(
                value = searchQuery,
                onValueChange = onSearchChange,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Buscar app en la Laptop...") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                singleLine = true,
                shape = RoundedCornerShape(14.dp)
            )

            if (isAppsLoading) {
                Spacer(modifier = Modifier.height(6.dp))
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = JarvisCyan)
            }
        }

        if (filteredApps.isEmpty() && !isAppsLoading) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = JarvisSurface),
                    border = BorderStroke(1.dp, JarvisOutline)
                ) {
                    Text(
                        text = "No se encontraron aplicaciones.",
                        modifier = Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        } else {
            items(filteredApps, key = { it }) { appName ->
                LaptopAppRow(
                    appName = appName,
                    onOpen = { onOpenLaptopApp(appName) }
                )
            }
        }
    }
}

@Composable
private fun HubSettingsCard(
    urlDraft: String,
    onUrlDraftChange: (String) -> Unit,
    onSaveUrl: () -> Unit,
    voiceProfile: VoiceProfile,
    onSelectVoice: (VoiceProfile) -> Unit,
    health: HubHealth?
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = JarvisSurface),
        border = BorderStroke(1.dp, JarvisOutline)
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text(
                text = "CONEXIÓN HUB & VOZ",
                style = MaterialTheme.typography.titleMedium,
                color = JarvisCyan
            )

            if (health != null) {
                Text(
                    text = "Ollama: ${health.executor} • Estado: ${health.status.uppercase()}",
                    style = MaterialTheme.typography.labelMedium,
                    color = JarvisEmerald
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = urlDraft,
                    onValueChange = onUrlDraftChange,
                    modifier = Modifier.weight(1f),
                    label = { Text("URL del Hub (Tailscale)") },
                    singleLine = true
                )
                Spacer(modifier = Modifier.width(8.dp))
                Button(
                    onClick = onSaveUrl,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = JarvisCyan,
                        contentColor = JarvisBg
                    )
                ) {
                    Text("Guardar")
                }
            }

            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Voz:",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                VoiceProfile.entries.forEach { profile ->
                    FilterChip(
                        selected = voiceProfile == profile,
                        onClick = { onSelectVoice(profile) },
                        label = { Text(profile.label) },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = JarvisCyan.copy(alpha = 0.2f),
                            selectedLabelColor = JarvisCyan
                        )
                    )
                }
            }
        }
    }
}

@Composable
private fun MobileCommsCard(
    notificationAccessEnabled: Boolean,
    onOpenNotificationSettings: () -> Unit,
    accessibilityEnabled: Boolean,
    onOpenAccessibilitySettings: () -> Unit,
    backgroundServiceEnabled: Boolean,
    onToggleBackgroundService: (Boolean) -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = JarvisSurface),
        border = BorderStroke(1.dp, JarvisOutline)
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "LLAMADAS Y MENSAJES (S24+)",
                style = MaterialTheme.typography.titleMedium,
                color = JarvisCyan
            )
            Text(
                text = if (notificationAccessEnabled) {
                    "Acceso a notificaciones: Activo (WhatsApp, SMS, Telegram)"
                } else {
                    "Acceso a notificaciones: Desactivado (requerido para leer y responder mensajes)"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = if (notificationAccessEnabled) {
                    JarvisEmerald
                } else {
                    MaterialTheme.colorScheme.error
                }
            )
            Button(
                onClick = onOpenNotificationSettings,
                colors = ButtonDefaults.buttonColors(
                    containerColor = JarvisCyan,
                    contentColor = JarvisBg
                )
            ) {
                Text(
                    if (notificationAccessEnabled) {
                        "Gestionar acceso a notificaciones"
                    } else {
                        "Activar acceso a notificaciones"
                    }
                )
            }

            Text(
                text = if (accessibilityEnabled) {
                    "Auto-envío WhatsApp (Accesibilidad): Activo"
                } else {
                    "Auto-envío WhatsApp (Accesibilidad): Desactivado (opcional)"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = if (accessibilityEnabled) {
                    JarvisEmerald
                } else {
                    JarvisTextSecondary
                }
            )
            Button(
                onClick = onOpenAccessibilitySettings,
                colors = ButtonDefaults.buttonColors(
                    containerColor = JarvisCyan,
                    contentColor = JarvisBg
                )
            ) {
                Text(
                    if (accessibilityEnabled) {
                        "Gestionar accesibilidad WhatsApp"
                    } else {
                        "Activar auto-envío WhatsApp"
                    }
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Servicio en segundo plano",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Switch(
                    checked = backgroundServiceEnabled,
                    onCheckedChange = onToggleBackgroundService,
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = JarvisBg,
                        checkedTrackColor = JarvisCyan
                    )
                )
            }
        }
    }
}

@Composable
private fun LaptopAppRow(
    appName: String,
    onOpen: () -> Unit
) {
    Card(
        onClick = onOpen,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = JarvisSurface),
        border = BorderStroke(1.dp, JarvisOutline)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Default.Computer,
                contentDescription = null,
                tint = JarvisCyan
            )
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                text = appName,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.weight(1f)
            )
            Icon(
                imageVector = Icons.Default.Launch,
                contentDescription = "Abrir $appName",
                tint = JarvisEmerald
            )
        }
    }
}
