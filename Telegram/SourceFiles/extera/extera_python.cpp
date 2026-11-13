/*
This file is part of extera Desktop,
an unofficial exteraGram build for PC based on Telegram Desktop.

For license and copyright information please follow this link:
https://github.com/tnt-cat/exera-desktop/blob/exg/LEGAL
*/
#include "extera/extera_python.h"

#include <QtCore/QDir>
#include <QtCore/QFile>

#ifdef Q_OS_WIN
#include <windows.h>
#endif // Q_OS_WIN

namespace Extera::Python {
namespace {

struct Object;

struct MethodDef {
	const char *name = nullptr;
	Object *(*method)(Object*, Object*) = nullptr;
	int flags = 0;
	const char *doc = nullptr;
};

#define EXTERA_PYTHON_API(X) \
	X(void, Py_SetPythonHome, (const wchar_t*)) \
	X(void, Py_InitializeEx, (int)) \
	X(int, Py_IsInitialized, ()) \
	X(void*, PyEval_SaveThread, ()) \
	X(int, PyGILState_Ensure, ()) \
	X(void, PyGILState_Release, (int)) \
	X(Object*, PyImport_ImportModule, (const char*)) \
	X(Object*, PyImport_AddModule, (const char*)) \
	X(Object*, PyObject_GetAttrString, (Object*, const char*)) \
	X(int, PyObject_SetAttrString, (Object*, const char*, Object*)) \
	X(Object*, PyObject_CallFunction, (Object*, const char*, ...)) \
	X(Object*, PyObject_CallMethod, (Object*, const char*, const char*, ...)) \
	X(Object*, PyObject_Str, (Object*)) \
	X(const char*, PyUnicode_AsUTF8AndSize, (Object*, ptrdiff_t*)) \
	X(Object*, PyUnicode_FromStringAndSize, (const char*, ptrdiff_t)) \
	X(Object*, PyTuple_GetItem, (Object*, ptrdiff_t)) \
	X(Object*, PyCFunction_NewEx, (MethodDef*, Object*, Object*)) \
	X(void, Py_DecRef, (Object*)) \
	X(void, PyErr_Fetch, (Object**, Object**, Object**)) \
	X(void, PyErr_Clear, ())

struct Functions {
#define EXTERA_PYTHON_FIELD(result, name, args) result (*name) args = nullptr;
	EXTERA_PYTHON_API(EXTERA_PYTHON_FIELD)
#undef EXTERA_PYTHON_FIELD
};

constexpr auto kMethVarArgs = 0x0001;

Functions Py;
Object *Bridge = nullptr;
HostCallback Host;
MethodDef HostMethod;
std::wstring Home;
QString LastError;
bool Started = false;

[[nodiscard]] QByteArray ToBytes(Object *value) {
	auto size = ptrdiff_t(0);
	const auto data = value
		? Py.PyUnicode_AsUTF8AndSize(value, &size)
		: nullptr;
	return data ? QByteArray(data, int(size)) : QByteArray();
}

[[nodiscard]] QString TakeError() {
	Object *type = nullptr;
	Object *value = nullptr;
	Object *trace = nullptr;
	Py.PyErr_Fetch(&type, &value, &trace);
	const auto text = value ? Py.PyObject_Str(value) : nullptr;
	const auto result = QString::fromUtf8(ToBytes(text));
	Py.PyErr_Clear();
	Py.Py_DecRef(text);
	Py.Py_DecRef(type);
	Py.Py_DecRef(value);
	Py.Py_DecRef(trace);
	return result;
}

Object *HostCall(Object*, Object *args) {
	const auto name = ToBytes(Py.PyTuple_GetItem(args, 0));
	const auto payload = ToBytes(Py.PyTuple_GetItem(args, 1));
	Py.PyErr_Clear();
	const auto result = Host ? Host(name, payload) : QByteArray();
	return Py.PyUnicode_FromStringAndSize(
		result.constData(),
		ptrdiff_t(result.size()));
}

} // namespace

bool Start(
		const QString &runtimeDir,
		const QString &sdkDir,
		HostCallback host) {
	if (Started) {
		return true;
	}
#ifdef Q_OS_WIN
	const auto dir = QDir(runtimeDir).absolutePath();
	const auto library = QDir::toNativeSeparators(dir + u"/python311.dll"_q);
	const auto hasLibrary = QFile::exists(dir + u"/python311.zip"_q)
		|| QFile::exists(dir + u"/Lib/os.py"_q);
	if (!QFile::exists(library) || !hasLibrary) {
		LastError = u"Python runtime not found in "_q
			+ QDir::toNativeSeparators(dir);
		return false;
	}
	const auto handle = LoadLibraryExW(
		library.toStdWString().c_str(),
		nullptr,
		LOAD_WITH_ALTERED_SEARCH_PATH);
	if (!handle) {
		LastError = u"Could not load %1 (error %2)"_q.arg(library).arg(
			int(GetLastError()));
		return false;
	}
	auto missing = QStringList();
#define EXTERA_PYTHON_LOAD(result, name, args) \
	Py.name = reinterpret_cast<decltype(Py.name)>( \
		GetProcAddress(handle, #name)); \
	if (!Py.name) { \
		missing.push_back(QString::fromLatin1(#name)); \
	}
	EXTERA_PYTHON_API(EXTERA_PYTHON_LOAD)
#undef EXTERA_PYTHON_LOAD
	if (!missing.isEmpty()) {
		LastError = u"Python runtime misses: "_q + missing.join(u", "_q);
		return false;
	}

	if (!QFile::exists(dir + u"/python311._pth"_q)) {
		Home = QDir::toNativeSeparators(dir).toStdWString();
		Py.Py_SetPythonHome(Home.c_str());
	}
	Py.Py_InitializeEx(0);
	if (!Py.Py_IsInitialized()) {
		LastError = u"Python did not start."_q;
		return false;
	}
	Host = std::move(host);

	const auto sys = Py.PyImport_ImportModule("sys");
	const auto path = sys ? Py.PyObject_GetAttrString(sys, "path") : nullptr;
	if (path) {
		const auto packages = QDir::toNativeSeparators(
			dir + u"/Lib/site-packages"_q).toUtf8();
		const auto sdk = QDir::toNativeSeparators(
			QDir(sdkDir).absolutePath()).toUtf8();
		Py.Py_DecRef(Py.PyObject_CallMethod(
			path,
			"append",
			"s",
			packages.constData()));
		Py.Py_DecRef(Py.PyObject_CallMethod(
			path,
			"insert",
			"is",
			0,
			sdk.constData()));
	}
	Py.Py_DecRef(path);
	Py.Py_DecRef(sys);

	HostMethod = { "call", &HostCall, kMethVarArgs, nullptr };
	const auto module = Py.PyImport_AddModule("_extera_host");
	const auto function = Py.PyCFunction_NewEx(&HostMethod, nullptr, nullptr);
	if (module && function) {
		Py.PyObject_SetAttrString(module, "call", function);
	}
	Py.Py_DecRef(function);
	Py.PyErr_Clear();

	const auto bridge = Py.PyImport_ImportModule("extera_bridge");
	Bridge = bridge ? Py.PyObject_GetAttrString(bridge, "call") : nullptr;
	if (!Bridge) {
		LastError = u"Could not load the plugin engine: "_q + TakeError();
	}
	Py.PyEval_SaveThread();
	Started = (Bridge != nullptr);
	return Started;
#else // Q_OS_WIN
	LastError = u"Plugins work only on Windows for now."_q;
	return false;
#endif // Q_OS_WIN
}

bool Running() {
	return Started;
}

QString Error() {
	return LastError;
}

QByteArray Call(const QByteArray &name, const QByteArray &payload) {
	if (!Started) {
		return QByteArray();
	}
	const auto state = Py.PyGILState_Ensure();
	const auto result = Py.PyObject_CallFunction(
		Bridge,
		"ss",
		name.constData(),
		payload.constData());
	const auto bytes = ToBytes(result);
	if (!result) {
		LastError = TakeError();
	}
	Py.Py_DecRef(result);
	Py.PyGILState_Release(state);
	return bytes;
}

} // namespace Extera::Python
