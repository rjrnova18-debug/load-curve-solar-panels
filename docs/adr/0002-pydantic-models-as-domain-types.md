# Pydantic models are the domain types

Domain concepts such as `Load`, `LoadTable` and `SizingAssumptions` are Pydantic models, used directly by the calculation modules and by the FastAPI routes. Every validation rule (non-negative rated power, usage factor between 0 and 1, a schedule of exactly 24 on/off flags, unique Load names) is written once and applies equally to JSON requests and to rows imported from CSV/XLSX files.

## Considered Options

- **Plain dataclasses in the domain plus separate Pydantic schemas in the API layer**: rejected. It keeps the domain free of a library dependency, but at this project's size it would duplicate every model and every rule, and the two copies would drift apart. If the domain ever needs to outlive Pydantic, the models are small enough to split later.
