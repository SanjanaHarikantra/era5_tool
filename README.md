# ERA5 Wind Data Processing Tool

## 🌐 Live Demo

🚀 **Deployment Link:**
https://era5-tool.onrender.com

Try the application online to retrieve and analyze ERA5 wind data directly from the browser.

## Overview

The ERA5 Wind Data Processing Tool is a web-based application that enables users to retrieve, process, and analyze wind data from the Copernicus Climate Data Store (CDS). Users can provide geographical coordinates and date ranges to generate processed datasets containing wind speed, wind direction, and wind power density information.

## Features

* Secure user registration and authentication using JWT.
* Integration with Copernicus Climate Data Store (CDS) API.
* Automated ERA5 wind data download and processing.
* Wind speed, wind direction, and power density calculations.
* Background job processing for improved user experience.
* Downloadable NetCDF and CSV output files.
* Request history and status tracking.

## Tech Stack

### Frontend

* HTML
* CSS
* JavaScript
* Jinja2 Templates

### Backend

* Python Flask
* Flask-JWT-Extended
* Flask-Bcrypt
* SQLAlchemy

### Database

* SQLite

### Data Processing

* CDS API
* xarray
* pandas
* numpy

## Workflow

1. Register or log in to the application.
2. Obtain a CDS API key from the Copernicus Climate Data Store.
3. Save the API key in the application.
4. Submit a wind data request with location and date range.
5. Background processing downloads and analyzes ERA5 data.
6. Download generated NetCDF and CSV files.

## Security Features

* Password hashing with bcrypt.
* JWT-based authentication.
* Server-side input validation.
* User-specific file access control.

## Future Enhancements

* Interactive charts and visualizations.
* Additional weather and climate parameters.
* Improved processing performance.
* Cloud deployment and scalability.

## Author

**Sanjana Harikantra**
**Vaishnavi Tandel**


