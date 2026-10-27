#include "utils.h"

#include <flutter_windows.h>
#include <io.h>
#include <stdio.h>
#include <windows.h>

#include <iostream>

void CreateAndAttachConsole() {
  if (::AllocConsole()) {
    FILE *unused;
    if (freopen_s(&unused, "CONOUT$", "w", stdout)) {
      _dup2(_fileno(stdout), 1);
    }
    if (freopen_s(&unused, "CONOUT$", "w", stderr)) {
      _dup2(_fileno(stdout), 2);
    }
    std::ios::sync_with_stdio();
    FlutterDesktopResyncOutputStreams();
  }
}

std::vector<std::string> GetCommandLineArguments() {
  // Convert the UTF-16 command line arguments to UTF-8 for the Engine to use.
  int argc;
  wchar_t** argv = ::CommandLineToArgvW(::GetCommandLineW(), &argc);
  if (argv == nullptr) {
    return std::vector<std::string>();
  }

  std::vector<std::string> command_line_arguments;

  // Skip the first argument as it's the binary name.
  for (int i = 1; i < argc; i++) {
    command_line_arguments.push_back(Utf8FromUtf16(argv[i]));
  }

  ::LocalFree(argv);

  return command_line_arguments;
}

std::string Utf8FromUtf16(const wchar_t* utf16_string) {
  if (utf16_string == nullptr) {
    return std::string();
  }
  unsigned int target_length = ::WideCharToMultiByte(
      CP_UTF8, WC_ERR_INVALID_CHARS, utf16_string,
      -1, nullptr, 0, nullptr, nullptr)
    -1; // remove the trailing null character
  int input_length = (int)wcslen(utf16_string);
  std::string utf8_string;
  if (target_length == 0 || target_length > utf8_string.max_size()) {
    return utf8_string;
  }
  utf8_string.resize(target_length);
  int converted_length = ::WideCharToMultiByte(
      CP_UTF8, WC_ERR_INVALID_CHARS, utf16_string,
      input_length, utf8_string.data(), target_length, nullptr, nullptr);
  if (converted_length == 0) {
    return std::string();
  }
  return utf8_string;
}

void ShowAndFocusWindow(HWND window) {
  if (window == nullptr || !::IsWindow(window)) return;

  if (::IsIconic(window)) {
    ::ShowWindow(window, SW_RESTORE);
  } else {
    ::ShowWindow(window, SW_SHOW);
  }

  RECT rect{};
  HMONITOR monitor = nullptr;
  if (::GetWindowRect(window, &rect)) {
    monitor = ::MonitorFromRect(&rect, MONITOR_DEFAULTTONULL);
  }

  // A normal visible window must still intersect a monitor. This catches the
  // -32000 sentinel rectangle left by some hide/minimize transitions.
  bool intersects_monitor = false;
  if (monitor != nullptr) {
    MONITORINFO info{};
    info.cbSize = sizeof(info);
    if (::GetMonitorInfo(monitor, &info)) {
      RECT visible{};
      intersects_monitor =
          ::IntersectRect(&visible, &rect, &info.rcWork) != FALSE &&
          visible.right - visible.left >= 120 &&
          visible.bottom - visible.top >= 80;
    }
  }

  if (!intersects_monitor) {
    monitor = ::MonitorFromWindow(window, MONITOR_DEFAULTTOPRIMARY);
    MONITORINFO info{};
    info.cbSize = sizeof(info);
    if (monitor != nullptr && ::GetMonitorInfo(monitor, &info)) {
      const LONG work_width = info.rcWork.right - info.rcWork.left;
      const LONG work_height = info.rcWork.bottom - info.rcWork.top;
      LONG width = rect.right - rect.left;
      LONG height = rect.bottom - rect.top;
      if (width < 980) width = 980;
      if (height < 622) height = 622;
      if (width > work_width) width = work_width;
      if (height > work_height) height = work_height;
      const LONG x = info.rcWork.left + (work_width - width) / 2;
      const LONG y = info.rcWork.top + (work_height - height) / 2;
      ::SetWindowPos(window, HWND_TOP, x, y, width, height,
                     SWP_SHOWWINDOW | SWP_NOOWNERZORDER);
    }
  }

  ::SetForegroundWindow(window);
}
