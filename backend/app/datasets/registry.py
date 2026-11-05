from fastapi import HTTPException, status

from app.datasets.academic import academic_datasets
from app.datasets.ingest_rules import with_ingestion_rules
from app.datasets.spec import DatasetSpec
from app.datasets.staff import staff_dataset
from app.datasets.teacher import teacher_datasets

DATASETS: dict[str, DatasetSpec] = {
    item.code: item
    for item in (
        staff_dataset(),
        *teacher_datasets(),
        *academic_datasets(),
    )
}
DATASETS = {code: with_ingestion_rules(spec) for code, spec in DATASETS.items()}


def get_dataset(code: str) -> DatasetSpec:
    spec = DATASETS.get(code)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    return spec
