#define _GNU_SOURCE

#include <stdlib.h>
#include <limits.h>
#include <stdio.h>
#include <stdarg.h>
#include <dlfcn.h>
#include <string.h>
#include <semaphore.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <stdint.h>
#include <unistd.h>
#include <errno.h>

#define GDB_SEMAPHORE_NAME "/PGDBSemaphore"
#define GDB_SHMEM_NAME "/PGDBMem"
#define GDB_SHMEM_SIZE 33554432
// This is GDB_SHMEM_SIZE - 6.
#define GDB_SHMEM_DATA_SIZE 33554426
#define GDB_SHMEM_ERROR "error"

struct _gdb_mem {
	uint8_t pgdb_dw;
	uint8_t gdb_dw;
	uint32_t size;
	uint8_t data[GDB_SHMEM_DATA_SIZE];
} __attribute__((packed));
typedef struct _gdb_mem gdb_mem_t;

struct _filename_list;

struct _data_buf {
	size_t size; // Size of data.
	void* data; // File data.
	uint32_t ref_count; // Number of references.
	struct _filename_list* filename; // Pointer to associated filename entry.
};
typedef struct _data_buf data_buf_t;

struct _file_data {
	int fd; // Internal file descriptor.
	off_t offset; // Current offset in data.
	data_buf_t* data; // File data.
	struct _file_data* prev;
	struct _file_data* next;
};
typedef struct _file_data file_data_t;

struct _filename_list {
	char* filename; // Filename.
	data_buf_t* data; // Pointer to associated data.
	int error; // Whether this file had an error in loading.
	struct _filename_list* prev;
	struct _filename_list* next;
};
typedef struct _filename_list filename_list_t;

// open
typedef int (*orig_open_t)(const char*, int, ...);
// close
typedef int (*orig_close_t)(int);
// read
typedef ssize_t (*orig_read_t)(int, void*, size_t);
// write
typedef ssize_t (*orig_write_t)(int, const void*, size_t);
// fcntl
typedef int (*orig_fcntl_t)(int, int, ...);
// fstat
typedef int (*orig_fstat_t)(int, struct stat*);
// lseek
typedef off_t (*orig_lseek_t)(int, off_t, int);
// pread
typedef ssize_t (*orig_pread_t)(int, void*, size_t, off_t);
// fopen
typedef FILE* (*orig_fopen_t)(const char*, const char*);
// fdopen
typedef FILE* (*orig_fdopen_t)(int, const char*);
// fclose
typedef int (*orig_fclose_t)(FILE*);
// fread
typedef size_t (*orig_fread_t)(void* restrict, size_t, size_t, FILE*);
// fwrite
typedef size_t (*orig_fwrite_t)(const void* restrict, size_t, size_t, FILE*);
// fgetc
typedef int (*orig_fgetc_t)(FILE*);
// fgets
typedef char* (*orig_fgets_t)(char*, int, FILE*);
// clearerr
typedef void (*orig_clearerr_t)(FILE*);
// feof
typedef int (*orig_feof_t)(FILE*);
// ferror
typedef int (*orig_ferror_t)(FILE*);
// fileno
typedef int (*orig_fileno_t)(FILE*);
// fileno_unlocked
typedef int (*orig_fileno_unlocked_t)(FILE*);
// fseeko64
typedef int (*orig_fseeko64_t)(FILE*, off64_t, int);
// ftello64
typedef off64_t (*orig_ftello64_t)(FILE*);
// mmap
typedef void* (*orig_mmap_t)(void*, size_t, int, int, int, off_t);
// munmap
typedef int (*orig_munmap_t)(void*, size_t);

// Semaphore for syncronizing with PGDB.
sem_t* gdb_semaphore = NULL;
// Mmap'd shared memory for communicating with PGDB.
gdb_mem_t* gdb_mem = NULL;
// File descriptor for shared memory.
int gdb_mem_fd;
// Whether the set-up is good.
int good = 0;
// Next file descriptor. Start high to avoid conflicts.
int next_fd = 65535;
// Linked list of file_data_t structs.
file_data_t* data_list = NULL;
// Linked list of filename_list_t structs.
filename_list_t* filename_list = NULL;

