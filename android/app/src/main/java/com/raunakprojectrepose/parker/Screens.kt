package com.raunakprojectrepose.parker

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val background = Brush.verticalGradient(listOf(Color.White, Gold.Ivory, Gold.Cream))

@Composable
fun PairScreen(onScan: () -> Unit, problem: String?) {
    Column(
        Modifier.fillMaxSize().background(background).safeDrawingPadding().padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Orb(Status.Ready, 140)
        Spacer(Modifier.height(28.dp))
        Wordmark()
        Spacer(Modifier.height(18.dp))
        Text(
            "On your laptop, open PARKER → Settings → Pair phone…, then scan the code. " +
                "Your phone must be on the same Wi-Fi.",
            color = Gold.Muted, fontSize = 15.sp,
        )
        Spacer(Modifier.height(28.dp))
        Button(onClick = onScan, colors = ButtonDefaults.buttonColors(containerColor = Gold.Main)) {
            Text("Pair with laptop", fontWeight = FontWeight.SemiBold)
        }
        problem?.let { Spacer(Modifier.height(16.dp)); Text(it, color = Gold.Error, fontSize = 14.sp) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(vm: ParkerViewModel, onUnpair: () -> Unit) {
    var showToday by remember { mutableStateOf(false) }
    var draft by remember { mutableStateOf("") }
    val list = rememberLazyListState()
    LaunchedEffect(vm.messages.size) { if (vm.messages.isNotEmpty()) list.animateScrollToItem(vm.messages.size - 1) }

    Column(Modifier.fillMaxSize().background(background).safeDrawingPadding().imePadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Wordmark()
            Spacer(Modifier.weight(1f))
            TextButton(onClick = { vm.refreshToday(); showToday = true }) { Text("Today", color = Gold.Deep) }
        }
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            Orb(vm.status, 96)
            Text(vm.status.label, color = Gold.Muted, fontSize = 11.sp, letterSpacing = 2.sp)
        }
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth().padding(horizontal = 14.dp),
            state = list, verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(vm.messages) { Bubble(it) }
        }
        Row(
            Modifier.padding(12.dp).clip(RoundedCornerShape(28.dp)).background(Color.White).padding(start = 6.dp, end = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextField(
                value = draft, onValueChange = { draft = it }, modifier = Modifier.weight(1f),
                placeholder = { Text("Ask PARKER anything…", color = Gold.Muted) },
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = Color.White, unfocusedContainerColor = Color.White,
                    focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent,
                ),
                singleLine = true,
            )
            if (draft.isNotBlank()) {
                TextButton(onClick = { vm.send(draft); draft = "" }) { Text("Send", color = Gold.Deep, fontWeight = FontWeight.SemiBold) }
            }
            MicButton(vm.status) { vm.toggleTalking() }
        }
    }

    vm.confirmation?.let { c ->
        AlertDialog(
            onDismissRequest = { vm.answer(false) },
            title = { Text("Add to Google Calendar?") },
            text = { Text(c.question) },
            confirmButton = { TextButton(onClick = { vm.answer(true) }) { Text("Add", color = Gold.Deep) } },
            dismissButton = { TextButton(onClick = { vm.answer(false) }) { Text("Cancel", color = Gold.Muted) } },
        )
    }
    vm.problem?.let { p ->
        AlertDialog(
            onDismissRequest = vm::dismissProblem,
            title = { Text("PARKER") },
            text = { Text(p) },
            confirmButton = { TextButton(onClick = { vm.dismissProblem(); vm.connect() }) { Text("Try again", color = Gold.Deep) } },
            dismissButton = { TextButton(onClick = vm::dismissProblem) { Text("OK", color = Gold.Muted) } },
        )
    }
    if (showToday) {
        ModalBottomSheet(onDismissRequest = { showToday = false }, containerColor = Gold.Ivory) {
            TodaySheet(vm, onUnpair = { showToday = false; onUnpair() })
        }
    }
}

