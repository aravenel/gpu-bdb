#
# Copyright (c) 2019-2020, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import sys


from blazingsql import BlazingContext
from xbb_tools.cluster_startup import attach_to_cluster
from dask_cuda import LocalCUDACluster
from dask.distributed import Client
import os

from xbb_tools.utils import (
    benchmark,
    tpcxbb_argparser,
    write_result,
)
from tpcx_bb_query_26 import get_clusters

cli_args = tpcxbb_argparser()


@benchmark()
def read_tables(data_dir):
    bc.create_table("store_sales", data_dir + "store_sales/*.parquet")
    bc.create_table("item", data_dir + "item/*.parquet")


@benchmark(dask_profile=cli_args.get("dask_profile"))
def main(client, data_dir):
    read_tables(data_dir)

    query = """
        SELECT
            ss.ss_customer_sk AS cid,
            CAST( count(CASE WHEN i.i_class_id=1  THEN 1 ELSE NULL END) AS DOUBLE ) AS id1,
            CAST( count(CASE WHEN i.i_class_id=2  THEN 1 ELSE NULL END) AS DOUBLE ) AS id2,
            CAST( count(CASE WHEN i.i_class_id=3  THEN 1 ELSE NULL END) AS DOUBLE ) AS id3,
            CAST( count(CASE WHEN i.i_class_id=4  THEN 1 ELSE NULL END) AS DOUBLE ) AS id4,
            CAST( count(CASE WHEN i.i_class_id=5  THEN 1 ELSE NULL END) AS DOUBLE ) AS id5,
            CAST( count(CASE WHEN i.i_class_id=6  THEN 1 ELSE NULL END) AS DOUBLE ) AS id6,
            CAST( count(CASE WHEN i.i_class_id=7  THEN 1 ELSE NULL END) AS DOUBLE ) AS id7,
            CAST( count(CASE WHEN i.i_class_id=8  THEN 1 ELSE NULL END) AS DOUBLE ) AS id8,
            CAST( count(CASE WHEN i.i_class_id=9  THEN 1 ELSE NULL END) AS DOUBLE ) AS id9,
            CAST( count(CASE WHEN i.i_class_id=10 THEN 1 ELSE NULL END) AS DOUBLE ) AS id10,
            CAST( count(CASE WHEN i.i_class_id=11 THEN 1 ELSE NULL END) AS DOUBLE ) AS id11,
            CAST( count(CASE WHEN i.i_class_id=12 THEN 1 ELSE NULL END) AS DOUBLE ) AS id12,
            CAST( count(CASE WHEN i.i_class_id=13 THEN 1 ELSE NULL END) AS DOUBLE ) AS id13,
            CAST( count(CASE WHEN i.i_class_id=14 THEN 1 ELSE NULL END) AS DOUBLE ) AS id14,
            CAST( count(CASE WHEN i.i_class_id=15 THEN 1 ELSE NULL END) AS DOUBLE ) AS id15
        FROM store_sales ss
        INNER JOIN item i 
        ON 
        (
            ss.ss_item_sk = i.i_item_sk
            AND i.i_category IN ('Books')
            AND ss.ss_customer_sk IS NOT NULL
        )
        GROUP BY ss.ss_customer_sk
        HAVING count(ss.ss_item_sk) > 5
        ORDER BY cid
    """

    result = bc.sql(query)
    result = result.repartition(npartitions=1)
    ml_result_dict = get_clusters(client=client, kmeans_input_df=result)
    return ml_result_dict


if __name__ == "__main__":
    client = attach_to_cluster(cli_args)

    bc = BlazingContext(
        allocator="existing",
        dask_client=client,
        network_interface=os.environ.get("INTERFACE", "eth0"),
    )

    ml_result_dict = main(client=client, data_dir=cli_args["data_dir"])
    write_result(
        ml_result_dict, output_directory=cli_args["output_dir"],
    )

    if cli_args["verify_results"]:
        result_verified = verify_results(cli_args["verify_dir"])
    cli_args["result_verified"] = result_verified