data_buf_t* create_data_buffer(void* buf, size_t size) {
	data_buf_t* data_buf = (data_buf_t*) malloc(sizeof(data_buf_t));
	data_buf->size = size;
	data_buf->data = buf;
	data_buf->ref_count = 2;
	data_buf->filename = NULL;
	return data_buf;
}

void del_filename_entry(char*);

int del_data_buffer(data_buf_t* data_buf) {
	data_buf->ref_count--;
	if (data_buf->ref_count == 0) {
		free(data_buf->data);
		free(data_buf);
		del_filename_entry(data_buf->filename->filename);
		return 1;
	}
	return 0;
}

filename_list_t* create_filename_entry(char* filename) {
	filename_list_t* fn_entry = (filename_list_t*) malloc(sizeof(filename_list_t));
	fn_entry->filename = strndup(filename, PATH_MAX);
	fn_entry->error = 0;
	fn_entry->data = NULL;
	fn_entry->prev = NULL;
	fn_entry->next = NULL;
	return fn_entry;
}

filename_list_t* get_filename_entry(char* filename) {
	filename_list_t* cur = filename_list;
	while (cur != NULL) {
		if (strncmp(filename, cur->filename, PATH_MAX) == 0) {
			return cur;
		}
		cur = cur->next;
	}
	return NULL;
}

void add_filename_entry(filename_list_t* fe) {
	filename_list_t* cur = filename_list;
	if (cur == NULL) {
		filename_list = fe;
		fe->prev = NULL;
		fe->next = NULL;
	}
	else {
		while (cur->next != NULL) {
			cur = cur->next;
		}
		cur->next = fe;
		fe->prev = cur;
		fe->next = NULL;
	}
}

void del_filename_entry(char* filename) {
	filename_list_t* fe = get_filename_entry(filename);
	if (fe) {
		if (fe->prev) {
			fe->prev->next = fe->next;
		}
		if (fe->next) {
			fe->next->prev = fe->prev;
		}
		if (fe == filename_list) {
			filename_list = fe->next;
		}
		free(fe->filename);
		free(fe);
	}
}

file_data_t* create_file_data(void* buf, size_t size) {
	file_data_t* data = (file_data_t*) malloc(sizeof(file_data_t));
	data->fd = next_fd++;
	data->offset = 0;
	data->data = create_data_buffer(buf, size);
	data->prev = NULL;
	data->next = NULL;
	return data;
}

file_data_t* create_file_data_from_buf(data_buf_t* data_buf) {
	file_data_t* data = (file_data_t*) malloc(sizeof(file_data_t));
	data->fd = next_fd++;
	data->data = data_buf;
	data->prev = NULL;
	data->next = NULL;
	return data;
}

file_data_t* get_file_data(int fd) {
	file_data_t* cur = data_list;
	while (cur != NULL) {
		if (cur->fd == fd) {
			return cur;
		}
		cur = cur->next;
	}
	return NULL;
}

void add_file_data(file_data_t* data) {
	file_data_t* cur = data_list;
	if (cur == NULL) {
		data_list = data;
		data->prev = NULL;
		data->next = NULL;
	}
	else {
		while (cur->next != NULL) {
			cur = cur->next;
		}
		cur->next = data;
		data->prev = cur;
		data->next = NULL;
	}
}

void del_file_data(int fd) {
	file_data_t* data = get_file_data(fd);
	if (data) {
		del_data_buffer(data->data);
		if (data->prev) {
			data->prev->next = data->next;
		}
		if (data->next) {
			data->next->prev = data->prev;
		}
		if (data == data_list) {
			data_list = data->next;
		}
		free(data);
	}
}

ssize_t read_file_data(int fd, void* buf, size_t nbytes) {
	file_data_t* data = get_file_data(fd);
	if (data) {
		if (data->offset >= data->data->size) {
			return EOF;
		}
		if (data->offset + nbytes > data->data->size) {
			nbytes = data->data->size - data->offset;
		}
		memcpy(buf, data->data->data + data->offset, nbytes);
		data->offset += nbytes;
		return nbytes;
	}
	else {
		errno = EIO;
		return -1;
	}
}

