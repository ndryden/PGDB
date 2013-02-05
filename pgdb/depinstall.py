"""Download and install PGDB dependencies.

This downloads LaunchMON and MRNet, builds, and installs them."""

import subprocess, sys, os, compileall, re

# The curl command to invoke.
curl = "curl -L {0}"

# The extraction command for .tar.gz.
extract_tgz = "tar -xzf {0}"
# The extraction command for .tar.bz2.
extract_tbz2 = "tar -xjf {0}"
# The extraction command for .zip.
extract_zip = "unzip {0}"

# The configure command to use.
configure = "./configure {0}"

# The make command to build.
make = "make"

# The make install command to install.
make_install = "make install"

# Waf configure/build/install commands.
waf_configure = "./waf configure {0}"
waf_build = "./waf"
waf_install = "./waf install"

# Python distutils build/install.
pydist_build = "python setup.py build"
pydist_install = "python setup.py install {0}"

# How to clean.
clean_file = "rm -f {0}"
clean_dir = "rm -rf {0}"

# Default configuration options.
config_opts = ""

# The directory to download/build things in.
working_dir = "third-party"

# LaunchMON sources.
launchmon_url = "http://sourceforge.net/projects/launchmon/files/launchmon/0.7%20stable%20releases/launchmon-0.7.2.tar.gz/download"
launchmon_dist = "launchmon-0.7.2.tar.gz"
launchmon_dir = launchmon_dist.replace(".tar.gz", "")
launchmon_extract = extract_tgz
launchmon_config = "--with-rm=slurm"

# MRNet sources.
mrnet_url = "ftp://ftp.cs.wisc.edu/paradyn/mrnet/mrnet_4.0.0.tar.gz"
mrnet_dist = "mrnet_4.0.0.tar.gz"
mrnet_dir = mrnet_dist.replace(".tar.gz", "")
mrnet_extract = extract_tgz
mrnet_config = ""

# PyBindGen sources.
pybindgen_url = "http://pybindgen.googlecode.com/files/pybindgen-0.16.0.tar.bz2"
pybindgen_dist = "pybindgen-0.16.0.tar.bz2"
pybindgen_dir = pybindgen_dist.replace(".tar.bz2", "")
pybindgen_extract = extract_tbz2
pybindgen_config = ""

# mpi4py sources.
mpi4py_url = "http://mpi4py.googlecode.com/files/mpi4py-1.3.tar.gz"
mpi4py_dist = "mpi4py-1.3.tar.gz"
mpi4py_dir = mpi4py_dist.replace(".tar.gz", "")
mpi4py_extract = extract_tgz
mpi4py_config = ""

# MRNet bindings.
mrnetbind_url = None
mrnetbind_dist = None
mrnetbind_dir = "mrnet-bind"
mrnetbind_extract = None
mrnetbind_config = ""

