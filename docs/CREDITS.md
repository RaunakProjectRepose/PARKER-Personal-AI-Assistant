# Credits

## Voice

PARKER speaks with the Piper voice **en_GB-alba-medium**.

- Dataset: https://datashare.ed.ac.uk/handle/10283/3270
- Dataset licence: [Creative Commons Attribution 4.0 (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- Voice model: [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices), fine-tuned from the
  `hifi_tts_92` base model (per the voice's MODEL_CARD).

CC BY 4.0 allows use, including commercial use, as long as the source is credited.
Voice files are downloaded locally into `voices/` and are not stored in this repository.

## Text-to-speech engine

[Piper](https://github.com/OHF-Voice/piper1-gpl) (`piper-tts`), licensed GPL-3.0-or-later.

## Speech recognition

[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) (MIT) running OpenAI's
[Whisper](https://github.com/openai/whisper) `small.en` model (MIT), entirely on this laptop.
Microphone access via [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) (MIT).
