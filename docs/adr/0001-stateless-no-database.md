# Stateless app, no database

The server keeps no state between requests: the browser holds the Load table and settings, sends them to the API for every calculation, and the user saves their work as files (the Load table as CSV/XLSX, or the whole session as a JSON project file). There are no user accounts and no database.

The tool produces an estimate for one site in one sitting; storing projects server-side would add authentication, persistence and data-protection concerns without improving the calculation. Being stateless also makes the API trivial to test and to deploy on a free host.

## Considered Options

- **Database with saved projects and user accounts**: rejected. Accounts and persistence would become the largest part of the codebase, while files already let users keep and share their work.