def download_extract(url, dist, extract):
    """Download and extract something."""
    ret = subprocess.call(curl.format(url) + " > " + dist, stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on downloading {1}!".format(ret, url)
        sys.exit(1)
    ret = subprocess.call(extract.format(dist), stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on extract: `{1}'".format(ret, extract.format(dist))
        sys.exit(1)

def make_build_install(directory, config_opts):
    """Use configure/make/make install to build something."""
    # Change to the directory to make path handling easier.
    cwd = os.getcwd()
    os.chdir(directory)
    # Configure.
    ret = subprocess.call(configure.format(config_opts), stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on configure `{1}' in {2}!".format(
            ret, configure.format(config_opts), directory)
        sys.exit(1)
    # Build.
    ret = subprocess.call(make, stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on make `{1}' in {2}!".format(ret, make, directory)
        sys.exit(1)
    # Install.
    ret = subprocess.call(make_install, stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on install `{1}' in {2}!".format(ret, make_install,
                                                                         directory)
        sys.exit(1)
    os.chdir(cwd)

def waf_build_install(directory, config_opts):
    """Use waf to build something (PyBindGen only for now)."""
    cwd = os.getcwd()
    os.chdir(directory)
    # Configure.
    ret = subprocess.call(waf_configure.format(config_opts), stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on configure `{1}' in {2}!".format(
            ret, waf_configure.format(config_opts), directory)
        sys.exit(1)
    # Build.
    ret = subprocess.call(waf_build, stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on build `{1}' in {2}!".format(ret, waf_build, directory)
        sys.exit(1)
    # Install.
    ret = subprocess.call(waf_install, stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on install `{1}' in {2}!".format(ret, waf_install, directory)
        sys.exit(1)
    os.chdir(cwd)

def pydist_build_install(directory, config_opts):
    """Use Python's distutils to build something."""
    cwd = os.getcwd()
    os.chdir(directory)
    # Build.
    ret = subprocess.call(pydist_build, stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on build `{1}' in {2}!".format(ret, pydist_build, directory)
        sys.exit(1)
    # Install.
    ret = subprocess.call(pydist_install.format(config_opts), stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on install `{1}' in {2}!".format(
            ret, pydist_install.format(config_opts), directory)
        sys.exit(1)
    os.chdir(cwd)

def download_build_install(url, dist, directory, extract, build_func, config_opts = ""):
    """Download, build, and install something."""
    download_extract(url, dist, extract)
    build_func(directory, config_opts)

def clean(dist, directory):
    """Clean something."""
    ret = subprocess.call(clean_dir.format(directory), stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on clean `{1}'!".format(ret, clean_dir.format(directory))
        sys.exit(1)
    if not dist:
        return
    ret = subprocess.call(clean_file.format(dist), stdout = sys.stdout, shell = True)
    if ret != 0:
        print "Non-zero return code {0} on clean `{1}'!".format(ret, clean_file.format(dist))
        sys.exit(1)

def do_build():
    """Build everything."""
    # Change into the working directory.
    if not os.path.isdir(working_dir):
        if os.path.exists(working_dir):
            print "Working directory {0} exists and is not a directory!".format(working_dir)
            sys.exit(1)
        os.makedirs(working_dir)
    cwd = os.getcwd()
    os.chdir(working_dir)
    # Build LaunchMON.
    print "=========="
    print "Building LaunchMON."
    print "=========="
    print "LaunchMON 1.0 sources are not yet available!"
    print "You can check them out from version control at http://sourceforge.net/projects/launchmon/ and build them yourself (recommended)."
    print "Note that if you use the 0.7.2 release, you probably will need to update conf/lmonconf.py."
    print "Using default config options '" + launchmon_config + "'"
    download_build_install(launchmon_url, launchmon_dist, launchmon_dir, launchmon_extract,
                           make_build_install, config_opts + " " + launchmon_config)
    # Build MRNet.
    print "=========="
    print "Building MRNet."
    print "=========="
    download_build_install(mrnet_url, mrnet_dist, mrnet_dir, mrnet_extract,
                           make_build_install, config_opts + " " + mrnet_config)
    # Build PyBindGen.
    print "=========="
    print "Building PyBindGen."
    print "=========="
    download_build_install(pybindgen_url, pybindgen_dist, pybindgen_dir, pybindgen_extract,
                           waf_build_install, config_opts + " " + pybindgen_config)
    # Build mpi4py.
    print "=========="
    print "Building mpi4py."
    print "=========="
    download_build_install(mpi4py_url, mpi4py_dist, mpi4py_dir, mpi4py_extract, pydist_build_install,
                           config_opts + " " + mpi4py_config)
    # Return to the regular directory for building the MRNet bindings.
    os.chdir(cwd)
    # Build the MRNet bindings.
    print "=========="
    print "Building MRNet Python bindings. (Not regenerating bindings.)"
    print "=========="
    pydist_build_install(mrnetbind_dir, config_opts + " " + mrnetbind_config)

    # Compile Python files.
    print "=========="
    print "Compiling Python files."
    print "=========="
    rx = re.compile(working_dir)
    compileall.compile_dir(".", rx = rx)

    print "=========="
    print "Everything built. Remember that you will probably need to edit the config files."

def do_clean():
    """Clean everything."""
    # Enter the working directory.
    if not os.path.isdir(working_dir):
        print "Cannot find working directory {0}!".format(working_dir)
        sys.exit(1)
    cwd = os.getcwd()
    os.chdir(working_dir)
    print "Cleaning all."
    # Clean LaunchMON.
    clean(launchmon_dist, launchmon_dir)
    # Clean MRNet.
    clean(mrnet_dist, mrnet_dir)
    # Clean PyBindGen.
    clean(pybindgen_dist, pybindgen_dir)
    # Clean mpi4py.
    clean(mpi4py_dist, mpi4py_dir)
    # Return to the regular directory.
    os.chdir(cwd)
    # Clean the MRNet bindings.
    clean(None, os.path.join(mrnetbind_dir, "build"))

# Parse input arguments and do stuff.
action = "build"
if len(sys.argv) == 2 and sys.argv[1] == "clean":
    action = "clean"

if action == "build":
    if len(sys.argv) > 1:
        # Any additional arguments are passed to configure.
        config_opts = " ".join(sys.argv[2:])
    do_build()
elif action == "clean":
    do_clean()
else:
    print "Unknown action!"
    sys.exit(1)
