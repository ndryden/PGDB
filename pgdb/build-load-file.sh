#!/bin/bash

gcc -O0 -g -std=c99 -Wall -Wno-int-to-pointer-cast -Wno-pointer-to-int-cast -shared -fPIC src/gdb_load_file.c -o load_file.so -ldl -pthread -lrt
