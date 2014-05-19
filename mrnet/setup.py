from distutils.core import setup, Extension

mrnet_path = raw_input("Please type the base path to MRNet: ")
if mrnet_path[-1:] == '/':
    mrnet_path = mrnet_path[:-1]
mrnet = Extension("MRNet",
                  sources = ["mrnet_module.cpp"],
                  include_dirs = [mrnet_path + "/include"],
                  library_dirs = [mrnet_path + "/lib"],
                  libraries = ["mrnet", "xplat", "boost_timer-mt", "boost_system-mt"],
                  extra_compile_args = [],
                  extra_link_args = ["-Wl,-rpath=" + mrnet_path + "/lib", "-Wl,-E"])
setup(name = "MRNet", version = "0.01", description = "Python interface to MRNet", ext_modules = [mrnet])
