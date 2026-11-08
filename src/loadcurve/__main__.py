"""Run the development server with ``python -m loadcurve``."""

import uvicorn


def main() -> None:
    # The app is passed as an import string so that --reload can re-import it.
    uvicorn.run("loadcurve.api.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
