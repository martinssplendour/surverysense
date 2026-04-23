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
    def build_service(self) -> EnglishTranslationService:
        return EnglishTranslationService(
            config=EnglishTranslationConfig(
                enabled=True,
                source_language="auto",
                target_language="en",
                batch_size=8,
            )
        )

    def test_translate_detects_language_before_translating(self) -> None:
        service = self.build_service()
        translator = _FakeTranslator(
            {
                "Mais materiais de inglês para o público adolescente.": "More English materials for teenage audiences.",
            }
        )
        service._detect_language = lambda text: "pt"  # type: ignore[method-assign]
        service._get_translator = lambda source_language: translator  # type: ignore[method-assign]

        result = service.translate(
            ["Mais materiais de inglês para o público adolescente."]
        )

        self.assertEqual(translator.batch_calls, [["Mais materiais de inglês para o público adolescente."]])
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
