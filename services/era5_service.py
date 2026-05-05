import os
import math
import tempfile
import traceback
import subprocess
import sys
from datetime import datetime


def _ensure_netcdf_backends():
    cmd = [sys.executable, "-m", "pip", "install", "netCDF4", "h5netcdf", "h5py"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _open_era5_dataset(nc_path):
    import xarray as xr

    for engine in ('netcdf4', 'h5netcdf', None):
        try:
            if engine is None:
                return xr.open_dataset(nc_path)
            return xr.open_dataset(nc_path, engine=engine)
        except Exception:
            continue

    installed, install_log = _ensure_netcdf_backends()
    if installed:
        for engine in ('netcdf4', 'h5netcdf', None):
            try:
                if engine is None:
                    return xr.open_dataset(nc_path)
                return xr.open_dataset(nc_path, engine=engine)
            except Exception:
                continue

    raise RuntimeError(
        "Unable to open downloaded ERA5 NetCDF file for CSV conversion. "
        f"Python runtime: {sys.executable}. "
        "Tried auto-installing netCDF4/h5netcdf/h5py but still failed. "
        f"Installer output: {install_log[-800:]}"
    )


def convert_nc_to_csv(nc_path, csv_path, place_name, latitude, longitude, start_date, end_date):
    import numpy as np
    import pandas as pd

    ds = _open_era5_dataset(nc_path)
    time_var = "time" if "time" in ds.variables else "valid_time"
    ds_site = ds.sel(latitude=latitude, longitude=longitude, method="nearest")
    if "expver" in ds_site.dims:
        ds_site = ds_site.isel(expver=0)

    if "u100" not in ds_site.variables or "v100" not in ds_site.variables:
        ds.close()
        raise RuntimeError("Downloaded NetCDF does not contain required variables: u100 and v100")

    # Extract site time series
    u = ds_site["u100"].values.squeeze()
    v = ds_site["v100"].values.squeeze()
    times = ds_site[time_var].values
    selected_lat = float(ds_site.latitude.values)
    selected_lon = float(ds_site.longitude.values)
    ds.close()

    # Build hourly dataframe
    df = pd.DataFrame({
        "time": pd.to_datetime(times),
        "u100_m_s": u,
        "v100_m_s": v,
    })
    df = df[
        (df["time"] >= pd.to_datetime(start_date)) &
        (df["time"] < (pd.to_datetime(end_date) + pd.Timedelta(days=1)))
    ]
    df["wind_speed_m_s"] = np.sqrt(df["u100_m_s"] ** 2 + df["v100_m_s"] ** 2)
    df["wind_speed_kmh"] = df["wind_speed_m_s"] * 3.6
    df["wind_direction_deg"] = (np.degrees(np.arctan2(-df["u100_m_s"], -df["v100_m_s"])) + 360) % 360
    df["power_density_W_m2"] = 0.5 * 1.225 * df["wind_speed_m_s"] ** 3
    df["place_name"] = place_name
    df["requested_latitude"] = latitude
    df["requested_longitude"] = longitude
    df["selected_latitude"] = selected_lat
    df["selected_longitude"] = selected_lon
    df = df.dropna(subset=["wind_speed_m_s"])
    df.to_csv(csv_path, index=False)

    # Monthly + annual parameters
    summary_df = df.copy()
    summary_df["month"] = summary_df["time"].dt.month
    summary = summary_df.groupby("month").agg(
        mean_wind_speed=("wind_speed_m_s", "mean"),
        std_wind_speed=("wind_speed_m_s", "std"),
        min_wind_speed=("wind_speed_m_s", "min"),
        max_wind_speed=("wind_speed_m_s", "max"),
        p10=("wind_speed_m_s", lambda x: x.quantile(0.10)),
        p50=("wind_speed_m_s", lambda x: x.quantile(0.50)),
        p90=("wind_speed_m_s", lambda x: x.quantile(0.90)),
        mean_power_density=("power_density_W_m2", "mean"),
        total_hours=("wind_speed_m_s", "count"),
    ).reset_index()

    threshold_90 = summary_df["wind_speed_m_s"].quantile(0.90)
    top10_data = summary_df[summary_df["wind_speed_m_s"] >= threshold_90]
    top10_mean_speed = float(top10_data["wind_speed_m_s"].mean()) if not top10_data.empty else np.nan
    top10_power_density = float(top10_data["power_density_W_m2"].mean()) if not top10_data.empty else np.nan

    annual_row = pd.DataFrame({
        "month": ["Annual"],
        "mean_wind_speed": [summary_df["wind_speed_m_s"].mean()],
        "std_wind_speed": [summary_df["wind_speed_m_s"].std()],
        "min_wind_speed": [summary_df["wind_speed_m_s"].min()],
        "max_wind_speed": [summary_df["wind_speed_m_s"].max()],
        "p10": [summary_df["wind_speed_m_s"].quantile(0.10)],
        "p50": [summary_df["wind_speed_m_s"].quantile(0.50)],
        "p90": [threshold_90],
        "mean_power_density": [summary_df["power_density_W_m2"].mean()],
        "total_hours": [len(summary_df)],
        "top10_mean_wind_speed_m_s": [top10_mean_speed],
        "top10_mean_power_density_W_m2": [top10_power_density],
        "top10_number_of_hours": [len(top10_data)],
        "selected_latitude": [selected_lat],
        "selected_longitude": [selected_lon],
    })

    summary = pd.concat([summary, annual_row], ignore_index=True)
    return summary


def infer_nc_defaults(nc_path):
    import pandas as pd

    ds = _open_era5_dataset(nc_path)
    time_var = "time" if "time" in ds.variables else "valid_time"

    if "latitude" not in ds.variables or "longitude" not in ds.variables:
        ds.close()
        raise RuntimeError("NetCDF file is missing latitude/longitude coordinates")

    lat_vals = ds["latitude"].values
    lon_vals = ds["longitude"].values
    lat = float(lat_vals.flat[0])
    lon = float(lon_vals.flat[0])

    times = pd.to_datetime(ds[time_var].values)
    if len(times) == 0:
        ds.close()
        raise RuntimeError("NetCDF file does not contain time values")

    start_date = times.min().strftime("%Y-%m-%d")
    end_date = times.max().strftime("%Y-%m-%d")
    ds.close()

    return {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
    }


def process_era5_request(request_id: int, api_key: str, variables=None, buffer=0.1):
    """
    Background worker: fetch ERA5 data, compute wind stats, save files.
    Uses a Flask app context so it can update the database.
    """
    # Import here to avoid circular imports
    from app import app, db
    from models import Request as DataRequest

    with app.app_context():
        req = DataRequest.query.get(request_id)
        if not req:
            return

        req.status = 'Processing'
        db.session.commit()

        try:
            import cdsapi
            import pandas as pd

            # ── Directory setup ──────────────────────────────────────────────
            safe_name = "".join(c if c.isalnum() else "_" for c in req.place_name)
            ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            out_dir = os.path.join('downloads', safe_name)
            os.makedirs(out_dir, exist_ok=True)

            nc_path      = os.path.join(out_dir, f'{safe_name}_{ts}.nc')
            csv_path     = os.path.join(out_dir, f'{safe_name}_{ts}_hourly.csv')
            summary_path = os.path.join(out_dir, f'{safe_name}_{ts}_monthly.csv')

            start = datetime.strptime(req.start_date, '%Y-%m-%d')
            end   = datetime.strptime(req.end_date,   '%Y-%m-%d')
            if variables is None:
                variables = [
                    '100m_u_component_of_wind',
                    '100m_v_component_of_wind',
                ]

            # ── CDS API call ─────────────────────────────────────────────────
            # Write a temporary .cdsapirc so cdsapi picks up the user's key
            cdsapirc = os.path.join(tempfile.gettempdir(), f'.cdsapirc_{request_id}')
            with open(cdsapirc, 'w') as f:
                f.write(f'url: https://cds.climate.copernicus.eu/api\n')
                f.write(f'key: {api_key}\n')
                f.write('verify: 1\n')

            os.environ['CDSAPI_RC'] = cdsapirc

            # ERA5 archive uses a 0.25-degree grid. Snap the requested box
            # outward to the grid and enforce at least one full grid cell.
            grid = 0.25
            effective_buffer = max(float(buffer), grid / 2)
            north_raw = req.latitude + effective_buffer
            west_raw = req.longitude - effective_buffer
            south_raw = req.latitude - effective_buffer
            east_raw = req.longitude + effective_buffer

            north = math.ceil(north_raw / grid) * grid
            west = math.floor(west_raw / grid) * grid
            south = math.floor(south_raw / grid) * grid
            east = math.ceil(east_raw / grid) * grid

            if north <= south:
                north = south + grid
            if east <= west:
                east = west + grid

            client = cdsapi.Client(quiet=True)
            client.retrieve(
                'reanalysis-era5-single-levels',
                {
                    'product_type': 'reanalysis',
                    'variable': variables,
                    'date': f'{req.start_date}/{req.end_date}',
                    'time':  [f'{h:02d}:00' for h in range(24)],
                    'area':  [north, west, south, east],
                    'data_format': 'netcdf',
                    'download_format': 'unarchived',
                },
                nc_path
            )

            # Clean up temp rc file
            try:
                os.remove(cdsapirc)
            except OSError:
                pass

            csv_generated = False
            summary_generated = False

            # ── xarray → DataFrame ───────────────────────────────────────────
            # If optional NetCDF engines are missing, keep request successful
            # with at least the downloaded .nc file available.
            try:
                summary = convert_nc_to_csv(
                    nc_path=nc_path,
                    csv_path=csv_path,
                    place_name=req.place_name,
                    latitude=req.latitude,
                    longitude=req.longitude,
                    start_date=req.start_date,
                    end_date=req.end_date,
                )
                csv_generated = True

                # ── Monthly summary CSV ──────────────────────────────────────
                summary.to_csv(summary_path, index=False)
                summary_generated = True
                req.error_message = None
            except Exception as csv_exc:
                warning = (
                    "NetCDF downloaded successfully, but CSV conversion was skipped. "
                    f"Reason: {csv_exc}"
                )
                print(f"[ERA5 Warning] request {request_id}: {warning}")
                req.error_message = warning

            # ── Update DB ────────────────────────────────────────────────────
            req.status           = 'Completed'
            req.nc_path          = nc_path
            req.csv_path         = csv_path if csv_generated else None
            req.summary_csv_path = summary_path if summary_generated else None
            db.session.commit()

        except Exception as exc:
            tb = traceback.format_exc()
            print(f"[ERA5 Error] request {request_id}:\n{tb}")
            req.status        = 'Failed'
            req.error_message = str(exc)
            db.session.commit()