char* append_hostname(const char* str) {
	size_t len = strnlen(str, 128);
	size_t hostname_len;
	char hostname[128];
	char* newstr;
	gethostname(hostname, 127);
	hostname_len = strnlen(hostname, 127);
	newstr = (char*) malloc(sizeof(char) * (len + hostname_len) + 1);
	strncpy(newstr, str, len);
	strncat(newstr, hostname, hostname_len);
	return newstr;
}

__attribute__((constructor))
void init(void) {
	char* sem_name = append_hostname(GDB_SEMAPHORE_NAME);
	char* mem_name = append_hostname(GDB_SHMEM_NAME);
	gdb_semaphore = sem_open(sem_name, 0);
	if (gdb_semaphore == SEM_FAILED) {
		printf("Failed to open semaphore: %d\n", errno);
	}
	else {
		gdb_mem_fd = shm_open(mem_name, O_RDWR, 0600);
		if (gdb_mem_fd == -1) {
			printf("Failed to open shared memory: %d\n", errno);
		}
		else {
			gdb_mem = (gdb_mem_t*) mmap((void*) 0, (size_t) GDB_SHMEM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, gdb_mem_fd, 0);
			if (gdb_mem == MAP_FAILED) {
				printf("Failed to mmap shared memory: %d\n", errno);
			}
			else {
				good = 1;
			}
		}
	}
	free(sem_name);
	free(mem_name);
}

__attribute__((destructor))
void fini(void) {
	int rc;
	char* sem_name = append_hostname(GDB_SEMAPHORE_NAME);
	char* mem_name = append_hostname(GDB_SHMEM_NAME);
	rc = munmap((void*) gdb_mem, (size_t) GDB_SHMEM_SIZE);
	if (rc) {
		printf("Failed to munmap shared memory: %d\n", errno);
	}
	shm_unlink(mem_name);
	if (close(gdb_mem_fd) == -1) {
		printf("Failed to close shared memory: %d\n", errno);
	}
	sem_unlink(sem_name);
	rc = sem_close(gdb_semaphore);
	if (rc) {
		printf("Failed to close semaphore: %d\n", errno);
	}
}

int acquire_semaphore(void) {
	int rc = sem_wait(gdb_semaphore);
	if (rc) {
		printf("Failed to acquire semaphore: %d\n", errno);
	}
	return rc;
}

int release_semaphore(void) {
	int rc = sem_post(gdb_semaphore);
	if (rc) {
		printf("Failed to release semaphore: %d\n", errno);
	}
	return rc;
}

int check_pgdb_memory_flag(void) {
	return gdb_mem->pgdb_dw == 1;
}

void* read_shmem(uint32_t* size) {
	uint32_t _size = gdb_mem->size;
	// Clear the PGDB-DW flag.
	gdb_mem->pgdb_dw = 0;
	*size = _size;
	void* buf = malloc(_size);
	memcpy(buf, (void*) gdb_mem->data, _size);
	return buf;
}

void write_shmem(void* buf, uint32_t size) {
	// Set the GDB-DW flag.
	gdb_mem->gdb_dw = 1;
	gdb_mem->size = size;
	memcpy((void*) gdb_mem->data, buf, size);
}

// Note, semaphore needs to be released after this returns.
void wait_for_data(void) {
	while (1) {
		if (!acquire_semaphore()) {
			if (check_pgdb_memory_flag()) {
				return;
			}
			else {
				release_semaphore();
				// Sleep for a little bit?
			}
		}
	}
}

int should_load_file(const char* path) {
	// Avoid intercepting /proc.
	if (strncmp(path, "/proc", 5) == 0) {
		return 0;
	}
	return 1;
}

