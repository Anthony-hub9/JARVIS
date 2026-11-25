package com.jarvis.hud.designsystem.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val JarvisBg = Color(0xFF050B14)
val JarvisSurface = Color(0xFF0B1728)
val JarvisSurfaceVariant = Color(0xFF11223A)
val JarvisCyan = Color(0xFF00E5FF)
val JarvisCyanDim = Color(0xFF007A99)
val JarvisEmerald = Color(0xFF10B981)
val JarvisError = Color(0xFFEF4444)
val JarvisAmber = Color(0xFFF59E0B)
val JarvisTextPrimary = Color(0xFFE2E8F0)
val JarvisTextSecondary = Color(0xFF94A3B8)
val JarvisOutline = Color(0xFF1E3A5F)

private val JarvisColorScheme = darkColorScheme(
    primary = JarvisCyan,
    onPrimary = JarvisBg,
    primaryContainer = Color(0xFF003642),
    onPrimaryContainer = JarvisCyan,
    secondary = JarvisEmerald,
    onSecondary = JarvisBg,
    secondaryContainer = Color(0xFF064E3B),
    onSecondaryContainer = JarvisEmerald,
    background = JarvisBg,
    onBackground = JarvisTextPrimary,
    surface = JarvisSurface,
    onSurface = JarvisTextPrimary,
    surfaceVariant = JarvisSurfaceVariant,
    onSurfaceVariant = JarvisTextSecondary,
    error = JarvisError,
    onError = Color.White,
    outline = JarvisOutline
)

private val JarvisTypography = Typography(
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 20.sp,
        letterSpacing = 1.2.sp
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        letterSpacing = 0.5.sp
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 14.sp,
        lineHeight = 20.sp
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        letterSpacing = 0.8.sp
    )
)

@Composable
fun JarvisTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = JarvisColorScheme,
        typography = JarvisTypography,
        content = content
    )
}
