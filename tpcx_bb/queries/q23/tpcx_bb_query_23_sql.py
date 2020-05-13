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

cli_args = tpcxbb_argparser()

# ---------------- Q23 --------------
q23_year = 2001
q23_month = 1
q23_coefficient = 1.3


@benchmark(dask_profile=cli_args["dask_profile"])
def read_tables(data_dir):
    bc.create_table("inventory", data_dir + "inventory/*.parquet")
    bc.create_table("date_dim", data_dir + "date_dim/*.parquet")
    bc.create_table("warehouse", data_dir + "warehouse/*.parquet")


@benchmark(dask_profile=cli_args["dask_profile"])
def main(data_dir):
    read_tables(data_dir)

    query_1 = f"""
        SELECT inv_warehouse_sk,
            inv_item_sk,
            inv_quantity_on_hand,
            d_moy
        FROM inventory inv
        INNER JOIN date_dim d ON inv.inv_date_sk = d.d_date_sk
        AND d.d_year = {q23_year} 
        AND d_moy between {q23_month} AND {q23_month + 1}
    """
    inv_dates_result = bc.sql(query_1)

    bc.create_table("inv_dates", inv_dates_result)
    query_2 = """
        SELECT inv_warehouse_sk,
            inv_item_sk,
            d_moy,
            AVG(CAST(inv_quantity_on_hand AS DOUBLE)) AS q_mean
        FROM inv_dates
        GROUP BY inv_warehouse_sk, inv_item_sk, d_moy
    """
    mean_result = bc.sql(query_2)

    bc.create_table("mean_df", mean_result)
    query_3 = """
        SELECT id.inv_warehouse_sk,
            id.inv_item_sk,
            id.d_moy,
            md.q_mean,
            SQRT( SUM( (id.inv_quantity_on_hand - md.q_mean) * (id.inv_quantity_on_hand - md.q_mean) )
                / (COUNT(id.inv_quantity_on_hand) - 1.0)) AS q_std
        FROM mean_df md
        INNER JOIN inv_dates id ON id.inv_warehouse_sk = md.inv_warehouse_sk
        AND id.inv_item_sk = md.inv_item_sk
        AND id.d_moy = md.d_moy
        AND md.q_mean > 0.0
        GROUP BY id.inv_warehouse_sk, id.inv_item_sk, id.d_moy, md.q_mean
    """
    std_result = bc.sql(query_3)

    bc.create_table("iteration", std_result)
    query_4 = f"""
        SELECT inv_warehouse_sk,
            inv_item_sk,
            d_moy,
            q_std / q_mean AS qty_cov
        FROM iteration
        WHERE (q_std / q_mean) >= {q23_coefficient}
    """
    std_result = bc.sql(query_4)

    bc.create_table("temp_table", std_result)
    last_query = f"""
        SELECT inv1.inv_warehouse_sk,
            inv1.inv_item_sk,
            inv1.d_moy,
            inv1.qty_cov AS cov,
            inv2.d_moy AS inv2_d_moy,
            inv2.qty_cov AS inv2_cov
        FROM temp_table inv1
        INNER JOIN temp_table inv2 ON inv1.inv_warehouse_sk = inv2.inv_warehouse_sk
        AND inv1.inv_item_sk = inv2.inv_item_sk
        AND inv1.d_moy = {q23_month}
        AND inv2.d_moy = {q23_month + 1}
        ORDER BY inv1.inv_warehouse_sk,
            inv1.inv_item_sk
    """

    result = bc.sql(last_query)

    # Casting as rapids dtypes (for validation)
    result["d_moy"] = result["d_moy"].astype("int64")
    result["inv2_d_moy"] = result["inv2_d_moy"].astype("int64")

    return result


if __name__ == "__main__":
    client = attach_to_cluster(cli_args)

    bc = BlazingContext(
        allocator="existing",
        dask_client=client,
        network_interface=os.environ.get("INTERFACE", "eth0"),
    )

    result_df = main(cli_args["data_dir"])
    write_result(
        result_df, output_directory=cli_args["output_dir"],
    )
