#define _CFFI_

/* We try to define Py_LIMITED_API before including Python.h.

   Mess: we can only define it if Py_DEBUG, Py_TRACE_REFS and
   Py_REF_DEBUG are not defined.  This is a best-effort approximation:
   we can learn about Py_DEBUG from pyconfig.h, but it is unclear if
   the same works for the other two macros.  Py_DEBUG implies them,
   but not the other way around.

   The implementation is messy (issue #350): on Windows, with _MSC_VER,
   we have to define Py_LIMITED_API even before including pyconfig.h.
   In that case, we guess what pyconfig.h will do to the macros above,
   and check our guess after the #include.

   Note that on Windows, with CPython 3.x, you need >= 3.5 and virtualenv
   version >= 16.0.0.  With older versions of either, you don't get a
   copy of PYTHON3.DLL in the virtualenv.  We can't check the version of
   CPython *before* we even include pyconfig.h.  ffi.set_source() puts
   a ``#define _CFFI_NO_LIMITED_API'' at the start of this file if it is
   running on Windows < 3.5, as an attempt at fixing it, but that's
   arguably wrong because it may not be the target version of Python.
   Still better than nothing I guess.  As another workaround, you can
   remove the definition of Py_LIMITED_API here.

   See also 'py_limited_api' in cffi/setuptools_ext.py.
*/
#if !defined(_CFFI_USE_EMBEDDING) && !defined(Py_LIMITED_API)
#  ifdef _MSC_VER
#    if !defined(_DEBUG) && !defined(Py_DEBUG) && !defined(Py_TRACE_REFS) && !defined(Py_REF_DEBUG) && !defined(_CFFI_NO_LIMITED_API)
#      define Py_LIMITED_API
#    endif
#    include <pyconfig.h>
     /* sanity-check: Py_LIMITED_API will cause crashes if any of these
        are also defined.  Normally, the Python file PC/pyconfig.h does not
        cause any of these to be defined, with the exception that _DEBUG
        causes Py_DEBUG.  Double-check that. */
#    ifdef Py_LIMITED_API
#      if defined(Py_DEBUG)
#        error "pyconfig.h unexpectedly defines Py_DEBUG, but Py_LIMITED_API is set"
#      endif
#      if defined(Py_TRACE_REFS)
#        error "pyconfig.h unexpectedly defines Py_TRACE_REFS, but Py_LIMITED_API is set"
#      endif
#      if defined(Py_REF_DEBUG)
#        error "pyconfig.h unexpectedly defines Py_REF_DEBUG, but Py_LIMITED_API is set"
#      endif
#    endif
#  else
#    include <pyconfig.h>
#    if !defined(Py_DEBUG) && !defined(Py_TRACE_REFS) && !defined(Py_REF_DEBUG) && !defined(_CFFI_NO_LIMITED_API)
#      define Py_LIMITED_API
#    endif
#  endif
#endif

