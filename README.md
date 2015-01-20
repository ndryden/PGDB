PGDB
====

**Warning: PGDB currently has several known major bugs and is somewhat out of date.** Real work on it will resume when my current project is more stable.

PGDB is a parallel/distributed debugger, based upon GDB, designed for debugging
MPI jobs on a cluster. The tool has been tested on Linux clusters and presently
scales to about 1K processes.

This package includes the PGDB application and associated Python bindings for
LaunchMON and MRNet, two tools that PGDB requires.

For further instructions on installing and using PGDB, see pgdb/README for an
overview or the documentation in pgdb/doc for complete instructions. For PGDB
licensing information, see pgdb/LICENSE.