@Composable
private fun TodaySheet(vm: ParkerViewModel, onUnpair: () -> Unit) {
    val t = vm.today
    LazyColumn(Modifier.fillMaxWidth().padding(horizontal = 22.dp).padding(bottom = 28.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        item { Text("Today", fontFamily = FontFamily.Serif, fontSize = 24.sp, color = Gold.Deep, fontWeight = FontWeight.SemiBold) }
        if (t == null) item { Text("Loading…", color = Gold.Muted) } else {
            item { Text(t.greeting, color = Gold.Text) }
            section("Plans for this session", t.plans.map { it to "" })
            section("Next 7 days", t.events.map { it.text to (it.whenText + if (it.source == "google") " · Google" else "") })
            section("Reminders", t.reminders.map { it.text to it.whenText })
            section("What PARKER remembers", t.memories.map { it to "" })
        }
        item {
            Row(Modifier.fillMaxWidth().padding(top = 18.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Speak replies", color = Gold.Text, modifier = Modifier.weight(1f))
                Switch(checked = vm.speakReplies, onCheckedChange = { vm.speakReplies = it })
            }
        }
        item {
            OutlinedButton(onClick = onUnpair, modifier = Modifier.padding(top = 8.dp)) { Text("Unpair this phone", color = Gold.Deep) }
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.section(title: String, rows: List<Pair<String, String>>) {
    item { Text(title.uppercase(), color = Gold.Muted, fontSize = 11.sp, letterSpacing = 2.sp, modifier = Modifier.padding(top = 14.dp)) }
    if (rows.isEmpty()) item { Text("Nothing yet", color = Gold.Muted, fontSize = 14.sp) }
    items(rows) { (text, sub) ->
        Card(colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(14.dp)) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp)) {
                Text(text, color = Gold.Text)
                if (sub.isNotBlank()) Text(sub, color = Gold.Muted, fontSize = 13.sp)
            }
        }
    }
}

@Composable
private fun Bubble(m: ChatMessage) {
    val mine = m.fromMe
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
        when (m.kind) {
            "note", "error" -> Text(
                m.text, color = if (m.kind == "error") Gold.Error else Gold.Muted, fontSize = 14.sp,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
            )
            else -> Box(
                Modifier.widthIn(max = 300.dp).clip(RoundedCornerShape(20.dp))
                    .background(if (mine) Gold.Pale else Color.White).padding(horizontal = 16.dp, vertical = 11.dp),
            ) { Text(m.text, color = Gold.Text, fontSize = 16.sp) }
        }
    }
}

@Composable
private fun Wordmark() =
    Text("P A R K E R", fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold, color = Gold.Deep, fontSize = 18.sp)

@Composable
private fun MicButton(status: Status, onClick: () -> Unit) {
    val listening = status == Status.Listening
    val speaking = status == Status.Speaking
    Box(
        Modifier.size(48.dp).clip(CircleShape)
            .background(
                when {
                    listening -> Brush.radialGradient(listOf(Color.White, Color(0xFFEBC350)))
                    speaking -> Brush.radialGradient(listOf(Gold.Deep, Gold.Deep))
                    else -> Brush.radialGradient(listOf(Color(0xFFF2D88A), Gold.Main))
                },
            ),
        contentAlignment = Alignment.Center,
    ) {
        TextButton(onClick = onClick, enabled = status != Status.Thinking && status != Status.Connecting) {
            Text(
                when { listening -> "✓"; speaking -> "■"; else -> "🎙" },
                color = if (listening) Gold.Deep else Color.White, fontSize = 18.sp,
            )
        }
    }
}

/** The glowing golden orb: breathes when ready, ripples while listening, pulses while speaking. */
@Composable
fun Orb(status: Status, sizeDp: Int) {
    val t = rememberInfiniteTransition(label = "orb")
    val speed = when (status) { Status.Listening -> 900; Status.Speaking -> 600; Status.Thinking -> 1200; else -> 2600 }
    val phase by t.animateFloat(0f, 1f, infiniteRepeatable(tween(speed, easing = LinearEasing), RepeatMode.Reverse), label = "breath")
    val dim = status == Status.Offline || status == Status.Connecting
    Canvas(Modifier.size(sizeDp.dp)) {
        val c = Offset(size.width / 2, size.height / 2)
        val full = size.minDimension / 2
        val depth = when (status) { Status.Listening -> 0.16f; Status.Speaking -> 0.14f; else -> 0.06f }
        val haloR = full * (0.78f + depth * phase)
        val haloAlpha = if (dim) 0.25f else 0.55f
        drawCircle(Brush.radialGradient(listOf(Gold.Main.copy(alpha = haloAlpha), Color.Transparent), c, haloR), haloR, c)
        if (status == Status.Listening) {
            drawCircle(Gold.Light.copy(alpha = 1f - phase), full * (0.45f + 0.45f * phase), c, style = Stroke(3f))
        }
        val coreR = full * (0.38f + 0.03f * phase)
        drawCircle(
            Brush.radialGradient(listOf(Color.White, Color(0xFFFFF3CF), Gold.Main), Offset(c.x - coreR * 0.3f, c.y - coreR * 0.3f), coreR * 1.4f),
            coreR, c,
        )
    }
}
