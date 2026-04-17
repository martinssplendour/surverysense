import unittest

from app.services.language_normalization_service import (
    EnglishTranslationConfig,
    EnglishTranslationService,
)


class _FakeTranslator:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping
        self.batch_calls: list[list[str]] = []

    def translate_batch(self, texts: list[str]) -> list[str]:
        self.batch_calls.append(list(texts))
        return [self.mapping.get(text, text) for text in texts]


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

    def test_translate_does_not_skip_latin_script_non_english_text(self) -> None:
        service = self.build_service()
        translator = _FakeTranslator(
            {
                "Mais materiais de inglês para o público adolescente.": "More English materials for teenage audiences.",
            }
        )
        service._get_translator = lambda: translator  # type: ignore[method-assign]

        result = service.translate(
            ["Mais materiais de inglês para o público adolescente."]
        )

        self.assertEqual(translator.batch_calls, [["Mais materiais de inglês para o público adolescente."]])
        self.assertEqual(result.texts, ["More English materials for teenage audiences."])
        self.assertEqual(result.translated_flags, [True])
        self.assertEqual(result.translated_count, 1)

