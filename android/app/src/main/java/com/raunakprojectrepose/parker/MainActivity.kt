package com.raunakprojectrepose.parker

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

class MainActivity : ComponentActivity() {
    private val vm: ParkerViewModel by viewModels()
    private var pairProblem by mutableStateOf<String?>(null)

    private val scan = registerForActivityResult(ScanContract()) { result ->
        val text = result.contents ?: return@registerForActivityResult
        pairProblem = if (vm.pair(text)) null else "That isn't a PARKER pairing code."
    }

    private val askMic = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) vm.toggleTalking()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ParkerTheme {
                if (vm.pairing == null) {
                    PairScreen(onScan = ::startScan, problem = pairProblem)
                } else {
                    ChatScreen(vm.withMicPermission(), onUnpair = vm::unpair)
                }
            }
        }
    }

    private fun startScan() {
        scan.launch(
            ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt("Scan the code from PARKER → Settings → Pair phone…")
                .setBeepEnabled(false).setOrientationLocked(true),
        )
    }

    /** The mic button asks for microphone permission the first time it's used. */
    private fun ParkerViewModel.withMicPermission(): ParkerViewModel {
        micGate = {
            val allowed = ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED
            if (!allowed) askMic.launch(Manifest.permission.RECORD_AUDIO)
            allowed
        }
        return this
    }
}
