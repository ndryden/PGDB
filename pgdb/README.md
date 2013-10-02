PGDB
====
PGDB is a GDB-based parallel/distributed debugger, written primarily in Python,
for debugging MPI applications on a cluster.

License
-------
PGDB is licensed under the BSD License with an additional notice. See LICENSE
for more details.

Availability
------------
PGDB is available at its Github project page, <https://github.com/ndryden/PGDB>.

Installation
------------
This is a brief summary of the installation process. For full details, see the
installation section in the manual available in docs/pgdbman.pdf. See the
Further Documentation section if the manual is not present.

### Requirements ###
* Python 2.6 or greater (2.7 recommended, >= 3 not supported)
  <http://www.python.org/>
* GDB 7.0 or greater (7.4 or greater recommended)
  <http://sources.redhat.com/gdb/>
* LaunchMON 0.7.2 or greater (1.0 recommended)
  <http://sourceforge.net/projects/launchmon/>
* MRNet 4.0.0
  <http://www.paradyn.org/mrnet/>
* PyBindGen 0.16.0 or greater
  <http://code.google.com/p/pybindgen/>
  This is only needed if you need to re-generate the MRNet bindings.
* Python bindings for MRNet (included)
* Python bindings for LaunchMON (included)

### Installing ###
This pgdb folder can be placed anywhere on your system to install it. There are
no further steps, assuming all dependencies have been installed correctly.

You will need to update the conf/gdbconf.py configuration file with your local
configuration options. Additionally, you may need to update the LaunchMON
configuration file before you install it.

Usage
-----
PGDB can run in either attach or launch modes.

In attach mode, PGDB will debug an already-running MPI job. PGDB will need to be
run on the same machine that you run your `mpirun' command (or equivalent) from.
You will need the PID of this process, which you can obtain with e.g.
`ps x | grep mpirun'. You then need to run PGDB with `pgdb -p PID>' to begin
debugging the job.

In launch mode, PGDB will launch a new MPI job directly under its control. The
syntax for this is `pgdb --launcher launcher -a args' where launcher is the MPI
launcher to use (defaults to `srun' if not specified) and args are the arguments
you would typically pass to the launcher in order to launch the job.

Additional information on using PGDB is available in the manual (see Further
Documentation), and brief command-line documentation is available by running
`pgdb -h'.

Further Documentation
---------------------
Complete documentation on PGDB is available in docs/pgdbman.pdf. If the manual
is not present, it can be generated from the included LaTeX sources using
pdflatex.

Credits
-------
PGDB is written and maintained by Nikoli Dryden, who you can reach at either of
these emails: <dryden2@illinois.edu> and <dryden1@llnl.gov>.

Development of PGDB has been supported by Lawrence Livermore National Laboratory
(LLNL), the National Center for Supercomputing Applications (NCSA), and the
Extreme Science and Engineering Discovery Environment (XSEDE).
