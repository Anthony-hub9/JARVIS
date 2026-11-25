package com.jarvis.hud.presentation

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Base64
import java.io.ByteArrayOutputStream
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.jarvis.hud.designsystem.theme.JarvisBg
import com.jarvis.hud.designsystem.theme.JarvisCyan
import com.jarvis.hud.designsystem.theme.JarvisSurface
import com.jarvis.hud.designsystem.theme.JarvisTextSecondary
import com.jarvis.hud.designsystem.theme.JarvisTheme
import com.jarvis.hud.presentation.screens.AgendaScreen
import com.jarvis.hud.presentation.screens.AppsControlScreen
import com.jarvis.hud.presentation.screens.HudScreen

private enum class HudTab(
    val route: String,
    val label: String,
    val icon: ImageVector
) {
    HUD("hud", "HUD", Icons.Default.GraphicEq),
    AGENDA("agenda", "Agenda", Icons.Default.CalendarMonth),
    CONTROL("control", "Control", Icons.Default.Tune)
}

class MainActivity : ComponentActivity() {

    private val viewModel: JarvisViewModel by viewModels {
        JarvisViewModel.Factory(applicationContext)
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ -> }

    private val cameraLauncher = registerForActivityResult(
        ActivityResultContracts.TakePicturePreview()
    ) { bitmap ->
        if (bitmap != null) {
            val encoded = encodeBitmapForVision(bitmap)
            viewModel.sendVisionBitmap(encoded)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        requestRequiredPermissions()

        setContent {
            JarvisTheme {
                JarvisRootApp(
                    viewModel = viewModel,
                    onOpenNotificationSettings = {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    },
                    onLaunchCamera = {
                        cameraLauncher.launch(null)
                    }
                )
            }
        }
    }

    private fun encodeBitmapForVision(bitmap: Bitmap): String {
        val scaled = if (bitmap.width > MAX_VISION_WIDTH) {
            val targetHeight = (bitmap.height * (MAX_VISION_WIDTH.toFloat() / bitmap.width)).toInt().coerceAtLeast(1)
            Bitmap.createScaledBitmap(bitmap, MAX_VISION_WIDTH, targetHeight, true)
        } else {
            bitmap
        }
        val out = ByteArrayOutputStream()
        scaled.compress(Bitmap.CompressFormat.JPEG, VISION_JPEG_QUALITY, out)
        return Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }

    companion object {
        private const val MAX_VISION_WIDTH = 1024
        private const val VISION_JPEG_QUALITY = 82
    }

    override fun onResume() {
        super.onResume()
        viewModel.refreshNotificationAccess()
    }

    private fun requestRequiredPermissions() {
        val needed = buildList {
            if (!hasPermission(Manifest.permission.RECORD_AUDIO)) {
                add(Manifest.permission.RECORD_AUDIO)
            }
            if (!hasPermission(Manifest.permission.ANSWER_PHONE_CALLS)) {
                add(Manifest.permission.ANSWER_PHONE_CALLS)
            }
            if (!hasPermission(Manifest.permission.READ_PHONE_STATE)) {
                add(Manifest.permission.READ_PHONE_STATE)
            }
            if (!hasPermission(Manifest.permission.SEND_SMS)) {
                add(Manifest.permission.SEND_SMS)
            }
            if (!hasPermission(Manifest.permission.READ_CONTACTS)) {
                add(Manifest.permission.READ_CONTACTS)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                !hasPermission(Manifest.permission.POST_NOTIFICATIONS)
            ) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        if (needed.isNotEmpty()) {
            permissionLauncher.launch(needed.toTypedArray())
        }
    }

    private fun hasPermission(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED
}

@Composable
private fun JarvisRootApp(
    viewModel: JarvisViewModel,
    onOpenNotificationSettings: () -> Unit,
    onLaunchCamera: () -> Unit
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val navController = rememberNavController()
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(state.statusBanner) {
        val msg = state.statusBanner ?: return@LaunchedEffect
        snackbarHostState.showSnackbar(msg)
        viewModel.clearBanner()
    }

    Scaffold(
        containerColor = JarvisBg,
        snackbarHost = { SnackbarHost(hostState = snackbarHostState) },
        bottomBar = {
            NavigationBar(containerColor = JarvisSurface) {
                val navBackStackEntry by navController.currentBackStackEntryAsState()
                val currentDestination = navBackStackEntry?.destination
                HudTab.entries.forEach { tab ->
                    val selected = currentDestination?.hierarchy?.any { it.route == tab.route } == true
                    NavigationBarItem(
                        selected = selected,
                        onClick = {
                            navController.navigate(tab.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = JarvisCyan,
                            selectedTextColor = JarvisCyan,
                            indicatorColor = JarvisCyan.copy(alpha = 0.16f),
                            unselectedIconColor = JarvisTextSecondary,
                            unselectedTextColor = JarvisTextSecondary
                        )
                    )
                }
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = HudTab.HUD.route,
            modifier = Modifier.padding(innerPadding)
        ) {
            composable(HudTab.HUD.route) {
                HudScreen(
                    state = state,
                    onOrbClick = viewModel::onOrbOrMicClicked,
                    onInputChange = viewModel::onInputTextChanged,
                    onSendClick = viewModel::sendCurrentInput,
                    onQuickCommand = viewModel::sendCommand,
                    onToggleWakeWord = viewModel::toggleWakeWord,
                    onToggleTts = viewModel::toggleTts,
                    onReconnect = viewModel::reconnectHub,
                    onLaunchMobileApp = viewModel::launchMobileApp,
                    onCameraClick = onLaunchCamera
                )
            }
            composable(HudTab.AGENDA.route) {
                AgendaScreen(
                    items = state.agendaItems,
                    isLoading = state.isAgendaLoading,
                    onRefresh = viewModel::refreshAgenda,
                    onCreateAgenda = viewModel::createAgendaItem
                )
            }
            composable(HudTab.CONTROL.route) {
                AppsControlScreen(
                    hubUrl = state.hubUrl,
                    voiceProfile = state.voiceProfile,
                    health = state.health,
                    apps = state.laptopApps,
                    searchQuery = state.appSearchQuery,
                    isAppsLoading = state.isAppsLoading,
                    onSearchChange = viewModel::onAppSearchChanged,
                    onRefreshApps = viewModel::refreshApps,
                    onOpenLaptopApp = viewModel::openLaptopApp,
                    onSaveHubUrl = viewModel::updateHubUrl,
                    onSelectVoiceProfile = viewModel::updateVoiceProfile,
                    notificationAccessEnabled = state.notificationAccessEnabled,
                    onOpenNotificationSettings = onOpenNotificationSettings,
                    backgroundServiceEnabled = state.backgroundServiceEnabled,
                    onToggleBackgroundService = viewModel::toggleBackgroundService
                )
            }
        }
    }
}
