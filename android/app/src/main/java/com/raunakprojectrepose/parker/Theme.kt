package com.raunakprojectrepose.parker

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** The same "heavenly gold" palette as the desktop app. */
object Gold {
    val Ivory = Color(0xFFFFFDF6)
    val Cream = Color(0xFFF7EDD3)
    val Main = Color(0xFFC9A227)
    val Light = Color(0xFFE9CF7A)
    val Pale = Color(0xFFF4E6BC)
    val Deep = Color(0xFF9C7A12)
    val Text = Color(0xFF4A3B1A)
    val Muted = Color(0xFF8C7A55)
    val Error = Color(0xFFA94428)
}

@Composable
fun ParkerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Gold.Main, onPrimary = Color.White, secondary = Gold.Deep,
            background = Gold.Ivory, surface = Color.White, onSurface = Gold.Text,
            onBackground = Gold.Text, error = Gold.Error,
        ),
        content = content,
    )
}
