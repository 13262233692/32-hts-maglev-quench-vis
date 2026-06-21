from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
from enum import Enum


class SensorType(str, Enum):
    CURRENT_DENSITY = "current_density"
    TEMPERATURE = "temperature"
    MAGNETIC_FIELD = "magnetic_field"
    RESISTIVITY = "resistivity"


class SensorInfo(BaseModel):
    sensor_id: str
    position: Tuple[float, float, float]
    type: SensorType
    channel: int


class SensorDataPoint(BaseModel):
    timestamp: float = Field(description="Unix timestamp in seconds")
    sensor_id: str
    current_density: float = Field(description="Current density in A/cm²")
    temperature: float = Field(description="Temperature in Kelvin")
    magnetic_field: float = Field(description="Magnetic field in Tesla")
    resistivity: float = Field(description="Resistivity in Ω·m")


class TimeSeriesQuery(BaseModel):
    start_time: float
    end_time: float
    sensor_ids: Optional[List[str]] = None
    downsample: Optional[int] = Field(default=1, ge=1, le=1000)


class TimeSeriesResponse(BaseModel):
    data: List[SensorDataPoint]
    query: TimeSeriesQuery
    total_points: int


class SummaryStats(BaseModel):
    timestamp: float
    avg_current_density: float
    max_current_density: float
    avg_temperature: float
    max_temperature: float
    avg_magnetic_field: float
    avg_resistivity: float
    quench_detected: bool
    quench_sensors: List[str]


class ParticleData(BaseModel):
    id: int
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    size: float
    opacity: float
    temperature: float


class ParticleResponse(BaseModel):
    particles: List[ParticleData]
    timestamp: float
    heat_zone_temperature: float
