from distutils.core import setup, Extension

use_mrnet400 = True

if use_mrnet400:
    mrnet = Extension("MRNet",
                      sources = ["mrnet_module.cpp"],
                      include_dirs = ["/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0/include"],
                      library_dirs = ["/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0/lib"],
                      libraries = ["mrnet", "xplat", "boost_timer-mt", "boost_system-mt"],
                      extra_compile_args = ["-O0", "-g"],
                      extra_link_args = ["-Wl,-rpath=/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0/lib", "-Wl,-E"])
else:
    mrnet = Extension("MRNet",
                      sources = ["mrnet_module.cpp"],
                      include_dirs = ["/usr/local/tools/mrnet-3.1.0/include"],
                      library_dirs = ["/usr/local/tools/mrnet-3.1.0/lib"],
                      libraries = ["mrnet", "xplat"],
                      extra_compile_args = ["-O0", "-g"],
                      extra_link_args = ["-Wl,-rpath=/usr/local/tools/mrnet-3.1.0/lib", "-Wl,-E"])

setup(name = "MRNet", version = "0.01", description = "Python interface to MRNet", ext_modules = [mrnet])
