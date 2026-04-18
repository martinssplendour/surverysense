from __future__ import annotations

import pandas as pd

from app.core.exceptions import ManifestBuildError


class WideTransformationService:
    def build(
        self,
        raw_df: pd.DataFrame,
        manifest,
        *,
        original_columns: pd.Index,
        index_map: dict[int, int],
        make_output_column_name,
    ) -> pd.DataFrame:
        keep_indices = manifest.metadata_indices + [
            idx for idx in manifest.verbatim_indices if idx not in set(manifest.metadata_indices)
        ]
        if not keep_indices:
            raise ManifestBuildError("Wide manifest did not provide any columns to keep.")

        selected_columns = {
            make_output_column_name(original_columns[idx], idx): raw_df.iloc[:, index_map[idx]]
            for idx in keep_indices
        }
        return pd.DataFrame(selected_columns)
