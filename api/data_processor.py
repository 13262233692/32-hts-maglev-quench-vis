import dask.dataframe as dd
import dask.array as da
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import logging
from functools import lru_cache
import gc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_PARTITION_BYTES = 64 * 1024 * 1024
MAX_RESULT_ROWS = 500_000
RESISTIVITY_THRESHOLD = 1e-10


class HTSDataProcessor:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).parent / "sample_data"
        self._ddf: Optional[dd.DataFrame] = None
        self._positions_df: Optional[pd.DataFrame] = None
        self._sorted_ddf: Optional[dd.DataFrame] = None
        self._sensor_ids: Optional[List[str]] = None
        self._time_range: Optional[Tuple[float, float]] = None
        self._load_data()

    def _load_data(self):
        parquet_path = self.data_dir / "sensor_data.parquet"
        csv_path = self.data_dir / "sensor_data.csv"
        positions_path = self.data_dir / "sensor_positions.csv"

        if parquet_path.exists():
            logger.info(f"Loading parquet data from {parquet_path}")
            self._ddf = dd.read_parquet(
                parquet_path,
                blocksize=MAX_PARTITION_BYTES
            )
        elif csv_path.exists():
            logger.info(f"Loading CSV data from {csv_path} with Dask (lazy)")
            self._ddf = dd.read_csv(
                csv_path,
                blocksize="64MB",
                dtype={
                    "timestamp": "float64",
                    "sensor_id": "category",
                    "current_density": "float32",
                    "temperature": "float32",
                    "magnetic_field": "float32",
                    "resistivity": "float32"
                }
            )
        else:
            logger.warning("No data found, will use synthetic data (lazy generation)")
            self._ddf = self._generate_synthetic_ddf()

        self._ddf = self._ddf.repartition(partition_size=MAX_PARTITION_BYTES)

        if positions_path.exists():
            self._positions_df = pd.read_csv(positions_path)
        else:
            self._positions_df = self._generate_synthetic_positions()

        self._sorted_ddf = self._ddf.set_index("timestamp", sorted=True)

        logger.info(
            f"Data graph built: {self._ddf.npartitions} partitions, "
            f"columns={list(self._ddf.columns)}"
        )

    def _generate_synthetic_ddf(self) -> dd.DataFrame:
        from sample_data.generate_data import generate_time_series
        from datetime import datetime

        df = generate_time_series(
            start_time=datetime.now(),
            duration_seconds=600,
            sample_rate=50,
            num_sensors=24,
            quench_time=400
        )
        ddf = dd.from_pandas(df, npartitions=8, sort=False)
        return ddf

    def _generate_synthetic_positions(self) -> pd.DataFrame:
        from sample_data.generate_data import generate_sensor_positions
        return generate_sensor_positions(24)

    @lru_cache(maxsize=1)
    def get_num_sensors(self) -> int:
        if self._sensor_ids is None:
            self._sensor_ids = self._ddf["sensor_id"].drop_duplicates().compute().tolist()
        return len(self._sensor_ids)

    def get_sensor_list(self) -> List[Dict]:
        if self._positions_df is None:
            return []
        return self._positions_df.to_dict("records")

    @lru_cache(maxsize=1)
    def get_time_range(self) -> Tuple[float, float]:
        if self._time_range is None:
            min_ts, max_ts = da.compute(
                self._ddf["timestamp"].min(),
                self._ddf["timestamp"].max()
            )
            self._time_range = (float(min_ts), float(max_ts))
        return self._time_range

    def _adaptive_downsample(self, start_time: float, end_time: float,
                            sensor_count: int, target_points: int = 50000) -> int:
        time_span = max(1e-6, end_time - start_time)
        sample_rate_est = 50.0
        total_est = int(time_span * sample_rate_est * sensor_count)
        if total_est <= target_points:
            return 1
        return max(1, total_est // target_points)

    def query_time_series(
        self,
        start_time: float,
        end_time: float,
        sensor_ids: Optional[List[str]] = None,
        downsample: int = 1
    ) -> pd.DataFrame:
        query = self._sorted_ddf.loc[start_time:end_time]

        if sensor_ids:
            query = query[query["sensor_id"].isin(sensor_ids)]

        effective_sensors = len(sensor_ids) if sensor_ids else self.get_num_sensors()
        auto_downsample = self._adaptive_downsample(start_time, end_time, effective_sensors)
        final_downsample = max(downsample, auto_downsample)

        if final_downsample > 1:
            stride = max(1, final_downsample)
            query = query.map_partitions(
                lambda df, s=stride: df.iloc[::s],
                meta=query._meta
            )

        query = query.map_partitions(
            lambda df: df.reset_index().sort_values(["sensor_id", "timestamp"]),
            meta=query._meta.reset_index()
        )

        expected_rows = (end_time - start_time) * 50 * effective_sensors / max(1, final_downsample)
        if expected_rows > MAX_RESULT_ROWS:
            logger.warning(
                f"Result too large (~{expected_rows:.0f} rows), "
                f"further downsampling to stay under {MAX_RESULT_ROWS}"
            )
            extra = int(expected_rows / MAX_RESULT_ROWS) + 1
            query = query.map_partitions(
                lambda df, e=extra: df.iloc[::e],
                meta=query._meta
            )

        result = query.compute()
        return result

    def get_summary(self, timestamp: float, window: float = 0.1) -> Dict[str, Any]:
        start = timestamp - window / 2
        end = timestamp + window / 2

        query = self._sorted_ddf.loc[start:end]

        agg_expr = {
            "avg_current_density": query["current_density"].mean(),
            "max_current_density": query["current_density"].max(),
            "avg_temperature": query["temperature"].mean(),
            "max_temperature": query["temperature"].max(),
            "avg_magnetic_field": query["magnetic_field"].mean(),
            "avg_resistivity": query["resistivity"].mean(),
            "row_count": query.index.count()
        }

        quench_subset = query[query["resistivity"] > RESISTIVITY_THRESHOLD]
        agg_expr["quench_sensor_ids"] = quench_subset["sensor_id"].drop_duplicates()

        results = da.compute(*agg_expr.values())
        computed = dict(zip(agg_expr.keys(), results))

        if computed["row_count"] == 0:
            time_range = self.get_time_range()
            nearest_ts = self._find_nearest_timestamp(timestamp, time_range)
            if nearest_ts is not None:
                return self.get_summary(nearest_ts, window)
            return {}

        quench_sensors = []
        if hasattr(computed["quench_sensor_ids"], "tolist"):
            quench_sensors = computed["quench_sensor_ids"].tolist()
        elif isinstance(computed["quench_sensor_ids"], list):
            quench_sensors = list(computed["quench_sensor_ids"])
        elif isinstance(computed["quench_sensor_ids"], pd.Series):
            quench_sensors = computed["quench_sensor_ids"].tolist()
        else:
            quench_sensors = list(pd.unique(computed["quench_sensor_ids"]))

        stats = {
            "timestamp": timestamp,
            "avg_current_density": float(computed["avg_current_density"]),
            "max_current_density": float(computed["max_current_density"]),
            "avg_temperature": float(computed["avg_temperature"]),
            "max_temperature": float(computed["max_temperature"]),
            "avg_magnetic_field": float(computed["avg_magnetic_field"]),
            "avg_resistivity": float(computed["avg_resistivity"]),
            "quench_detected": len(quench_sensors) > 0,
            "quench_sensors": quench_sensors
        }

        del computed
        gc.collect()
        return stats

    def _find_nearest_timestamp(self, target: float,
                                time_range: Tuple[float, float]) -> Optional[float]:
        start, end = time_range
        search_start = max(start, target - 5)
        search_end = min(end, target + 5)

        search_region = self._sorted_ddf.loc[search_start:search_end]
        if search_region.npartitions == 0:
            return None

        ts_series = search_region.index.to_series()
        if len(ts_series) == 0:
            return None

        timestamps = ts_series.unique().compute()
        if len(timestamps) == 0:
            return None

        idx = (np.abs(timestamps.values - target)).argmin()
        return float(timestamps.values[idx])

    def rolling_cross_correlation(
        self,
        voltage_sensor_id: str,
        temperature_sensor_id: str,
        start_time: float,
        end_time: float,
        window_size: int = 100,
        max_lag: int = 20
    ) -> dd.DataFrame:
        """
        Purely lazy rolling-window cross-correlation between voltage probe
        signal and adjacent temperature readings. No full memory expansion.

        Uses Dask's map_overlap with partition-level numpy correlation to
        keep memory bounded by partition size regardless of dataset length.
        """
        df = self._sorted_ddf.loc[start_time:end_time]
        df_pair = df[df["sensor_id"].isin([voltage_sensor_id, temperature_sensor_id])]

        def _pivot_and_corr(partition: pd.DataFrame) -> pd.DataFrame:
            if len(partition) == 0:
                return pd.DataFrame({
                    "timestamp": pd.Series(dtype="float64"),
                    "correlation": pd.Series(dtype="float32"),
                    "lag": pd.Series(dtype="int32")
                })

            part = partition.reset_index()

            pivot = part.pivot_table(
                index="timestamp",
                columns="sensor_id",
                values=["current_density", "temperature"]
            )

            if pivot.empty or len(pivot.columns) < 2:
                return pd.DataFrame({
                    "timestamp": pd.Series(dtype="float64"),
                    "correlation": pd.Series(dtype="float32"),
                    "lag": pd.Series(dtype="int32")
                })

            voltage_col = ("current_density", voltage_sensor_id)
            temp_col = ("temperature", temperature_sensor_id)

            if voltage_col not in pivot.columns or temp_col not in pivot.columns:
                return pd.DataFrame({
                    "timestamp": pd.Series(dtype="float64"),
                    "correlation": pd.Series(dtype="float32"),
                    "lag": pd.Series(dtype="int32")
                })

            v = pivot[voltage_col].astype("float32").values
            t = pivot[temp_col].astype("float32").values
            ts_vals = pivot.index.values.astype("float64")

            results = []
            n = len(v)
            effective_window = min(window_size, n)
            if effective_window < max_lag * 2 + 2:
                return pd.DataFrame({
                    "timestamp": pd.Series(dtype="float64"),
                    "correlation": pd.Series(dtype="float32"),
                    "lag": pd.Series(dtype="int32")
                })

            for i in range(effective_window, n, max(1, effective_window // 4)):
                seg_start = max(0, i - effective_window)
                v_seg = v[seg_start:i]
                t_seg = t[seg_start:i]

                if np.std(v_seg) < 1e-12 or np.std(t_seg) < 1e-12:
                    continue

                v_norm = (v_seg - np.mean(v_seg)) / (np.std(v_seg) + 1e-12)
                t_norm = (t_seg - np.mean(t_seg)) / (np.std(t_seg) + 1e-12)

                lags = np.arange(-max_lag, max_lag + 1)
                corrs = np.correlate(v_norm, t_norm, mode="full") / len(v_seg)
                mid = len(corrs) // 2
                lag_corrs = corrs[mid - max_lag:mid + max_lag + 1]

                best_idx = int(np.argmax(np.abs(lag_corrs)))
                results.append({
                    "timestamp": float(ts_vals[i]),
                    "correlation": float(lag_corrs[best_idx]),
                    "lag": int(lags[best_idx])
                })

            del pivot, v, t, ts_vals
            gc.collect()

            if not results:
                return pd.DataFrame({
                    "timestamp": pd.Series(dtype="float64"),
                    "correlation": pd.Series(dtype="float32"),
                    "lag": pd.Series(dtype="int32")
                })
            return pd.DataFrame(results)

        corr_ddf = df_pair.map_overlap(
            _pivot_and_corr,
            before=window_size,
            after=0,
            meta=pd.DataFrame({
                "timestamp": pd.Series(dtype="float64"),
                "correlation": pd.Series(dtype="float32"),
                "lag": pd.Series(dtype="int32")
            })
        )

        return corr_ddf

    def get_particles(
        self,
        timestamp: float,
        num_particles: int = 3000,
        heat_zone_temp: Optional[float] = None
    ) -> Dict[str, Any]:
        if heat_zone_temp is None:
            summary = self.get_summary(timestamp)
            heat_zone_temp = summary.get("avg_temperature", 77.0)

        boiling_intensity = max(0.0, min(1.0, (heat_zone_temp - 77.0) / 20.0))
        num_active = int(num_particles * (0.3 + boiling_intensity * 0.7))

        rng = np.random.RandomState(int(timestamp * 1000) % 1_000_000)

        particle_ids = np.arange(num_active, dtype="int32")

        phases = timestamp * (1.0 + particle_ids * 0.001) + particle_ids * 100.0
        base_angles = rng.uniform(0.0, 2.0 * np.pi, num_active).astype("float32")
        base_radii = rng.uniform(0.2, 0.9, num_active).astype("float32")

        rise_speed = 0.5 + boiling_intensity * 2.0
        vertical_pos = ((phases * rise_speed + particle_ids * 0.01) % 1.5 - 0.2).astype("float32")

        wobble = (np.sin(phases * 3.0 + particle_ids) * 0.05).astype("float32")
        x = (base_radii * np.cos(base_angles + wobble)).astype("float32")
        z = (base_radii * np.sin(base_angles + wobble)).astype("float32")
        y = vertical_pos

        sizes = (0.01 + rng.uniform(0.0, 0.02, num_active) * (1.0 + boiling_intensity)).astype("float32")
        opacities = np.clip(1.0 - vertical_pos / 1.5, 0.0, 1.0).astype("float32")
        temps = (77.0 + vertical_pos * 10.0 + rng.uniform(0.0, 5.0, num_active)).astype("float32")

        positions = np.stack([x, y, z], axis=1)
        velocities = np.stack([
            wobble * 0.1,
            np.full(num_active, rise_speed * 0.1, dtype="float32"),
            -wobble * 0.1
        ], axis=1)

        particles = []
        for i in range(num_active):
            particles.append({
                "id": int(particle_ids[i]),
                "position": [float(positions[i, 0]), float(positions[i, 1]), float(positions[i, 2])],
                "velocity": [float(velocities[i, 0]), float(velocities[i, 1]), float(velocities[i, 2])],
                "size": float(sizes[i]),
                "opacity": float(opacities[i]),
                "temperature": float(temps[i])
            })

        del particle_ids, phases, base_angles, base_radii, vertical_pos
        del wobble, x, y, z, sizes, opacities, temps, positions, velocities
        gc.collect()

        return {
            "particles": particles,
            "timestamp": timestamp,
            "heat_zone_temperature": float(heat_zone_temp)
        }

    def detect_quench_events(
        self,
        start_time: float,
        end_time: float,
        threshold: float = RESISTIVITY_THRESHOLD
    ) -> List[Dict[str, Any]]:
        query = self._sorted_ddf.loc[start_time:end_time]
        quench_only = query[query["resistivity"] > threshold]

        if quench_only.npartitions == 0:
            return []

        quench_with_ts = quench_only.reset_index()
        sensor_grouped = quench_with_ts.groupby("sensor_id").agg({
            "timestamp": "min",
            "resistivity": "max",
            "temperature": "max"
        })

        result_df = sensor_grouped.compute()

        if len(result_df) == 0:
            return []

        events = [
            {
                "sensor_id": str(sensor_id),
                "start_time": float(row["timestamp"]),
                "peak_resistivity": float(row["resistivity"]),
                "peak_temperature": float(row["temperature"])
            }
            for sensor_id, row in result_df.iterrows()
        ]

        del result_df, query, quench_only, sensor_grouped
        gc.collect()

        return sorted(events, key=lambda x: x["start_time"])

    def get_cross_correlation_summary(
        self,
        start_time: float,
        end_time: float,
        voltage_sensor: str,
        temperature_sensor: str
    ) -> Dict[str, Any]:
        corr_ddf = self.rolling_cross_correlation(
            voltage_sensor, temperature_sensor,
            start_time, end_time
        )

        if corr_ddf.npartitions == 0:
            return {"status": "no_data"}

        stats_expr = {
            "mean_corr": corr_ddf["correlation"].mean(),
            "max_abs_corr": corr_ddf["correlation"].abs().max(),
            "mean_lag": corr_ddf["lag"].mean(),
            "count": corr_ddf["correlation"].count()
        }

        results = da.compute(*stats_expr.values())
        computed = dict(zip(stats_expr.keys(), results))

        return {
            "voltage_sensor": voltage_sensor,
            "temperature_sensor": temperature_sensor,
            "mean_correlation": float(computed["mean_corr"]) if computed["count"] > 0 else 0.0,
            "max_abs_correlation": float(computed["max_abs_corr"]) if computed["count"] > 0 else 0.0,
            "mean_lag": float(computed["mean_lag"]) if computed["count"] > 0 else 0,
            "sample_count": int(computed["count"])
        }