file_data_t* create_file_from_shmem(const char* path) {
	uint32_t size;
	void* data;
	file_data_t* file_data;
	filename_list_t* fn_entry;
	char full_path[PATH_MAX];
	size_t path_len;
	realpath(path, full_path);
	path_len = strnlen(full_path, PATH_MAX);
	fn_entry = get_filename_entry(full_path);
	if (should_load_file(full_path) == 0) {
		return NULL;
	}
	if (fn_entry) {
		if (fn_entry->error) {
			return NULL;
		}
		file_data = create_file_data_from_buf(fn_entry->data);
		fn_entry->data->ref_count++;
		add_file_data(file_data);
		return file_data;
	}
	acquire_semaphore();
	write_shmem((void*) full_path, path_len);
	release_semaphore();
	wait_for_data();
	data = read_shmem(&size);
	if (memcmp(data, GDB_SHMEM_ERROR, 5) == 0) {
		free(data);
		fn_entry = create_filename_entry(full_path);
		fn_entry->error = 1;
		add_filename_entry(fn_entry);
		release_semaphore();
		return NULL;
	}
	file_data = create_file_data(data, size);
	add_file_data(file_data);
	fn_entry = create_filename_entry(full_path);
	fn_entry->data = file_data->data;
	file_data->data->filename = fn_entry;
	add_filename_entry(fn_entry);
	release_semaphore(); // wait_for_data acquired the semaphore.
	return file_data;
}

int open(const char* path, int flags, ...) {
	va_list ap;
	mode_t mode;
	orig_open_t orig_open = (orig_open_t) dlsym(RTLD_NEXT, "open");
	file_data_t* file_data;
	va_start(ap, flags);
	mode = va_arg(ap, mode_t);
	va_end(ap);
	if (!good) {
		return orig_open(path, flags, mode);
	}
	//printf("Open(%s, %d, %d)\n", path, flags, mode);
	errno = 0;
	file_data = create_file_from_shmem(path);
	if (!file_data) {
		return orig_open(path, flags, mode);
	}
	return file_data->fd;
}

int close(int d) {
	orig_close_t orig_close = (orig_close_t) dlsym(RTLD_NEXT, "close");
	file_data_t* file_data = get_file_data(d);
	if (file_data) {
		//printf("Close(%d)\n", d);
		errno = 0;
		del_file_data(d);
		return 0;
	}
	return orig_close(d);
}

ssize_t read(int d, void* buf, size_t nbytes) {
	orig_read_t orig_read = (orig_read_t) dlsym(RTLD_NEXT, "read");
	file_data_t* file_data = get_file_data(d);
	if (file_data) {
		//printf("Read(%d, %p, %d)\n", d, buf, nbytes);
		errno = 0;
		return read_file_data(d, buf, nbytes);
	}
	return orig_read(d, buf, nbytes);
}

ssize_t write(int d, const void* buf, size_t nbytes) {
	orig_write_t orig_write = (orig_write_t) dlsym(RTLD_NEXT, "write");
	file_data_t* file_data = get_file_data(d);
	if (file_data) {
		//printf("Write(%d, %p, %d)\n", d, buf, nbytes);
		// Do not support writing.
		errno = EIO;
		return -1;
	}
	return orig_write(d, buf, nbytes);
}

int fcntl(int fd, int cmd, ...) {
	va_list ap;
	int arg;
	orig_fcntl_t orig_fcntl = (orig_fcntl_t) dlsym(RTLD_NEXT, "fcntl");
	file_data_t* file_data = get_file_data(fd);
	va_start(ap, cmd);
	arg = va_arg(ap, int);
	va_end(ap);
	if (file_data) {
		//printf("Fcntl(%d, %d, %d)\n", fd, cmd, arg);
		errno = 0;
		// Succeed silently.
		return 0;
	}
	return orig_fcntl(fd, cmd, arg);
}

int fstat(int fd, struct stat* sb) {
	orig_fstat_t orig_fstat = (orig_fstat_t) dlsym(RTLD_NEXT, "fstat");
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Fstat(%d, %p)\n", fd, sb);
		errno = 0;
		// Fill with zeros.
		memset(sb, 0, sizeof(struct stat));
		return 0;
	}
	return orig_fstat(fd, sb);
}

