import unittest

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


if __name__ == "__main__":
    unittest.main()
