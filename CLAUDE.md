# HEC-RAS Compliance Checker

## Project Overview

Python 3.10+ tool that validates HEC-RAS hydraulic models against regulatory compliance rules. The target user is a hydraulic engineer, not a software developer.

## Tech Stack

- **Language**: Python 3.10+
- **Build**: setuptools with src layout (`src/hecras_compliance/`)
- **CLI**: click (`hecras-check` entry point)
- **HDF5 reading**: h5py (for HEC-RAS 6.x+ result files)
- **Config/rules**: pyyaml
- **Reports**: fpdf2
- **Testing**: pytest

## HEC-RAS File Formats

- **Geometry files** (`.g01`–`.g99`): Structured text with keyword sections like `BEGIN HEADER`, `Manning's n Values`, `XS GIS Cut Line`, `Bridge/Culvert`
- **Plan files** (`.p01`–`.p99`): Simulation parameters
- **Flow files** (`.f01`–`.f99`): Steady/unsteady flow data
- **HDF results** (`.hdf`): HEC-RAS 6.x+ stores results in HDF5 format, read with h5py

## Compliance Rules

- All compliance rules live in YAML config files — never hardcoded in Python
- Every check must cite a specific regulation (e.g., `44 CFR 65.12`, `TX Admin Code §299.14`)
- We follow FEMA Guidelines and Specifications for Flood Hazard Mapping Partners

## Project Structure

```
src/hecras_compliance/   # Main package
tests/                   # pytest tests with fixture files
```

## Commands

```bash
source .venv/bin/activate
pytest                   # Run tests
pip install -e ".[dev]"  # Install in dev mode
```

## Conventions

- Keep compliance logic declarative: YAML rules in, pass/fail results out
- Parsers for each HEC-RAS file type should be independent modules
- Test with realistic fixture files under `tests/`
