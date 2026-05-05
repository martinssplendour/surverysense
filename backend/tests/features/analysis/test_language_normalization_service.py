import unittest

from app.features.analysis.language_normalization_service import (
    EnglishTranslationConfig,
    EnglishTranslationService,
)


class _FakeTranslator:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping
        self.batch_calls: list[list[str]] = []
        self.single_calls: list[str] = []

    def translate_batch(self, texts: list[str]) -> list[str]:
        self.batch_calls.append(list(texts))
        return [self.mapping.get(text, text) for text in texts]

    def translate(self, text: str) -> str:
        self.single_calls.append(text)
        return self.mapping.get(text, text)


class EnglishTranslationServiceTests(unittest.TestCase):
    def build_service(self, *, cache_ttl_seconds: int = 900, clock=None) -> EnglishTranslationService:
        return EnglishTranslationService(
            config=EnglishTranslationConfig(
                enabled=True,
                source_language="auto",
                target_language="en",
                batch_size=8,
            ),
            cache_ttl_seconds=cache_ttl_seconds,
            clock=clock or (lambda: 1000.0),
        )

    def test_translate_detects_language_before_translating(self) -> None:
        service = self.build_service()
        translator = _FakeTranslator(
            {
                "Mais materiais de ingles para o publico adolescente.": "More English materials for teenage audiences.",
            }
        )
        service._detect_language = lambda text: "pt"  # type: ignore[method-assign]
        service._get_translator = lambda source_language: translator  # type: ignore[method-assign]

        result = service.translate(
            ["Mais materiais de ingles para o publico adolescente."]
        )

        self.assertEqual(translator.batch_calls, [["Mais materiais de ingles para o publico adolescente."]])
        self.assertEqual(result.texts, ["More English materials for teenage audiences."])
        self.assertEqual(result.translated_flags, [True])
        self.assertEqual(result.detected_languages, ["pt"])
        self.assertEqual(result.translated_count, 1)

    def test_translate_keeps_english_text_without_calling_translator(self) -> None:
        service = self.build_service()
        service._detect_language = lambda text: "en"  # type: ignore[method-assign]
        service._get_translator = lambda source_language: self.fail("Translator should not be used for English text")  # type: ignore[method-assign]

        result = service.translate(["Already English text."])

        self.assertEqual(result.texts, ["Already English text."])
        self.assertEqual(result.translated_flags, [False])
        self.assertEqual(result.detected_languages, ["en"])
        self.assertEqual(result.translated_count, 0)

    def test_translate_warns_when_non_english_translation_is_unavailable(self) -> None:
        service = self.build_service()
        service._detect_language = lambda text: "es"  # type: ignore[method-assign]
        service._get_translator = lambda source_language: (_ for _ in ()).throw(ImportError("unavailable"))  # type: ignore[method-assign]

        result = service.translate(["Mas material de ingles para primaria."])

        self.assertEqual(result.texts, ["Mas material de ingles para primaria."])
        self.assertEqual(result.translated_flags, [False])
        self.assertEqual(result.detected_languages, ["es"])
        self.assertEqual(result.translated_count, 0)
        self.assertIn("may cluster by language instead of topic", " ".join(result.warnings))

    def test_translate_detects_language_without_translating_when_disabled(self) -> None:
        service = EnglishTranslationService(
            config=EnglishTranslationConfig(
                enabled=False,
                source_language="auto",
                target_language="en",
                batch_size=8,
            ),
            clock=lambda: 1000.0,
        )
        service._detect_language = lambda text: "es"  # type: ignore[method-assign]
        service._get_translator = lambda source_language: self.fail("Translator should not be used when disabled")  # type: ignore[method-assign]

        result = service.translate(["Mas material de ingles para primaria."])

        self.assertEqual(result.texts, ["Mas material de ingles para primaria."])
        self.assertEqual(result.translated_flags, [False])
        self.assertEqual(result.detected_languages, ["es"])
        self.assertEqual(result.translated_count, 0)

    def test_cleanup_expired_purges_translation_cache_entries(self) -> None:
        current_time = 1000.0
        service = self.build_service(cache_ttl_seconds=900, clock=lambda: current_time)
        translator = _FakeTranslator(
            {
                "Mais materiais de ingles para o publico adolescente.": "More English materials for teenage audiences.",
            }
        )
        service._detect_language = lambda text: "pt"  # type: ignore[method-assign]
        service._get_translator = lambda source_language: translator  # type: ignore[method-assign]

        service.translate(["Mais materiais de ingles para o publico adolescente."])
        self.assertEqual(len(service._translation_cache), 1)

        current_time += 901

        self.assertEqual(service.cleanup_expired(), 1)
        self.assertEqual(service.cleanup_expired(), 0)
        self.assertEqual(service._translation_cache, {})
        self.assertEqual(service._translation_cache_saved_at, {})


if __name__ == "__main__":
    unittest.main()