off_t lseek(int fildes, off_t offset, int whence) {
	orig_lseek_t orig_lseek = (orig_lseek_t) dlsym(RTLD_NEXT, "lseek");
	file_data_t* file_data = get_file_data(fildes);
	if (file_data) {
		//printf("Lseek(%d, %d, %d)\n", fildes, offset, whence);
		errno = 0;
		switch (whence) {
		case SEEK_SET:
			file_data->offset = offset;
			break;
		case SEEK_CUR:
			file_data->offset += offset;
			break;
		case SEEK_END:
			file_data->offset = file_data->data->size + offset;
			break;
		default:
			errno = EINVAL;
			return -1;
		}
		return file_data->offset;
	}
	return orig_lseek(fildes, offset, whence);
}

ssize_t pread(int d, void* buf, size_t nbytes, off_t offset) {
	orig_pread_t orig_pread = (orig_pread_t) dlsym(RTLD_NEXT, "pread");
	file_data_t* file_data = get_file_data(d);
	off_t orig_offset;
	ssize_t bytes_read;
	if (file_data) {
		//printf("Pread(%d, %p, %d, %d)\n", d, buf, nbytes, offset);
		errno = 0;
		orig_offset = file_data->offset;
		file_data->offset = offset;
		bytes_read = read_file_data(d, buf, nbytes);
		file_data->offset = orig_offset;
		return bytes_read;
	}
	return orig_pread(d, buf, nbytes, offset);
}

FILE* fopen(const char* path, const char* mode) {
	orig_fopen_t orig_fopen = (orig_fopen_t) dlsym(RTLD_NEXT, "fopen");
	file_data_t* file_data;
	//printf("Fopen(%s, %s)\n", path, mode);
	errno = 0;
	file_data = create_file_from_shmem(path);
	if (!file_data) {
		return orig_fopen(path, mode);
	}
	return (FILE*) file_data->fd;
}

FILE* fdopen(int fd, const char* mode) {
	orig_fdopen_t orig_fdopen = (orig_fdopen_t) dlsym(RTLD_NEXT, "fdopen");
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Fdopen(%d, %s)\n", fd, mode);
		errno = 0;
		return (FILE*) file_data->fd;
	}
	return orig_fdopen(fd, mode);
}

int fclose(FILE* stream) {
	orig_fclose_t orig_fclose = (orig_fclose_t) dlsym(RTLD_NEXT, "fclose");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Fclose(%p)\n", stream);
		errno = 0;
		del_file_data(fd);
		return 0;
	}
	return orig_fclose(stream);
}

size_t fread(void* restrict ptr, size_t size, size_t nitems, FILE* restrict stream) {
	orig_fread_t orig_fread = (orig_fread_t) dlsym(RTLD_NEXT, "fread");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	ssize_t nread;
	if (file_data) {
		//printf("Fread(%p, %d, %d, %p)\n", ptr, size, nitems, stream);
		errno = 0;
		nread = read_file_data(fd, ptr, size * nitems);
		if (nread >= 0) {
			return nread / size;
		}
		return 0;
	}
	return orig_fread(ptr, size, nitems, stream);
}

size_t fwrite(const void* restrict ptr, size_t size, size_t nitems, FILE* restrict stream) {
	orig_fwrite_t orig_fwrite = (orig_fwrite_t) dlsym(RTLD_NEXT, "fwrite");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Fwrite(%p, %d, %d, %p)\n", ptr, size, nitems, stream);
		// Do not support writing.
		return 0;
	}
	return orig_fwrite(ptr, size, nitems, stream);
}

int fgetc(FILE* stream) {
	orig_fgetc_t orig_fgetc = (orig_fgetc_t) dlsym(RTLD_NEXT, "fgetc");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	char buf;
	ssize_t nbytes;
	if (file_data) {
		//printf("Fgetc(%p)\n", stream);
		errno = 0;
		nbytes = read_file_data(fd, &buf, 1);
		if (nbytes > 0) {
			return buf;
		}
		if (nbytes == 0) {
			return EOF;
		}
		return -1;
	}
	return orig_fgetc(stream);
}

