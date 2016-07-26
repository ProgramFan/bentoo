# TODO

- [x] Use generator to simplify collector pipeline
- [x] Support table column filter in collector
- [x] Add a pandas backend for collector
- [x] Support table selection other than -1
- [x] Make possible to run a subpart of a test
- [x] Add an option to runner to generate running scripts instead of real run
- [ ] Add result parser spec support in generator
- [ ] Refactor runner for better extensibility

# Future Ideas

1. Unified storage backend: define an unified interface to data storage and
   implement sqlite, pandas etc. as backends.
2. Parallel and out-of-core data processing support: through dask maybe.
