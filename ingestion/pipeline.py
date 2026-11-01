"""Load Companies House search results into DuckDB as Parquet.

Usage: python -m ingestion.pipeline
"""

import os

import dlt
from dlt.common.pipeline import LoadInfo

from ingestion.companies_house import companies_house

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")
RAW_DATASET = "raw_companies_house"


def run(duckdb_path: str = DUCKDB_PATH, **source_kwargs) -> LoadInfo:
    os.makedirs(os.path.dirname(duckdb_path) or ".", exist_ok=True)
    pipeline = dlt.pipeline(
        pipeline_name="companies_house",
        destination=dlt.destinations.duckdb(duckdb_path),
        dataset_name=RAW_DATASET,
    )
    load_info = pipeline.run(companies_house(**source_kwargs), loader_file_format="parquet")
    load_info.raise_on_failed_jobs()
    return load_info


if __name__ == "__main__":
    print(run())
