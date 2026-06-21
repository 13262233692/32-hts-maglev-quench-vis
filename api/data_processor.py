import dask.dataframe as dd
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTSDataProcessor:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).parent / "sample_data"
        self._ddf: Optional[dd.DataFrame] = None
        self._positions_df: Optional[pd.DataFrame] = None
        self._load_data()
    
    def _load_data(self):
        parquet_path = self.data_dir / "sensor_data.parquet"
        csv_path = self.data_dir / "sensor_data.csv"
        positions_path = self.data_dir / "sensor_positions.csv"
        
        if parquet_path.exists():
            logger.info(f"Loading parquet data from {parquet_path}")
            self._ddf = dd.read_parquet(parquet_path)
        elif csv_path.exists():
            logger.info(f"Loading CSV data from {csv_path} with Dask")
            self._ddf = dd.read_csv(csv_path, blocksize="64MB")
            self._ddf = self._ddf.sort_values("timestamp").persist()
        else:
            logger.warning("No data found, will use synthetic data")
            self._ddf = self._generate_synthetic_ddf()
        
        if positions_path.exists():
            self._positions_df = pd.read_csv(positions_path)
        else:
            self._positions_df = self._generate_synthetic_positions()
        
        logger.info(f"Data loaded: {len(self._ddf)} records across {self.get_num_sensors()} sensors")
    
    def _generate_synthetic_ddf(self) -> dd.DataFrame:
        from sample_data.generate_data import generate_time_series
        from datetime import datetime
        
        df = generate_time_series(
            start_time=datetime.now(),
            duration_seconds=600,
            sample_rate=20,
            num_sensors=24,
            quench_time=400
        )
        return dd.from_pandas(df, npartitions=8).persist()
    
    def _generate_synthetic_positions(self) -> pd.DataFrame:
        from sample_data.generate_data import generate_sensor_positions
        return generate_sensor_positions(24)
    
    def get_num_sensors(self) -> int:
        return self._ddf["sensor_id"].nunique().compute()
    
    def get_sensor_list(self) -> List[Dict]:
        if self._positions_df is None:
            return []
        return self._positions_df.to_dict("records")
    
    def get_time_range(self) -> Tuple[float, float]:
        min_ts = self._ddf["timestamp"].min().compute()
        max_ts = self._ddf["timestamp"].max().compute()
        return float(min_ts), float(max_ts)
    
    def query_time_series(
        self,
        start_time: float,
        end_time: float,
        sensor_ids: Optional[List[str]] = None,
        downsample: int = 1
    ) -> pd.DataFrame:
        query = self._ddf[
            (self._ddf["timestamp"] >= start_time) &
            (self._ddf["timestamp"] <= end_time)
        ]
        
        if sensor_ids:
            query = query[query["sensor_id"].isin(sensor_ids)]
        
        if downsample > 1:
            query = query.map_partitions(
                lambda df: df.iloc[::downsample].copy(),
                meta=query._meta
            )
        
        result = query.compute()
        return result.sort_values(["sensor_id", "timestamp"])
    
    def get_summary(self, timestamp: float, window: float = 0.1) -> Dict:
        start = timestamp - window / 2
        end = timestamp + window / 2
        
        query = self._ddf[
            (self._ddf["timestamp"] >= start) &
            (self._ddf["timestamp"] <= end)
        ]
        
        if len(query) == 0:
            nearest = self._ddf.map_partitions(
                lambda df: df.iloc[(df["timestamp"] - timestamp).abs().argsort()[:1]]
            ).compute()
            if len(nearest) > 0:
                return self.get_summary(float(nearest.iloc[0]["timestamp"]), window)
            return {}
        
        stats = {
            "timestamp": timestamp,
            "avg_current_density": float(query["current_density"].mean().compute()),
            "max_current_density": float(query["current_density"].max().compute()),
            "avg_temperature": float(query["temperature"].mean().compute()),
            "max_temperature": float(query["temperature"].max().compute()),
            "avg_magnetic_field": float(query["magnetic_field"].mean().compute()),
            "avg_resistivity": float(query["resistivity"].mean().compute()),
        }
        
        resistivity_threshold = 1e-10
        quench_sensors = query[query["resistivity"] > resistivity_threshold]
        quench_sensor_ids = quench_sensors["sensor_id"].unique().compute().tolist()
        
        stats["quench_detected"] = len(quench_sensor_ids) > 0
        stats["quench_sensors"] = quench_sensor_ids
        
        return stats
    
    def get_particles(
        self,
        timestamp: float,
        num_particles: int = 3000,
        heat_zone_temp: Optional[float] = None
    ) -> List[Dict]:
        if heat_zone_temp is None:
            summary = self.get_summary(timestamp)
            heat_zone_temp = summary.get("avg_temperature", 77.0)
        
        boiling_intensity = max(0, min(1, (heat_zone_temp - 77) / 20))
        num_active = int(num_particles * (0.3 + boiling_intensity * 0.7))
        
        particles = []
        np.random.seed(int(timestamp * 1000) % 1000000)
        
        for i in range(num_active):
            phase = timestamp * (1.0 + i * 0.001) + i * 100
            base_angle = np.random.uniform(0, 2 * np.pi)
            base_radius = np.random.uniform(0.2, 0.9)
            
            rise_speed = 0.5 + boiling_intensity * 2.0
            vertical_pos = (phase * rise_speed + i * 0.01) % 1.5 - 0.2
            
            wobble = np.sin(phase * 3 + i) * 0.05
            x = base_radius * np.cos(base_angle + wobble)
            z = base_radius * np.sin(base_angle + wobble)
            y = vertical_pos
            
            size = 0.01 + np.random.uniform(0, 0.02) * (1 + boiling_intensity)
            opacity = max(0, min(1, 1.0 - vertical_pos / 1.5))
            
            temp = 77 + vertical_pos * 10 + np.random.uniform(0, 5)
            
            particles.append({
                "id": i,
                "position": (float(x), float(y), float(z)),
                "velocity": (
                    float(wobble * 0.1),
                    float(rise_speed * 0.1),
                    float(-wobble * 0.1)
                ),
                "size": float(size),
                "opacity": float(opacity),
                "temperature": float(temp)
            })
        
        return particles
    
    def detect_quench_events(
        self,
        start_time: float,
        end_time: float,
        threshold: float = 1e-10
    ) -> List[Dict]:
        query = self._ddf[
            (self._ddf["timestamp"] >= start_time) &
            (self._ddf["timestamp"] <= end_time) &
            (self._ddf["resistivity"] > threshold)
        ]
        
        result = query.compute()
        if len(result) == 0:
            return []
        
        events = []
        for sensor_id, group in result.groupby("sensor_id"):
            if len(group) > 0:
                events.append({
                    "sensor_id": sensor_id,
                    "start_time": float(group["timestamp"].min()),
                    "peak_resistivity": float(group["resistivity"].max()),
                    "peak_temperature": float(group["temperature"].max())
                })
        
        return sorted(events, key=lambda x: x["start_time"])
