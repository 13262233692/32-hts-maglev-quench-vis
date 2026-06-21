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

    def _quench_propagation_velocity(
        self,
        temperature: float,
        current_density: float,
        magnetic_field: float,
        resistivity: float
    ) -> float:
        """
        非线性热传导方程推导的失超传播速度。
        基于：v ∝ sqrt(J²ρ / (γcΔT)) 的修正形式，
        加入温度相关的指数项和磁场抑制因子。
        """
        T_c = 92.0
        T_op = 77.0
        if temperature >= T_c:
            return 100.0

        delta_T = max(0.1, temperature - T_op)
        overheat_ratio = delta_T / (T_c - T_op)

        j_factor = (current_density / 200.0) ** 1.5

        b_factor = 1.0 / (1.0 + magnetic_field / 12.0)

        v_base = 5.0

        exponent = 3.0 * overheat_ratio

        v_prop = v_base * j_factor * b_factor * np.exp(exponent)

        return float(min(200.0, max(0.001, v_prop)))

    def detect_quench_hotspots(
        self,
        timestamp: float,
        window: float = 0.05
    ) -> List[Dict[str, Any]]:
        """
        实时捕获局部超导带材冲破临界温升的微小前兆，
        识别所有失超热点及其传播方向。
        """
        start = timestamp - window / 2
        end = timestamp + window / 2
        query = self._sorted_ddf.loc[start:end]

        agg_df = query.groupby("sensor_id").agg({
            "temperature": "mean",
            "current_density": "mean",
            "magnetic_field": "mean",
            "resistivity": "mean"
        }).compute()

        hotspots = []
        for sensor_id, row in agg_df.iterrows():
            t = float(row["temperature"])
            j = float(row["current_density"])
            b = float(row["magnetic_field"])
            rho = float(row["resistivity"])

            if t > 77.5 or rho > RESISTIVITY_THRESHOLD:
                v_prop = self._quench_propagation_velocity(t, j, b, rho)

                if self._positions_df is not None:
                    pos_row = self._positions_df[
                        self._positions_df["sensor_id"] == sensor_id
                    ]
                    if len(pos_row) > 0:
                        position = [
                            float(pos_row.iloc[0]["pos_x"]),
                            float(pos_row.iloc[0]["pos_y"]),
                            float(pos_row.iloc[0]["pos_z"])
                        ]
                    else:
                        position = [0.0, 0.0, 0.0]
                else:
                    position = [0.0, 0.0, 0.0]

                hotspots.append({
                    "sensor_id": str(sensor_id),
                    "position": position,
                    "temperature": t,
                    "current_density": j,
                    "magnetic_field": b,
                    "resistivity": rho,
                    "propagation_velocity": v_prop,
                    "severity": min(1.0, max(0.0, (t - 77.0) / 15.0))
                })

        del agg_df, query
        gc.collect()

        return sorted(hotspots, key=lambda x: -x["severity"])

    def predict_quench_propagation(
        self,
        start_time: float,
        end_time: float,
        sensor_id: str,
        predict_seconds: float = 2.0,
        time_step: float = 0.01
    ) -> Dict[str, Any]:
        """
        从预警点分叉，使用非线性热传导方程推算
        "预计全线失超"虚线 + 半透明置信区间阴影带。

        输出：预测时间序列 + 上下置信边界 + 加热器触发截点。
        """
        history = self.query_time_series(
            start_time=max(0, end_time - 1.0),
            end_time=end_time,
            sensor_ids=[sensor_id],
            downsample=1
        )

        if len(history) < 3:
            return {"status": "insufficient_data"}

        sensor_hist = history[history["sensor_id"] == sensor_id]
        if len(sensor_hist) < 2:
            return {"status": "insufficient_data"}

        last_temp = float(sensor_hist["temperature"].iloc[-1])
        last_rho = float(sensor_hist["resistivity"].iloc[-1])
        last_j = float(sensor_hist["current_density"].iloc[-1])
        last_b = float(sensor_hist["magnetic_field"].iloc[-1])
        start_ts = float(sensor_hist["timestamp"].iloc[-1])

        if last_temp < 77.5 and last_rho < RESISTIVITY_THRESHOLD:
            return {
                "status": "superconducting",
                "start_time": start_ts,
                "prediction_seconds": predict_seconds
            }

        n_steps = int(predict_seconds / time_step)
        times = np.zeros(n_steps, dtype="float64")
        temps_pred = np.zeros(n_steps, dtype="float32")
        rho_pred = np.zeros(n_steps, dtype="float32")
        temp_upper = np.zeros(n_steps, dtype="float32")
        temp_lower = np.zeros(n_steps, dtype="float32")
        rho_upper = np.zeros(n_steps, dtype="float32")
        rho_lower = np.zeros(n_steps, dtype="float32")

        T_burn = 150.0
        R_n = 5e-5
        T_heater = 85.0

        t = last_temp
        rho = last_rho
        times[0] = start_ts
        temps_pred[0] = t
        rho_pred[0] = rho
        temp_upper[0] = t + 0.3
        temp_lower[0] = max(77.0, t - 0.3)
        rho_upper[0] = rho * 1.8
        rho_lower[0] = rho * 0.6

        j_factor = (last_j / 150.0) ** 1.2
        b_suppression = 1.0 / (1.0 + last_b / 15.0)
        growth_rate = 2.5 * j_factor * b_suppression

        heater_trigger = None
        burn_through = None
        heater_delay_ms = 0.0
        burn_delay_ms = 0.0
        final_idx = n_steps

        for i in range(1, n_steps):
            dt = time_step
            elapsed_ms = i * time_step * 1000
            t_norm = i * time_step * growth_rate

            growth_exp = min(50.0, 1.8 * t_norm)
            temp_growth = (t - 77.0) * np.exp(growth_exp)
            t_new = 77.0 + temp_growth
            t = float(min(500.0, t_new))

            rho_norm = min(1.0, max(0.0, (t - 77.0) / 25.0) ** 1.8)
            rho = float(RESISTIVITY_THRESHOLD + rho_norm * (R_n - RESISTIVITY_THRESHOLD))

            unc = 0.15 + min(0.5, t_norm * 0.4)
            t_upper = float(min(600.0, 77.0 + temp_growth * (1.0 + unc)))
            t_lower = float(77.0 + max(0.01, temp_growth * max(0.2, 1.0 - unc)))

            rho_upper_norm = min(1.0, max(0.0, (t_upper - 77.0) / 25.0) ** 1.8)
            rho_lower_norm = min(1.0, max(0.0, (t_lower - 77.0) / 25.0) ** 1.8)
            rho_upper_val = RESISTIVITY_THRESHOLD + rho_upper_norm * (R_n - RESISTIVITY_THRESHOLD)
            rho_lower_val = RESISTIVITY_THRESHOLD + rho_lower_norm * (R_n - RESISTIVITY_THRESHOLD)

            times[i] = start_ts + i * time_step
            temps_pred[i] = t
            rho_pred[i] = rho
            temp_upper[i] = t_upper
            temp_lower[i] = t_lower
            rho_upper[i] = rho_upper_val
            rho_lower[i] = rho_lower_val

            if heater_trigger is None and t > 85.0:
                heater_trigger = {
                    "time": start_ts + i * time_step,
                    "temperature": t,
                    "resistivity": rho,
                    "delay_ms": elapsed_ms,
                    "action": "secondary_heater_trigger",
                    "severity": "critical"
                }
                heater_delay_ms = elapsed_ms

            if burn_through is None and t > T_burn:
                burn_through = {
                    "time": start_ts + i * time_step,
                    "temperature": t,
                    "delay_ms": elapsed_ms
                }
                burn_delay_ms = elapsed_ms
                break

        v_prop = self._quench_propagation_velocity(last_temp, last_j, last_b, last_rho)

        prediction_points = min(i + 1, n_steps)

        result = {
            "status": "quenching",
            "sensor_id": sensor_id,
            "start_time": start_ts,
            "prediction_seconds": predict_seconds,
            "propagation_velocity": v_prop,
            "initial_temperature": last_temp,
            "initial_resistivity": last_rho,
            "time_series": [
                {
                    "timestamp": float(times[j]),
                    "temperature": float(temps_pred[j]),
                    "resistivity": float(rho_pred[j]),
                    "temp_upper": float(temp_upper[j]),
                    "temp_lower": float(temp_lower[j]),
                    "rho_upper": float(rho_upper[j]),
                    "rho_lower": float(rho_lower[j])
                }
                for j in range(prediction_points)
            ],
            "heater_trigger": heater_trigger,
            "burn_through": burn_through,
            "heater_delay_ms": float(heater_delay_ms),
            "burn_delay_ms": float(burn_delay_ms)
        }

        del history, sensor_hist, times, temps_pred, rho_pred
        del temp_upper, temp_lower, rho_upper, rho_lower
        gc.collect()

        return result

    def get_heater_events(
        self,
        start_time: float,
        end_time: float
    ) -> List[Dict[str, Any]]:
        """
        获取所有二次保护加热器触发事件，
        在曲线触碰绝对烧毁阈值前的毫秒级截点上标亮鲜红信标。
        """
        quench_events = self.detect_quench_events(start_time, end_time)
        heater_events = []

        for q_event in quench_events:
            sensor_id = q_event["sensor_id"]
            q_time = q_event["start_time"]

            pred_window_start = max(start_time, q_time)
            pred_window_end = min(end_time, q_time + 1.0)
            if pred_window_end - pred_window_start < 0.3:
                pred_window_end = min(end_time, pred_window_start + 0.3)

            pred = self.predict_quench_propagation(
                start_time=pred_window_start,
                end_time=pred_window_end,
                sensor_id=sensor_id,
                predict_seconds=3.0
            )

            if pred.get("status") == "quenching" and pred.get("heater_trigger"):
                ht = pred["heater_trigger"]
                heater_events.append({
                    "sensor_id": sensor_id,
                    "trigger_time": ht["time"],
                    "trigger_temperature": ht["temperature"],
                    "trigger_resistivity": ht["resistivity"],
                    "delay_ms": ht["delay_ms"],
                    "propagation_velocity": pred["propagation_velocity"],
                    "burn_through_time": pred.get("burn_through", {}).get("time"),
                    "severity": ht["severity"],
                    "action": "secondary_heater_activated"
                })

        del quench_events
        gc.collect()

        return sorted(heater_events, key=lambda x: x["trigger_time"])
