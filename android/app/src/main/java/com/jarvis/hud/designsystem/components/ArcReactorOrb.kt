package com.jarvis.hud.designsystem.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.jarvis.hud.designsystem.theme.JarvisAmber
import com.jarvis.hud.designsystem.theme.JarvisCyan
import com.jarvis.hud.designsystem.theme.JarvisEmerald
import com.jarvis.hud.domain.model.OrbState

@Composable
fun ArcReactorOrb(
    state: OrbState,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    size: Dp = 156.dp
) {
    val accentColor by animateColorAsState(
        targetValue = when (state) {
            OrbState.IDLE -> JarvisCyan
            OrbState.LISTENING -> JarvisEmerald
            OrbState.THINKING -> JarvisAmber
            OrbState.SPEAKING -> JarvisCyan
        },
        animationSpec = tween(durationMillis = 350),
        label = "orbColor"
    )

    val transition = rememberInfiniteTransition(label = "arcReactor")
    val pulseDuration = when (state) {
        OrbState.IDLE -> 2600
        OrbState.LISTENING -> 900
        OrbState.THINKING -> 700
        OrbState.SPEAKING -> 550
    }
    val rotationDuration = when (state) {
        OrbState.IDLE -> 9000
        OrbState.LISTENING -> 3200
        OrbState.THINKING -> 1600
        OrbState.SPEAKING -> 2400
    }

    val pulse by transition.animateFloat(
        initialValue = 0.86f,
        targetValue = 1.0f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = pulseDuration),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse"
    )
    val rotation by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = rotationDuration, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "rotation"
    )

    val stateLabel = when (state) {
        OrbState.IDLE -> "EN ESPERA"
        OrbState.LISTENING -> "ESCUCHANDO"
        OrbState.THINKING -> "PROCESANDO"
        OrbState.SPEAKING -> "HABLANDO"
    }

    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .size(size)
                .semantics { contentDescription = "Orbe JARVIS: $stateLabel" }
                .clickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                    role = Role.Button,
                    onClick = onClick
                ),
            contentAlignment = Alignment.Center
        ) {
            Canvas(modifier = Modifier.size(size)) {
                val center = Offset(this.size.width / 2f, this.size.height / 2f)
                val maxRadius = this.size.minDimension / 2f

                // Outer glow
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            accentColor.copy(alpha = 0.30f * pulse),
                            accentColor.copy(alpha = 0.08f),
                            Color.Transparent
                        ),
                        center = center,
                        radius = maxRadius
                    ),
                    radius = maxRadius,
                    center = center
                )

                // Outer segmented rotating ring
                val outerR = maxRadius * 0.80f
                val outerTopLeft = Offset(center.x - outerR, center.y - outerR)
                val outerSize = Size(outerR * 2f, outerR * 2f)
                for (i in 0 until 4) {
                    drawArc(
                        color = accentColor.copy(alpha = 0.85f),
                        startAngle = rotation + i * 90f,
                        sweepAngle = 58f,
                        useCenter = false,
                        topLeft = outerTopLeft,
                        size = outerSize,
                        style = Stroke(width = 5.dp.toPx(), cap = StrokeCap.Round)
                    )
                }

                // Counter-rotating inner ring
                val innerR = maxRadius * 0.58f
                val innerTopLeft = Offset(center.x - innerR, center.y - innerR)
                val innerSize = Size(innerR * 2f, innerR * 2f)
                for (i in 0 until 3) {
                    drawArc(
                        color = accentColor.copy(alpha = 0.65f),
                        startAngle = -rotation * 1.4f + i * 120f,
                        sweepAngle = 82f,
                        useCenter = false,
                        topLeft = innerTopLeft,
                        size = innerSize,
                        style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round)
                    )
                }

                // Core reactor circle
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            Color.White.copy(alpha = 0.95f),
                            accentColor.copy(alpha = 0.85f),
                            accentColor.copy(alpha = 0.25f)
                        ),
                        center = center,
                        radius = maxRadius * 0.36f * pulse
                    ),
                    radius = maxRadius * 0.34f * pulse,
                    center = center
                )
            }
        }

        Spacer(modifier = Modifier.height(6.dp))

        Text(
            text = stateLabel,
            style = MaterialTheme.typography.labelMedium,
            color = accentColor
        )
    }
}
