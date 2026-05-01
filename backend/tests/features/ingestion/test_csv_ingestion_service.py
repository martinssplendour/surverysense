import unittest

from app.core.exceptions import CsvDecodeError
from app.features.ingestion.csv_ingestion_service import CsvIngestionService
from app.features.ingestion.encoding_service import EncodingDetectionService


class CsvIngestionServiceTests(unittest.TestCase):
    def test_ingest_uses_first_rows_for_samples(self) -> None:
        payload = (
            b"id,text\n"
            b"1,first\n"
            b"2,second\n"
            b"3,third\n"
            b"4,fourth\n"
        )
        service = CsvIngestionService(
            encoding_service=EncodingDetectionService(),
            sample_size=3,
            architect_sample_size=2,
        )

        ingested = service.ingest(payload)

        self.assertEqual(ingested.sample_df["id"].tolist(), ["1", "2", "3"])
        self.assertEqual(ingested.architect_df["id"].tolist(), ["1", "2"])

    def test_ingest_detects_tab_delimited_utf16_csv_exports(self) -> None:
        payload = (
            "Exit Reasons\tComment\tCount\n"
            "I can't afford it right now\tYour service is exceptional, but I cannot afford it.\t1\n"
            "Technical issue\tThe website says it is insecure, every time I click the link.\t2\n"
        ).encode("utf-16")
        service = CsvIngestionService(
            encoding_service=EncodingDetectionService(),
            sample_size=3,
            architect_sample_size=2,
        )

        ingested = service.ingest(payload)

        self.assertEqual(ingested.encoding_result.encoding, "utf_16")
        self.assertEqual(ingested.dataframe.shape, (2, 3))
        self.assertEqual(ingested.dataframe.columns.tolist(), ["Exit Reasons", "Comment", "Count"])
        self.assertEqual(ingested.dataframe.loc[0, "Count"], "1")

    def test_ingest_asks_user_to_reexport_when_csv_cannot_be_parsed(self) -> None:
        payload = b'id,comment\n1,"unfinished quote\n2,still broken\n'
        service = CsvIngestionService(
            encoding_service=EncodingDetectionService(),
            sample_size=3,
            architect_sample_size=2,
        )

        with self.assertRaisesRegex(CsvDecodeError, "please reexport to csv"):
            service.ingest(payload)


if __name__ == "__main__":
    unittest.main()