char* fgets(char* restrict str, int size, FILE* restrict stream) {
	orig_fgets_t orig_fgets = (orig_fgets_t) dlsym(RTLD_NEXT, "fgets");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Fgets(%p, %d, %p)\n", str, size, stream);
		errno = 0;
		// TODO.
		return NULL;
	}
	return orig_fgets(str, size, stream);
}

void clearerr(FILE* stream) {
	orig_clearerr_t orig_clearerr = (orig_clearerr_t) dlsym(RTLD_NEXT, "clearerr");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (!file_data) {
		orig_clearerr(stream);
	}
	//printf("Clearerr(%p)\n", stream);
	errno = 0;
}

int feof(FILE* stream) {
	orig_feof_t orig_feof = (orig_feof_t) dlsym(RTLD_NEXT, "feof");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Feof(%p)\n", stream);
		errno = 0;
		if (file_data->offset >= file_data->data->size) {
			return 1;
		}
		return 0;
	}
	return orig_feof(stream);
}

int ferror(FILE* stream) {
	orig_ferror_t orig_ferror = (orig_ferror_t) dlsym(RTLD_NEXT, "ferror");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Ferror(%p)\n", stream);
		errno = 0;
		return 0;
	}
	return orig_ferror(stream);
}

int fileno(FILE* stream) {
	orig_fileno_t orig_fileno = (orig_fileno_t) dlsym(RTLD_NEXT, "fileno");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Fileno(%p)\n", stream);
		errno = 0;
		return fd;
	}
	return orig_fileno(stream);
}

int fileno_unlocked(FILE* stream) {
	orig_fileno_unlocked_t orig_fileno_unlocked = (orig_fileno_unlocked_t) dlsym(RTLD_NEXT, "fileno_unlocked");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Fileno_unlocked(%p)\n", stream);
		errno = 0;
		return fd;
	}
	return orig_fileno_unlocked(stream);
}

int fseeko64(FILE* stream, off64_t offset, int whence) {
	orig_fseeko64_t orig_fseeko64 = (orig_fseeko64_t) dlsym(RTLD_NEXT, "fseeko64");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Fseeko64(%p, %d, %d)\n", stream, offset, whence);
		errno = 0;
		switch (whence) {
		case SEEK_SET:
			file_data->offset = offset;
			break;
		case SEEK_CUR:
			file_data->offset += offset;
			break;
		case SEEK_END:
			file_data->offset = file_data->data->size + offset;
			break;
		default:
			errno = EINVAL;
			return -1;
		}
		return 0;
	}
	return orig_fseeko64(stream, offset, whence);
}

off64_t ftello64(FILE* stream) {
	orig_ftello64_t orig_ftello64 = (orig_ftello64_t) dlsym(RTLD_NEXT, "ftello64");
	int fd = (int) stream;
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Ftello64(%p)\n", stream);
		errno = 0;
		return file_data->offset;
	}
	return orig_ftello64(stream);
}

void* mmap(void* addr, size_t len, int prot, int flags, int fd, off_t offset) {
	orig_mmap_t orig_mmap = (orig_mmap_t) dlsym(RTLD_NEXT, "mmap");
	file_data_t* file_data = get_file_data(fd);
	if (file_data) {
		//printf("Mmap(%p, %d, %d, %d, %d, %d)\n", addr, len, prot, flags, fd, offset);
		errno = 0;
		if (flags & MAP_FIXED) {
			errno = ENOMEM;
			return MAP_FAILED;
		}
		file_data->data->ref_count++;
		return file_data->data;
	}
	return orig_mmap(addr, len, prot, flags, fd, offset);
}

int munmap(void* addr, size_t len) {
	orig_munmap_t orig_munmap = (orig_munmap_t) dlsym(RTLD_NEXT, "munmap");
	file_data_t* file_data = data_list;
	while (file_data != NULL) {
		errno = 0;
		if (file_data->data == addr) {
			//printf("Munmap(%p, %d)\n", addr, len);
			del_file_data(file_data->fd);
			return 0;
		}
		file_data = file_data->next;
	}
	return orig_munmap(addr, len);
}
