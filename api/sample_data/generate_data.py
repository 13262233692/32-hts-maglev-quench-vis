import numpy as np
import pandas as pd
from pathlib import Path
import dask.dataframe as dd
from datetime import datetime, timedelta


def generate_sensor_positions(num_sensors: int = 24) -> pd.DataFrame:
    positions = []
    for i in range(num_sensors):
        angle = (i / num_sensors) * 2 * np.pi
        radius = 0.8 + np.random.uniform(-0.1, 0.1)
        height = 0.3 + (i % 6) * 0.15
        positions.append({
            "sensor_id": f"HTS-{i:03d}",
            "pos_x": radius * np.cos(angle),
            "pos_y": height,
            "pos_z": radius * np.sin(angle),
            "channel": i,
            "type": "resistivity"
        })
    return pd.DataFrame(positions)


def generate_time_series(
    start_time: datetime,
    duration_seconds: int = 600,
    sample_rate: float = 100,
    num_sensors: int = 24,
    quench_time: float = 400
) -> pd.DataFrame:
    total_samples = int(duration_seconds * sample_rate)
    timestamps = np.linspace(0, duration_seconds, total_samples)
    
    data = []
    
    for sensor_idx in range(num_sensors):
        base_temp = 77.0 + np.random.uniform(-0.5, 0.5)
        base_current = 150 + np.random.uniform(-20, 20)
        base_field = 8.0 + np.random.uniform(-0.5, 0.5)
        
        noise_temp = np.random.normal(0, 0.02, total_samples)
        noise_current = np.random.normal(0, 2, total_samples)
        noise_field = np.random.normal(0, 0.05, total_samples)
        
        temperature = base_temp + noise_temp
        current_density = base_current + noise_current
        magnetic_field = base_field + noise_field
        
        quench_transition = 1.0 / (1.0 + np.exp(-20 * (timestamps - quench_time)))
        sensor_quench_factor = 0.5 + 0.5 * np.sin(sensor_idx * 0.3)
        temperature += quench_transition * sensor_quench_factor * (20 + sensor_idx * 0.5)
        
        t_over_tc = temperature / 92.0
        b_over_bc2 = magnetic_field / 14.0
        normal_resistivity = 1.5e-7 * (1 + 0.02 * (temperature - 77))
        superconductivity_factor = np.maximum(0, 1 - t_over_tc**2) * np.maximum(0, 1 - b_over_bc2)
        quench_factor = 1.0 / (1.0 + np.exp(-15 * (timestamps - quench_time - 2)))
        resistivity = normal_resistivity * (1 - superconductivity_factor * (1 - quench_factor * 0.7))
        
        sensor_id = f"HTS-{sensor_idx:03d}"
        for i, ts in enumerate(timestamps):
            data.append({
                "timestamp": ts,
                "sensor_id": sensor_id,
                "current_density": float(current_density[i]),
                "temperature": float(temperature[i]),
                "magnetic_field": float(magnetic_field[i]),
                "resistivity": float(resistivity[i])
            })
    
    return pd.DataFrame(data)


def main():
    output_dir = Path(__file__).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Generating sensor positions...")
    positions_df = generate_sensor_positions(24)
    positions_df.to_csv(output_dir / "sensor_positions.csv", index=False)
    print(f"Generated {len(positions_df)} sensor positions")
    
    print("Generating time series data (this may take a while)...")
    start_time = datetime.now()
    ts_df = generate_time_series(
        start_time=start_time,
        duration_seconds=600,
        sample_rate=50,
        num_sensors=24,
        quench_time=400
    )
    print(f"Generated {len(ts_df)} data points")
    
    csv_path = output_dir / "sensor_data.csv"
    ts_df.to_csv(csv_path, index=False, chunksize=100000)
    print(f"Saved CSV to {csv_path}")
    
    print("Converting to Parquet with Dask...")
    ddf = dd.read_csv(csv_path, blocksize="64MB")
    ddf = ddf.sort_values("timestamp")
    parquet_path = output_dir / "sensor_data.parquet"
    ddf.to_parquet(parquet_path, write_index=False)
    print(f"Saved Parquet to {parquet_path}")
    
    print("Data generation complete!")


if __name__ == "__main__":
    main()
