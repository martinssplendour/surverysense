import unittest

from app.services.csv_ingestion_service import CsvIngestionService
from app.services.encoding_service import EncodingDetectionService


class CsvIngestionServiceTests(unittest.TestCase):
    def test_ingest_uses_first_rows_for_samples(self) -> None:
        payload = (
            "id,text\n"
            "1,first\n"
            "2,second\n"
            "3,third\n"
            "4,fourth\n"
        ).encode("utf-8")
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
