package com.raunakprojectrepose.parker

import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest

class PairingTest {
    private val fp = "ab".repeat(32)

    @Test fun parsesTheLaptopsQrCode() {
        val p = Pairing.parse("""{"app":"parker","v":1,"hosts":["192.168.1.20","100.64.0.7"],"port":8765,"token":"${"t".repeat(43)}","fp":"$fp","name":"Raunak"}""")!!
        assertEquals(listOf("192.168.1.20", "100.64.0.7"), p.hosts)
        assertEquals(8765, p.port)
        assertEquals(fp, p.fingerprint)
        assertEquals(p, Pairing.parse(p.toJson()))
    }

    @Test fun rejectsOtherCodes() {
        assertNull(Pairing.parse("https://example.com"))
        assertNull(Pairing.parse("""{"app":"other","hosts":["1.2.3.4"],"token":"${"t".repeat(43)}","fp":"$fp"}"""))
        assertNull(Pairing.parse("""{"app":"parker","hosts":[],"token":"${"t".repeat(43)}","fp":"$fp"}"""))
        assertNull(Pairing.parse("""{"app":"parker","hosts":["1.2.3.4"],"token":"short","fp":"$fp"}"""))
        assertNull(Pairing.parse("""{"app":"parker","hosts":["1.2.3.4"],"token":"${"t".repeat(43)}","fp":"not-a-hash"}"""))
    }
}

class WavTest {
    @Test fun wavHeaderMatchesWhatTheLaptopExpects() {
        val pcm = ByteArray(32000) // one second of silence
        val wav = pcmToWav(pcm)
        val b = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals("RIFF", String(wav, 0, 4))
        assertEquals("WAVE", String(wav, 8, 4))
        assertEquals(1, b.getShort(20).toInt())      // PCM
        assertEquals(1, b.getShort(22).toInt())      // mono
        assertEquals(16000, b.getInt(24))            // sample rate
        assertEquals(16, b.getShort(34).toInt())     // 16-bit
        assertEquals(32000, b.getInt(40))            // data size
        assertEquals(44 + 32000, wav.size)
    }
}

class PinningTest {
    private lateinit var server: MockWebServer
    private lateinit var laptopCert: HeldCertificate
    private val token = "secret-token-" + "x".repeat(30)

    private fun fingerprint(cert: HeldCertificate) =
        MessageDigest.getInstance("SHA-256").digest(cert.certificate.encoded).joinToString("") { "%02x".format(it) }

    @Before fun start() {
        laptopCert = HeldCertificate.Builder().commonName("PARKER companion").build()
        server = MockWebServer()
        server.useHttps(HandshakeCertificates.Builder().heldCertificate(laptopCert).build().sslSocketFactory(), false)
        server.start()
    }

    @After fun stop() = server.shutdown()

    private fun pairing(fp: String) = Pairing(listOf(server.hostName), server.port, token, fp, "Raunak")

    @Test fun connectsToThePairedLaptopAndSendsTheToken() {
        server.enqueue(MockResponse().setBody("""{"app":"parker"}"""))
        server.enqueue(MockResponse().setBody("""{"messages":[{"kind":"parker","text":"Hello Raunak"}],"confirm":{"id":"c1","question":"Add it?"}}"""))
        val client = ParkerClient(pairing(fingerprint(laptopCert)))
        client.connect()
        val reply = client.message("Hi")
        assertEquals(listOf(ChatMessage("parker", "Hello Raunak")), reply.messages)
        assertEquals(Confirmation("c1", "Add it?"), reply.confirm)
        assertEquals("Bearer $token", server.takeRequest().getHeader("Authorization"))
        val sent = server.takeRequest()
        assertEquals("/api/message", sent.path)
        assertTrue(sent.body.readUtf8().contains("\"text\":\"Hi\""))
    }

    @Test fun refusesAServerWithAnyOtherCertificate() {
        val impostor = HeldCertificate.Builder().commonName("PARKER companion").build()
        server.enqueue(MockResponse().setBody("""{"app":"parker"}"""))
        try {
            ParkerClient(pairing(fingerprint(impostor))).connect()
            fail("Connected to a server whose certificate wasn't the paired one")
        } catch (e: ParkerException) {
            assertTrue(e.message!!.contains("Can't reach PARKER"))
        }
        assertEquals(0, server.requestCount) // nothing (not even the token) was sent
    }

    @Test fun explainsWhenThePhoneWasUnpaired() {
        server.enqueue(MockResponse().setResponseCode(401))
        try {
            ParkerClient(pairing(fingerprint(laptopCert))).today()
            fail("Expected an error")
        } catch (e: ParkerException) {
            assertTrue(e.message!!.contains("Can't reach PARKER") || e.message!!.contains("isn't paired"))
        }
    }

    @Test fun parsesVoiceReplies() {
        val r = ParkerClient.parseReply("""{"heard":"What's on today?","messages":[{"kind":"note","text":"x"}]}""")
        assertEquals("What's on today?", r.heard)
        assertNull(r.confirm)
    }
}
