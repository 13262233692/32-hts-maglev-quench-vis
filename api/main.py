from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import asyncio
import json
import logging

from models import (
    SensorInfo, SensorDataPoint, TimeSeriesQuery, TimeSeriesResponse,
    SummaryStats, ParticleResponse
)
from data_processor import HTSDataProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HTS Maglev Quench Visualization API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

processor = HTSDataProcessor()


@app.get("/api/sensors", response_model=List[SensorInfo])
async def get_sensors():
    sensors = processor.get_sensor_list()
    return [
        SensorInfo(
            sensor_id=s["sensor_id"],
            position=(float(s["pos_x"]), float(s["pos_y"]), float(s["pos_z"])),
            type=s["type"],
            channel=int(s["channel"])
        )
        for s in sensors
    ]


@app.get("/api/time-range")
async def get_time_range():
    start, end = processor.get_time_range()
    return {"start_time": start, "end_time": end}


@app.get("/api/timeseries", response_model=TimeSeriesResponse)
async def get_timeseries(
    start_time: float,
    end_time: float,
    sensor_ids: Optional[str] = None,
    downsample: int = Query(default=1, ge=1, le=1000)
):
    sensor_id_list = sensor_ids.split(",") if sensor_ids else None
    
    df = processor.query_time_series(
        start_time=start_time,
        end_time=end_time,
        sensor_ids=sensor_id_list,
        downsample=downsample
    )
    
    data_points = [
        SensorDataPoint(
            timestamp=float(row["timestamp"]),
            sensor_id=row["sensor_id"],
            current_density=float(row["current_density"]),
            temperature=float(row["temperature"]),
            magnetic_field=float(row["magnetic_field"]),
            resistivity=float(row["resistivity"])
        )
        for _, row in df.iterrows()
    ]
    
    query = TimeSeriesQuery(
        start_time=start_time,
        end_time=end_time,
        sensor_ids=sensor_id_list,
        downsample=downsample
    )
    
    return TimeSeriesResponse(
        data=data_points,
        query=query,
        total_points=len(data_points)
    )


@app.get("/api/summary", response_model=SummaryStats)
async def get_summary(timestamp: float):
    stats = processor.get_summary(timestamp)
    return SummaryStats(**stats)


@app.get("/api/particles", response_model=ParticleResponse)
async def get_particles(timestamp: float, num_particles: int = Query(default=3000, ge=100, le=10000)):
    summary = processor.get_summary(timestamp)
    heat_zone_temp = summary.get("avg_temperature", 77.0)
    
    particles = processor.get_particles(
        timestamp=timestamp,
        num_particles=num_particles,
        heat_zone_temp=heat_zone_temp
    )
    
    return ParticleResponse(
        particles=particles,
        timestamp=timestamp,
        heat_zone_temperature=heat_zone_temp
    )


@app.get("/api/quench-events")
async def get_quench_events(start_time: float, end_time: float):
    events = processor.detect_quench_events(start_time, end_time)
    return {"events": events}


@app.get("/api/cross-correlation")
async def get_cross_correlation(
    start_time: float,
    end_time: float,
    voltage_sensor: str,
    temperature_sensor: str
):
    result = processor.get_cross_correlation_summary(
        start_time=start_time,
        end_time=end_time,
        voltage_sensor=voltage_sensor,
        temperature_sensor=temperature_sensor
    )
    return result


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    start_time, end_time = processor.get_time_range()
    current_time = start_time
    playback_speed = 1.0
    is_playing = False
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                message = json.loads(data)
                
                if "action" in message:
                    if message["action"] == "play":
                        is_playing = True
                        playback_speed = message.get("speed", 1.0)
                    elif message["action"] == "pause":
                        is_playing = False
                    elif message["action"] == "seek":
                        current_time = float(message.get("timestamp", current_time))
                        current_time = max(start_time, min(end_time, current_time))
                    elif message["action"] == "set_speed":
                        playback_speed = message.get("speed", 1.0)
                
            except asyncio.TimeoutError:
                pass
            
            if is_playing:
                current_time += 0.016 * playback_speed
                if current_time > end_time:
                    current_time = start_time
                
                stats = processor.get_summary(current_time)
                particles = processor.get_particles(current_time, num_particles=2000)
                
                await websocket.send_json({
                    "type": "update",
                    "timestamp": current_time,
                    "stats": stats,
                    "particles": particles
                })
            
            await asyncio.sleep(0.016)
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
