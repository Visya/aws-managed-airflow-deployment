from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.utils.dates import days_ago

from airflow.providers.amazon.aws.operators.athena import AWSAthenaOperator
from airflow.providers.amazon.aws.operators.glue import AwsGlueJobOperator

default_args = {
    "owner": "visya",
    "sla": timedelta(hours=1),
}

region = Variable.get("region")
data_lake_bucket = Variable.get("data_lake_bucket")
infra_bucket = Variable.get("infra_bucket")
glue_db = Variable.get("glue_db")
table = "test_table"


with DAG(
    "dynamodb-table-export",
    default_args=default_args,
    description="Export DynamoDB table to S3 in parquet format",
    schedule_interval=timedelta(days=1),
    start_date=days_ago(1),
) as dag:
    snapshot_ts = datetime.timestamp()
    path = f"{table}/snapshot_ts={snapshot_ts}"
    athena_output_location = f"s3://{infra_bucket}/athena-output/{table}"

    dynamodb_to_s3_export = AwsGlueJobOperator(
        task_id="dynamodb_to_s3_export",
        job_name="dynamodb-to-s3-export",
        num_of_dpus=2,
        region_name=region,
        script_args={"--snapshot_ts": snapshot_ts},
    )

    add_new_partition = AWSAthenaOperator(
        task_id="add_new_partition",
        query=f"""
          ALTER TABLE {table} ADD PARTITION (snapshot_ts = '{snapshot_ts}')
          LOCATION 's3://{data_lake_bucket}/{path}'
        """,
        database=glue_db,
        output_location=athena_output_location,
    )

    update_latest_view = AWSAthenaOperator(
        task_id="update_latest_view",
        query=f"""
          CREATE OR REPLACE VIEW {table}_latest AS
          SELECT * from {table}
          WHERE snapshot_ts = '{snapshot_ts}'
        """,
        database=glue_db,
        output_location=athena_output_location,
    )

dynamodb_to_s3_export >> add_new_partition >> update_latest_view