#include <Python.h>
#ifdef __cplusplus
extern "C" {
#endif
#include <stddef.h>
#include "parse_c_type.h"

/* this block of #ifs should be kept exactly identical between
   c/_cffi_backend.c, cffi/vengine_cpy.py, cffi/vengine_gen.py
   and cffi/_cffi_include.h */
#if defined(_MSC_VER)
# include <malloc.h>   /* for alloca() */
# if _MSC_VER < 1600   /* MSVC < 2010 */
   typedef __int8 int8_t;
   typedef __int16 int16_t;
   typedef __int32 int32_t;
   typedef __int64 int64_t;
   typedef unsigned __int8 uint8_t;
   typedef unsigned __int16 uint16_t;
   typedef unsigned __int32 uint32_t;
   typedef unsigned __int64 uint64_t;
   typedef __int8 int_least8_t;
   typedef __int16 int_least16_t;
   typedef __int32 int_least32_t;
   typedef __int64 int_least64_t;
   typedef unsigned __int8 uint_least8_t;
   typedef unsigned __int16 uint_least16_t;
   typedef unsigned __int32 uint_least32_t;
   typedef unsigned __int64 uint_least64_t;
   typedef __int8 int_fast8_t;
   typedef __int16 int_fast16_t;
   typedef __int32 int_fast32_t;
   typedef __int64 int_fast64_t;
   typedef unsigned __int8 uint_fast8_t;
   typedef unsigned __int16 uint_fast16_t;
   typedef unsigned __int32 uint_fast32_t;
   typedef unsigned __int64 uint_fast64_t;
   typedef __int64 intmax_t;
   typedef unsigned __int64 uintmax_t;
# else
#  include <stdint.h>
# endif
# if _MSC_VER < 1800   /* MSVC < 2013 */
#  ifndef __cplusplus
    typedef unsigned char _Bool;
#  endif
# endif
# define _cffi_float_complex_t   _Fcomplex    /* include <complex.h> for it */
# define _cffi_double_complex_t  _Dcomplex    /* include <complex.h> for it */
#else
# include <stdint.h>
# if (defined (__SVR4) && defined (__sun)) || defined(_AIX) || defined(__hpux)
#  include <alloca.h>
# endif
# define _cffi_float_complex_t   float _Complex
# define _cffi_double_complex_t  double _Complex
#endif

#ifdef __GNUC__
# define _CFFI_UNUSED_FN  __attribute__((unused))
#else
# define _CFFI_UNUSED_FN  /* nothing */
#endif

#ifdef __cplusplus
# ifndef _Bool
   typedef bool _Bool;   /* semi-hackish: C++ has no _Bool; bool is builtin */
# endif
#endif

/**********  CPython-specific section  **********/
#ifndef PYPY_VERSION


#if PY_MAJOR_VERSION >= 3
# define PyInt_FromLong PyLong_FromLong
#endif

#define _cffi_from_c_double PyFloat_FromDouble
#define _cffi_from_c_float PyFloat_FromDouble
#define _cffi_from_c_long PyInt_FromLong
#define _cffi_from_c_ulong PyLong_FromUnsignedLong
#define _cffi_from_c_longlong PyLong_FromLongLong
#define _cffi_from_c_ulonglong PyLong_FromUnsignedLongLong
#define _cffi_from_c__Bool PyBool_FromLong

#define _cffi_to_c_double PyFloat_AsDouble
#define _cffi_to_c_float PyFloat_AsDouble

#define _cffi_from_c_int(x, type)                                        \
    (((type)-1) > 0 ? /* unsigned */                                     \
        (sizeof(type) < sizeof(long) ?                                   \
            PyInt_FromLong((long)x) :                                    \
         sizeof(type) == sizeof(long) ?                                  \
            PyLong_FromUnsignedLong((unsigned long)x) :                  \
            PyLong_FromUnsignedLongLong((unsigned long long)x)) :        \
        (sizeof(type) <= sizeof(long) ?                                  \
            PyInt_FromLong((long)x) :                                    \
            PyLong_FromLongLong((long long)x)))

#define _cffi_to_c_int(o, type)                                          \
    ((type)(                                                             \
     sizeof(type) == 1 ? (((type)-1) > 0 ? (type)_cffi_to_c_u8(o)        \
                                         : (type)_cffi_to_c_i8(o)) :     \
     sizeof(type) == 2 ? (((type)-1) > 0 ? (type)_cffi_to_c_u16(o)       \
                                         : (type)_cffi_to_c_i16(o)) :    \
     sizeof(type) == 4 ? (((type)-1) > 0 ? (type)_cffi_to_c_u32(o)       \
                                         : (type)_cffi_to_c_i32(o)) :    \
     sizeof(type) == 8 ? (((type)-1) > 0 ? (type)_cffi_to_c_u64(o)       \
                                         : (type)_cffi_to_c_i64(o)) :    \
     (Py_FatalError("unsupported size for type " #type), (type)0)))

#define _cffi_to_c_i8                                                    \
                 ((int(*)(PyObject *))_cffi_exports[1])
#define _cffi_to_c_u8                                                    \
                 ((int(*)(PyObject *))_cffi_exports[2])
#define _cffi_to_c_i16                                                   \
                 ((int(*)(PyObject *))_cffi_exports[3])
#define _cffi_to_c_u16                                                   \
                 ((int(*)(PyObject *))_cffi_exports[4])
#define _cffi_to_c_i32                                                   \
                 ((int(*)(PyObject *))_cffi_exports[5])
#define _cffi_to_c_u32                                                   \
                 ((unsigned int(*)(PyObject *))_cffi_exports[6])
#define _cffi_to_c_i64                                                   \
                 ((long long(*)(PyObject *))_cffi_exports[7])
#define _cffi_to_c_u64                                                   \
                 ((unsigned long long(*)(PyObject *))_cffi_exports[8])
#define _cffi_to_c_char                                                  \
                 ((int(*)(PyObject *))_cffi_exports[9])
#define _cffi_from_c_pointer                                             \
    ((PyObject *(*)(char *, struct _cffi_ctypedescr *))_cffi_exports[10])
#define _cffi_to_c_pointer                                               \
    ((char *(*)(PyObject *, struct _cffi_ctypedescr *))_cffi_exports[11])
#define _cffi_get_struct_layout                                          \
    not used any more
#define _cffi_restore_errno                                              \
    ((void(*)(void))_cffi_exports[13])
#define _cffi_save_errno                                                 \
    ((void(*)(void))_cffi_exports[14])
#define _cffi_from_c_char                                                \
    ((PyObject *(*)(char))_cffi_exports[15])
#define _cffi_from_c_deref                                               \
    ((PyObject *(*)(char *, struct _cffi_ctypedescr *))_cffi_exports[16])
#define _cffi_to_c                                                       \
    ((int(*)(char *, struct _cffi_ctypedescr *, PyObject *))_cffi_exports[17])
#define _cffi_from_c_struct                                              \
    ((PyObject *(*)(char *, struct _cffi_ctypedescr *))_cffi_exports[18])
#define _cffi_to_c_wchar_t                                               \
    ((_cffi_wchar_t(*)(PyObject *))_cffi_exports[19])
#define _cffi_from_c_wchar_t                                             \
    ((PyObject *(*)(_cffi_wchar_t))_cffi_exports[20])
#define _cffi_to_c_long_double                                           \
    ((long double(*)(PyObject *))_cffi_exports[21])
#define _cffi_to_c__Bool                                                 \
    ((_Bool(*)(PyObject *))_cffi_exports[22])
#define _cffi_prepare_pointer_call_argument                              \
    ((Py_ssize_t(*)(struct _cffi_ctypedescr *,                           \
                    PyObject *, char **))_cffi_exports[23])
#define _cffi_convert_array_from_object                                  \
    ((int(*)(char *, struct _cffi_ctypedescr *, PyObject *))_cffi_exports[24])
#define _CFFI_CPIDX  25
#define _cffi_call_python                                                \
    ((void(*)(struct _cffi_externpy_s *, char *))_cffi_exports[_CFFI_CPIDX])
#define _cffi_to_c_wchar3216_t                                           \
    ((int(*)(PyObject *))_cffi_exports[26])
#define _cffi_from_c_wchar3216_t                                         \
    ((PyObject *(*)(int))_cffi_exports[27])
#define _CFFI_NUM_EXPORTS 28

struct _cffi_ctypedescr;

static void *_cffi_exports[_CFFI_NUM_EXPORTS];

#define _cffi_type(index)   (                           \
    assert((((uintptr_t)_cffi_types[index]) & 1) == 0), \
    (struct _cffi_ctypedescr *)_cffi_types[index])

static PyObject *_cffi_init(const char *module_name, Py_ssize_t version,
                            const struct _cffi_type_context_s *ctx)
{
    PyObject *module, *o_arg, *new_module;
    void *raw[] = {
        (void *)module_name,
        (void *)version,
        (void *)_cffi_exports,
        (void *)ctx,
    };

    module = PyImport_ImportModule("_cffi_backend");
    if (module == NULL)
        goto failure;

    o_arg = PyLong_FromVoidPtr((void *)raw);
    if (o_arg == NULL)
        goto failure;

    new_module = PyObject_CallMethod(
        module, (char *)"_init_cffi_1_0_external_module", (char *)"O", o_arg);

    Py_DECREF(o_arg);
    Py_DECREF(module);
    return new_module;

  failure:
    Py_XDECREF(module);
    return NULL;
}


#ifdef HAVE_WCHAR_H
typedef wchar_t _cffi_wchar_t;
#else
typedef uint16_t _cffi_wchar_t;   /* same random pick as _cffi_backend.c */
#endif

_CFFI_UNUSED_FN static uint16_t _cffi_to_c_char16_t(PyObject *o)
{
    if (sizeof(_cffi_wchar_t) == 2)
        return (uint16_t)_cffi_to_c_wchar_t(o);
    else
        return (uint16_t)_cffi_to_c_wchar3216_t(o);
}

_CFFI_UNUSED_FN static PyObject *_cffi_from_c_char16_t(uint16_t x)
{
    if (sizeof(_cffi_wchar_t) == 2)
        return _cffi_from_c_wchar_t((_cffi_wchar_t)x);
    else
        return _cffi_from_c_wchar3216_t((int)x);
}

_CFFI_UNUSED_FN static int _cffi_to_c_char32_t(PyObject *o)
{
    if (sizeof(_cffi_wchar_t) == 4)
        return (int)_cffi_to_c_wchar_t(o);
    else
        return (int)_cffi_to_c_wchar3216_t(o);
}

_CFFI_UNUSED_FN static PyObject *_cffi_from_c_char32_t(unsigned int x)
{
    if (sizeof(_cffi_wchar_t) == 4)
        return _cffi_from_c_wchar_t((_cffi_wchar_t)x);
    else
        return _cffi_from_c_wchar3216_t((int)x);
}

union _cffi_union_alignment_u {
    unsigned char m_char;
    unsigned short m_short;
    unsigned int m_int;
    unsigned long m_long;
    unsigned long long m_longlong;
    float m_float;
    double m_double;
    long double m_longdouble;
};

struct _cffi_freeme_s {
    struct _cffi_freeme_s *next;
    union _cffi_union_alignment_u alignment;
};

_CFFI_UNUSED_FN static int
_cffi_convert_array_argument(struct _cffi_ctypedescr *ctptr, PyObject *arg,
                             char **output_data, Py_ssize_t datasize,
                             struct _cffi_freeme_s **freeme)
{
    char *p;
    if (datasize < 0)
        return -1;

    p = *output_data;
    if (p == NULL) {
        struct _cffi_freeme_s *fp = (struct _cffi_freeme_s *)PyObject_Malloc(
            offsetof(struct _cffi_freeme_s, alignment) + (size_t)datasize);
        if (fp == NULL)
            return -1;
        fp->next = *freeme;
        *freeme = fp;
        p = *output_data = (char *)&fp->alignment;
    }
    memset((void *)p, 0, (size_t)datasize);
    return _cffi_convert_array_from_object(p, ctptr, arg);
}

_CFFI_UNUSED_FN static void
_cffi_free_array_arguments(struct _cffi_freeme_s *freeme)
{
    do {
        void *p = (void *)freeme;
        freeme = freeme->next;
        PyObject_Free(p);
    } while (freeme != NULL);
}

/**********  end CPython-specific section  **********/
#else
_CFFI_UNUSED_FN
static void (*_cffi_call_python_org)(struct _cffi_externpy_s *, char *);
# define _cffi_call_python  _cffi_call_python_org
#endif


#define _cffi_array_len(array)   (sizeof(array) / sizeof((array)[0]))

#define _cffi_prim_int(size, sign)                                      \
    ((size) == 1 ? ((sign) ? _CFFI_PRIM_INT8  : _CFFI_PRIM_UINT8)  :    \
     (size) == 2 ? ((sign) ? _CFFI_PRIM_INT16 : _CFFI_PRIM_UINT16) :    \
     (size) == 4 ? ((sign) ? _CFFI_PRIM_INT32 : _CFFI_PRIM_UINT32) :    \
     (size) == 8 ? ((sign) ? _CFFI_PRIM_INT64 : _CFFI_PRIM_UINT64) :    \
     _CFFI__UNKNOWN_PRIM)

#define _cffi_prim_float(size)                                          \
    ((size) == sizeof(float) ? _CFFI_PRIM_FLOAT :                       \
     (size) == sizeof(double) ? _CFFI_PRIM_DOUBLE :                     \
     (size) == sizeof(long double) ? _CFFI__UNKNOWN_LONG_DOUBLE :       \
     _CFFI__UNKNOWN_FLOAT_PRIM)

#define _cffi_check_int(got, got_nonpos, expected)      \
    ((got_nonpos) == (expected <= 0) &&                 \
     (got) == (unsigned long long)expected)

#ifdef MS_WIN32
# define _cffi_stdcall  __stdcall
#else
# define _cffi_stdcall  /* nothing */
#endif

#ifdef __cplusplus
}
#endif
